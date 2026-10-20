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
    Distribution,
    Remote,
    Repository,
)
from pulpcore.plugin.util import get_domain_pk

from .utils import extract_package_info, urlpath_sanitize

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

        return Package(name=name, version=version)

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

        local = self._packument_from_local_packages(name, packages) if packages else None

        # With a remote attached, fetch the upstream packument ourselves and rewrite its
        # tarball URLs, rather than returning None and letting pulpcore proxy that same
        # remote with unmodified URLs. It is fetched even when local packages exist:
        # pull-through adds packages to the repository one version at a time, so local
        # content is usually a small part of what upstream lists.
        upstream = self._packument_from_remote(name) if self.remote else None

        if local and upstream:
            data = self._merge_packuments(local, upstream)
        else:
            # Either side alone; local only also covers an unreachable remote, so
            # versions already held here stay installable while upstream is down.
            data = local or upstream
        if data is None:
            return None
        return Response(body=json.dumps(data), content_type="application/json")

    @staticmethod
    def _merge_packuments(local, upstream):
        """Upstream's packument, plus the versions held only in this repository.

        Upstream's entry is kept for every version it lists, including ones already
        pulled through: it carries the full manifest and the integrity of the published
        tarball, which is the tarball Pulp cached. Versions held only locally are added
        so they stay installable, but they do not move a dist-tag; tags belong to the
        upstream publisher.
        """
        merged = dict(upstream)
        versions = dict(upstream.get("versions", {}))
        for version, entry in local["versions"].items():
            versions.setdefault(version, entry)
        merged["versions"] = versions
        if not merged.get("dist-tags"):
            merged["dist-tags"] = local["dist-tags"]
        return merged

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

        for package in packages:
            tarball_url = f"{prefix_url}{package.name}/-/{package.relative_path.split('/')[-1]}"

            version = {
                package.version: {
                    "name": package.name,
                    "version": package.version,
                    "_id": f"{package.name}@{package.version}",
                    "dist": {"tarball": tarball_url},
                }
            }
            versions.append(package.version)
            data["versions"].update(version)

        parsed = {v: semver.Version.parse(v) for v in versions if semver.Version.is_valid(v)}
        stable_versions = [v for v, parsed_v in parsed.items() if not parsed_v.prerelease]
        latest = (
            max(stable_versions, key=parsed.get) if stable_versions else max(parsed, key=parsed.get)
        )
        data["dist-tags"] = {"latest": latest}

        return data

    def _packument_from_remote(self, name):
        """Fetch the upstream packument and rewrite dist.tarball to point at Pulp.

        Returns None if the remote does not have the package or cannot be reached.
        """
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

        return data
