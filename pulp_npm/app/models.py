import json
from logging import getLogger

from aiohttp.web_response import Response
from django.conf import settings
from django.db import models


from pulpcore.plugin.models import (
    Content,
    Remote,
    Repository,
    Distribution,
)

from pulpcore.plugin.util import get_domain_pk
from .utils import urlpath_sanitize, extract_package_info

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
    version = models.CharField(max_length=16)
    _pulp_domain = models.ForeignKey("core.Domain", default=get_domain_pk, on_delete=models.PROTECT)

    @property
    def relative_path(self):
        """
        Returns relative_path.
        """
        return f"{self.name}/-/{self.name}-{self.version}.tgz"

    @staticmethod
    def init_from_artifact_and_relative_path(artifact, relative_path):
        name, version = extract_package_info(relative_path)

        return Package(name=name, version=version)

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = ("name", "version", "_pulp_domain")


class NpmRemote(Remote):
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


class NpmRepository(Repository):
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


class NpmDistribution(Distribution):
    """
    Distribution for "npm" content.
    """

    TYPE = "npm"

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"

    def content_handler(self, path):
        data = {}

        if not self.repository:
            return None

        repository_version = self.repository_version
        if not repository_version:
            repository_version = self.repository.latest_version()

        content = repository_version.content
        packages = Package.objects.filter(name=path, pk__in=content)

        if not packages:
            return None

        data["name"] = path
        data["versions"] = {}
        versions = []

        if settings.DOMAIN_ENABLED:
            prefix_url = "{}/".format(
                urlpath_sanitize(
                    settings.CONTENT_ORIGIN,
                    settings.CONTENT_PATH_PREFIX,
                    self.pulp_domain.name,
                    self.base_path,
                )
            )
        else:
            prefix_url = "{}/".format(
                urlpath_sanitize(
                    settings.CONTENT_ORIGIN,
                    settings.CONTENT_PATH_PREFIX,
                    self.base_path,
                )
            )

        for package in packages:
            tarball_url = f"{prefix_url}{package.relative_path.split('/')[-1]}"

            version = {
                package.version: {
                    "_id": f"{package.name}@{package.version}",
                    "dist": {"tarball": tarball_url},
                }
            }
            versions.append(package.version)
            data["versions"].update(version)

        data["dist-tags"] = {"latest": max(versions)}

        serialized_data = json.dumps(data)
        return Response(body=serialized_data)
