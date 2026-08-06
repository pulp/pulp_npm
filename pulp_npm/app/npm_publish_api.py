import base64
import hashlib
from logging import getLogger
from tempfile import NamedTemporaryFile
from urllib.parse import unquote

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import Throttled
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from pulpcore.plugin.access_policy import AccessPolicyFromDB
from pulpcore.plugin.models import Artifact, ContentArtifact
from pulpcore.plugin.tasking import dispatch
from pulpcore.plugin.util import get_domain

from .models import NpmDistribution, Package
from .tasks.publish import aadd_and_remove

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

        try:
            content = Package(name=name, version=version)
            content.save()
        except IntegrityError:
            content = Package.objects.get(name=name, version=version, _pulp_domain=domain)

        relative_path = content.relative_path
        try:
            ContentArtifact.objects.create(
                artifact=artifact,
                content=content,
                relative_path=relative_path,
            )
        except IntegrityError:
            ca = ContentArtifact.objects.get(content=content, relative_path=relative_path)
            if not ca.artifact:
                ca.artifact = artifact
                ca.save()

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
    permission_classes = []

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
