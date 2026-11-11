import base64
import hashlib
from logging import getLogger
from tempfile import NamedTemporaryFile
from urllib.parse import unquote

from django.db import IntegrityError
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import Throttled
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from pulpcore.plugin.access_policy import AccessPolicyFromDB
from pulpcore.plugin.models import Artifact, ContentArtifact, RemoteArtifact
from pulpcore.plugin.tasking import dispatch
from pulpcore.plugin.util import get_domain

from .models import NpmDistribution, Package
from .tasks.publish import aadd_and_remove
from .utils import (
    extract_npm_metadata_from_artifact,
    parse_sri,
    sanitize_manifest,
    sri_from_artifact,
)

logger = getLogger(__name__)


def _has_task_completed(task):
    if task.state == "completed":
        task.delete()
        return True
    elif task.state == "canceled":
        raise Throttled()
    else:
        error = task.error
        task.delete()
        raise Exception(str(error))


def _decode_package_name(raw_name):
    """Decode URL-encoded scoped package names (e.g. ``@scope%2Fname`` -> ``@scope/name``)."""
    return unquote(raw_name)


_EXPECTED_DIGEST_FIELDS = ("sha512", "sha384", "sha256", "sha224", "sha1")


def _expected_digests(content, content_artifact):
    """Collect every checksum known for an existing content unit."""
    expected = {}

    def add(algorithm, value):
        expected.setdefault(algorithm, set()).add(value.lower())

    if content.integrity:
        parsed = parse_sri(content.integrity)
        if parsed:
            add(*parsed)
    if content.shasum:
        add("sha1", content.shasum)

    if content_artifact is not None:
        for remote_artifact in RemoteArtifact.objects.filter(content_artifact=content_artifact):
            for field in _EXPECTED_DIGEST_FIELDS:
                value = getattr(remote_artifact, field, None)
                if value:
                    add(field, value)

    return expected


def _artifact_digest(artifact, algorithm, tarball_bytes):
    value = getattr(artifact, algorithm, None)
    if value:
        return value.lower()
    if tarball_bytes is not None:
        try:
            return hashlib.new(algorithm, tarball_bytes).hexdigest()
        except ValueError:
            return None
    return None


def _artifact_matches(artifact, expected, tarball_bytes):
    if not expected:
        return False
    for algorithm, values in expected.items():
        digest = _artifact_digest(artifact, algorithm, tarball_bytes)
        if digest is None or any(value != digest for value in values):
            return False
    return True


def _remove_orphan_artifact(artifact):
    if ContentArtifact.objects.filter(artifact=artifact).exists():
        return
    try:
        artifact.delete()
    except ProtectedError:
        # A concurrent request attached it after the check.
        pass


def _reject_publish(artifact, message, status=400):
    _remove_orphan_artifact(artifact)
    return Response({"error": message}, status=status)


def _validate_against_existing(content, content_artifact, artifact, tarball_bytes):
    """Return an error message, or attach the artifact when it is verified."""
    if content_artifact is not None and content_artifact.artifact is not None:
        if content_artifact.artifact.sha256 != artifact.sha256:
            return f"{content.name}@{content.version} already exists with different content"
        return None

    expected = _expected_digests(content, content_artifact)
    if not expected:
        return (
            f"{content.name}@{content.version} already exists and has no recorded "
            "integrity; refusing to attach different content"
        )
    if not _artifact_matches(artifact, expected, tarball_bytes):
        return f"{content.name}@{content.version} already exists with different content"

    if content_artifact is not None and content_artifact.artifact is None:
        content_artifact.artifact = artifact
        content_artifact.save(update_fields=["artifact"])
    return None


class NpmPublishView(APIView):
    """Handle npm/yarn publish requests (``PUT /<package>``)."""

    parser_classes = [JSONParser]
    permission_classes = [AccessPolicyFromDB]

    def initial(self, request, *args, **kwargs):
        self.action = request.method.lower()
        super().initial(request, *args, **kwargs)

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["put"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "npm_has_repository_perm:npm.modify_npmrepository",
            },
        ],
    }

    @classmethod
    def urlpattern(cls):
        return "npm/publish"

    @property
    def distribution(self):
        if not hasattr(self, "_distribution"):
            domain = get_domain()
            self._distribution = get_object_or_404(
                NpmDistribution,
                base_path=self.kwargs["path"],
                pulp_domain=domain,
            )
        return self._distribution

    def put(self, request, path, package_name):
        package_name = _decode_package_name(package_name)
        domain = get_domain()

        distribution = self.distribution
        repository = distribution.repository
        if not repository:
            return Response(
                {"error": "Distribution is not backed by a repository"},
                status=400,
            )

        body = request.data

        body_name = body.get("name")
        if body_name and body_name != package_name:
            return Response(
                {"error": "Package name in body does not match URL"},
                status=400,
            )

        versions = body.get("versions")
        if not versions or not isinstance(versions, dict):
            return Response({"error": "Missing or invalid 'versions' in request body"}, status=400)
        if len(versions) != 1:
            return Response({"error": "Publish body must contain exactly one version"}, status=400)

        attachments = body.get("_attachments")
        if not attachments or not isinstance(attachments, dict):
            return Response(
                {"error": "Missing or invalid '_attachments' in request body"},
                status=400,
            )

        version_key = next(iter(versions))
        attachment_key = next(iter(attachments))

        attachment_data = attachments[attachment_key].get("data")
        if not attachment_data:
            return Response({"error": "Attachment is missing 'data' field"}, status=400)

        try:
            tarball_bytes = base64.b64decode(attachment_data)
        except Exception:
            return Response({"error": "Could not base64-decode attachment data"}, status=400)

        artifact = self._save_artifact(tarball_bytes, domain)

        name = package_name
        version = version_key

        # The tarball's ``package.json`` is the authoritative source of the
        # package's own metadata. Never trust the publish request for it: npm
        # sends the same document, but any client can send anything.
        try:
            metadata = extract_npm_metadata_from_artifact(artifact)
        except ValueError as exc:
            return _reject_publish(artifact, f"Invalid npm tarball: {exc}")

        if metadata["name"] != name:
            return _reject_publish(artifact, "Package name in package.json does not match URL")
        if metadata["version"] != version:
            return _reject_publish(artifact, "Package version in package.json does not match URL")

        try:
            manifest = sanitize_manifest(metadata.get("manifest") or {}, strict=True)
        except ValueError as exc:
            return _reject_publish(artifact, str(exc))

        request_manifest = sanitize_manifest(versions.get(version_key) or {})
        if request_manifest and request_manifest != manifest:
            logger.warning(
                "Publish metadata for %s@%s disagrees with the tarball; using tarball metadata",
                name,
                version,
            )

        try:
            content = Package(
                name=name,
                version=version,
                manifest=manifest,
                integrity=sri_from_artifact(artifact),
                shasum=artifact.sha1 or None,
            )
            content.save()
        except IntegrityError:
            content = Package.objects.get(name=name, version=version, _pulp_domain=domain)
            existing_ca = (
                ContentArtifact.objects.filter(content=content).select_related("artifact").first()
            )
            error = _validate_against_existing(content, existing_ca, artifact, tarball_bytes)
            if error:
                return _reject_publish(artifact, error)

        relative_path = content.relative_path
        try:
            ContentArtifact.objects.create(
                artifact=artifact,
                content=content,
                relative_path=relative_path,
            )
        except IntegrityError:
            ca = ContentArtifact.objects.get(content=content, relative_path=relative_path)
            error = _validate_against_existing(content, ca, artifact, tarball_bytes)
            if error:
                return _reject_publish(artifact, error)

        dispatched_task = dispatch(
            aadd_and_remove,
            exclusive_resources=[repository],
            immediate=True,
            deferred=False,
            kwargs={
                "repository_pk": str(repository.pk),
                "add_content_units": [str(content.pk)],
                "remove_content_units": [],
            },
        )

        if _has_task_completed(dispatched_task):
            return Response({"ok": True}, status=201)

    @staticmethod
    def _save_artifact(tarball_bytes, domain):
        with NamedTemporaryFile("wb", suffix=".tgz") as tmp:
            tmp.write(tarball_bytes)
            tmp.flush()

            size = len(tarball_bytes)
            digests = {}
            for algorithm in Artifact.DIGEST_FIELDS:
                h = getattr(hashlib, algorithm)()
                h.update(tarball_bytes)
                digests[algorithm] = h.hexdigest()

            artifact = Artifact(
                file=tmp.name,
                size=size,
                pulp_domain=domain,
                **digests,
            )
            try:
                artifact.save()
            except IntegrityError:
                artifact = Artifact.objects.get(sha256=digests["sha256"], pulp_domain=domain)
                artifact.touch()
            return artifact


class NpmPingView(APIView):
    """Handle ``GET /-/ping`` -- registry health check."""

    authentication_classes = []
    permission_classes = [AccessPolicyFromDB]

    def initial(self, request, *args, **kwargs):
        self.action = request.method.lower()
        super().initial(request, *args, **kwargs)

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["get"],
                "principal": "*",
                "effect": "allow",
            }
        ]
    }

    @classmethod
    def urlpattern(cls):
        return "npm/ping"

    def get(self, request, **kwargs):
        return Response({})


class NpmWhoamiView(APIView):
    """Handle ``GET /-/whoami`` -- return the authenticated user."""

    permission_classes = [AccessPolicyFromDB]

    def initial(self, request, *args, **kwargs):
        self.action = request.method.lower()
        super().initial(request, *args, **kwargs)

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["get"],
                "principal": "authenticated",
                "effect": "allow",
            },
        ],
    }

    @classmethod
    def urlpattern(cls):
        return "npm/whoami"

    def get(self, request, **kwargs):
        username = None
        if hasattr(request, "user") and request.user and request.user.is_authenticated:
            username = request.user.username

        if not username:
            return Response({"error": "Not authenticated"}, status=401)

        return Response({"username": username})
