from pulpcore.plugin.importexport import BaseContentResource
from pulpcore.plugin.modelresources import RepositoryResource
from pulpcore.plugin.util import get_domain

from pulp_npm.app.models import NpmRepository, Package


class PackageResource(BaseContentResource):
    """
    Resource for import/export of npm_package entities.
    """

    def set_up_queryset(self):
        """
        :return: Packages specific to a specified repo-version.
        """
        return Package.objects.filter(pk__in=self.repo_version.content, _pulp_domain=get_domain())

    class Meta:
        model = Package
        import_id_fields = model.natural_key_fields()


class NpmRepositoryResource(RepositoryResource):
    """
    A resource for importing/exporting npm repository entities.
    """

    def set_up_queryset(self):
        """
        :return: A queryset containing one repository that will be exported.
        """
        return NpmRepository.objects.filter(pk=self.repo_version.repository)

    class Meta:
        model = NpmRepository


IMPORT_ORDER = [PackageResource, NpmRepositoryResource]
