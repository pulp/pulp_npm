import asyncio
import json
import os
from contextlib import suppress
from logging import getLogger

import semver
from aiohttp.web_response import Response
from django.conf import settings
from django.db import models

from pulpcore.plugin.models import (
    AutoAddObjPermsMixin,
    Content,
    ContentArtifact,
    Distribution,
    Remote,
    Repository,
)
from pulpcore.plugin.util import get_domain_pk

from .utils import (
    PACKUMENT_MANIFEST_FIELDS,
    extract_npm_metadata_from_artifact,
    extract_package_info,
    has_install_script,
    sanitize_manifest,
    sri_from_artifact,
    urlpath_sanitize,
)

logger = getLogger(__name__)


class Package(Content):
    """
    The "npm" content type.

    Define fields you need for your new content type and
    specify uniqueness constraint to identify unit of this type.
    """

    TYPE = "package"
    repo_key_fields = ("name", "version")

    name = models.CharField(max_length=214)
    version = models.CharField(max_length=256)
    manifest = models.JSONField(default=dict, blank=True)
    #: Expected tarball integrity (SRI sha512) retained for deferred content,
    #: where no local Artifact exists yet. Replaced by the computed value once
    #: the artifact has been downloaded.
    integrity = models.CharField(max_length=255, null=True, blank=True)
    shasum = models.CharField(max_length=40, null=True, blank=True)
    _pulp_domain = models.ForeignKey("core.Domain", default=get_domain_pk, on_delete=models.PROTECT)

    @property
    def relative_path(self):
        """
        Returns relative_path.
        """
        base_name = self.name.split("/")[-1] if "/" in self.name else self.name
        return f"{self.name}/-/{base_name}-{self.version}.tgz"

    @staticmethod
    def init_from_artifact_and_relative_path(artifact, relative_path):
        name, version = extract_package_info(relative_path)

        # The tarball is the only source of the package's own metadata on this
        # path (generic upload, pull-through). Failing to read it must not fail
        # the whole content creation -- a package with no recorded manifest is
        # degraded, not broken -- so fall back to what the path alone tells us.
        manifest = {}
        try:
            metadata = extract_npm_metadata_from_artifact(artifact)
            manifest = sanitize_manifest(metadata.get("manifest") or {})
            name = name or metadata.get("name")
            version = version or metadata.get("version")
        except ValueError as exc:
            logger.warning("Could not read package.json from %s: %s", relative_path, exc)

        return Package(
            name=name,
            version=version,
            manifest=manifest,
            integrity=sri_from_artifact(artifact),
            shasum=artifact.sha1 or None,
        )

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = ("name", "version", "_pulp_domain")


class NpmRemote(Remote, AutoAddObjPermsMixin):
    """
    A Remote for NpmContent.

    Define any additional fields for your new remote if needed.
    """

    TYPE = "npm"

    def get_remote_artifact_content_type(self, relative_path=None):
        name, version = extract_package_info(relative_path)

        if name and version:
            return Package

        return None

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = [
            ("manage_roles_npmremote", "Can manage roles on npm remotes"),
        ]


class NpmRepository(Repository, AutoAddObjPermsMixin):
    """
    A Repository for NpmContent.

    Define any additional fields for your new repository if needed.
    """

    TYPE = "npm"

    CONTENT_TYPES = [Package]
    REMOTE_TYPES = [NpmRemote]

    PULL_THROUGH_SUPPORTED = True

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = [
            ("sync_npmrepository", "Can start a sync task"),
            ("modify_npmrepository", "Can modify content of the repository"),
            ("manage_roles_npmrepository", "Can manage roles on npm repositories"),
        ]


class NpmDistribution(Distribution, AutoAddObjPermsMixin):
    """
    Distribution for "npm" content.
    """

    TYPE = "npm"

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = [
            ("manage_roles_npmdistribution", "Can manage roles on npm distributions"),
        ]

    def content_handler(self, path):
        # A name+version path is a tarball request, handled by normal artifact lookup.
        # An unparsable path (name is None) is not a packument request either.
        name, version = extract_package_info(path)
        if not name or version:
            return None

        repository_version = None
        if self.repository:
            repository_version = self.repository_version or self.repository.latest_version()

        packages = (
            Package.objects.filter(name=name, pk__in=repository_version.content)
            if repository_version is not None
            else Package.objects.none()
        )

        if packages:
            return self._packument_from_local_packages(name, packages)

        # A remote is attached directly (pull-through, no repository content yet):
        # fetch it ourselves and rewrite tarball URLs, rather than returning None
        # and letting pulpcore proxy that same remote with unmodified URLs.
        if self.remote:
            return self._packument_from_remote(name)

        return None

    def _tarball_url_prefix(self):
        """Base URL under which this distribution serves package tarballs."""
        if settings.DOMAIN_ENABLED:
            return "{}/".format(
                urlpath_sanitize(
                    settings.CONTENT_ORIGIN,
                    settings.CONTENT_PATH_PREFIX,
                    self.pulp_domain.name,
                    self.base_path,
                )
            )
        return "{}/".format(
            urlpath_sanitize(
                settings.CONTENT_ORIGIN,
                settings.CONTENT_PATH_PREFIX,
                self.base_path,
            )
        )

    def _packument_from_local_packages(self, name, packages):
        data = {"name": name, "versions": {}}
        versions = []
        prefix_url = self._tarball_url_prefix()

        # Pull the stored checksums alongside the packages so `dist` can carry
        # integrity data, and so this stays one query rather than one per version.
        artifact_by_content = {
            ca.content_id: ca.artifact
            for ca in ContentArtifact.objects.filter(
                content__in=packages, artifact__isnull=False
            ).select_related("artifact")
        }

        for package in packages:
            tarball_url = f"{prefix_url}{package.name}/-/{package.relative_path.split('/')[-1]}"

            dist = {"tarball": tarball_url}
            artifact = artifact_by_content.get(package.pk)
            # Prefer checksums computed from the stored bytes. Deferred content
            # has no artifact yet, so fall back to the integrity captured from
            # the upstream registry document.
            integrity = sri_from_artifact(artifact) if artifact else None
            shasum = artifact.sha1 if artifact else None
            integrity = integrity or package.integrity
            shasum = shasum or package.shasum
            if integrity:
                dist["integrity"] = integrity
            if shasum:
                dist["shasum"] = shasum

            version_data = {
                key: package.manifest[key]
                for key in PACKUMENT_MANIFEST_FIELDS
                if key in (package.manifest or {})
            }
            # Derive the flag on serve as well, so content stored before this
            # change still reports install scripts correctly.
            if "scripts" in version_data:
                version_data["hasInstallScript"] = has_install_script(version_data)
            version_data.update(
                {
                    "name": package.name,
                    "version": package.version,
                    "_id": f"{package.name}@{package.version}",
                    "dist": dist,
                }
            )

            versions.append(package.version)
            data["versions"].update({package.version: version_data})

        parsed = {v: semver.Version.parse(v) for v in versions if semver.Version.is_valid(v)}
        stable_versions = [v for v, parsed_v in parsed.items() if not parsed_v.prerelease]
        if parsed:
            candidates = stable_versions or list(parsed)
            latest = max(candidates, key=parsed.get)
        else:
            # Some registries publish non-semver versions. Keep the registry
            # document usable instead of raising on an empty version set.
            latest = versions[-1]
        data["dist-tags"] = {"latest": latest}

        return Response(body=json.dumps(data), content_type="application/json")

    def _packument_from_remote(self, name):
        """Fetch the upstream packument and rewrite dist.tarball to point at Pulp."""
        remote = self.remote.cast()
        url = f"{remote.url.rstrip('/')}/{name}"

        async def download():
            # The downloader's aiohttp session must be created inside the loop that
            # uses it, so it is built here rather than outside. The session belongs
            # to the remote's factory, so close it to not leak sockets per request.
            downloader = remote.get_downloader(url=url)
            try:
                return await downloader.run()
            finally:
                if session := getattr(downloader, "session", None):
                    await session.close()

        # content_handler runs via sync_to_async, i.e. in a worker thread with no
        # event loop, so the downloader's own blocking fetch() cannot be used.
        result = None
        try:
            result = asyncio.run(download())
            with open(result.path, encoding="utf-8") as fd:
                data = json.load(fd)
        except Exception:
            logger.exception("Failed to read npm metadata for '%s' from '%s'", name, url)
            return None
        finally:
            # The packument was downloaded to a temporary file; only the parsed JSON
            # is needed, and packuments are mutable so they are not cached.
            if result and result.path:
                with suppress(OSError):
                    os.unlink(result.path)

        prefix_url = self._tarball_url_prefix()
        for version_data in data.get("versions", {}).values():
            tarball = version_data.get("dist", {}).get("tarball")
            if not tarball:
                continue
            filename = tarball.split("/")[-1]
            version_data["dist"]["tarball"] = f"{prefix_url}{name}/-/{filename}"

        return Response(body=json.dumps(data), content_type="application/json")
