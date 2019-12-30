import logging
from gettext import gettext as _

from pulpcore.plugin.models import (
    ContentArtifact,
    RepositoryVersion,
    PublishedArtifact,
    PublishedMetadata,
    RemoteArtifact,
)
from pulpcore.plugin.tasking import WorkingDirectory
from pulp_npm.app.models import NpmPublication


log = logging.getLogger(__name__)


def publish(repository_version_pk):
    """
    Use provided publisher to create a Publication based on a RepositoryVersion.

    Args:
        repository_version_pk (str): Create a publication from this repository version.
    """
    repository_version = RepositoryVersion.objects.get(pk=repository_version_pk)

    log.info(_('Publishing: repository={repo}, version={version}').format(
        repo=repository_version.repository.name,
        version=repository_version.number,
    ))

    with WorkingDirectory():
        with NpmPublication.create(repository_version) as publication:
            # Write any Artifacts (files) to the file system, and the database.

            content = publication.repository_version.content
            published_artifacts = []
            for content_artifact in ContentArtifact.objects.filter(content__in=content).iterator():
                published_artifacts.append(PublishedArtifact(
                    relative_path=content_artifact.relative_path,
                    publication=publication,
                    content_artifact=content_artifact)
                )

            PublishedArtifact.objects.bulk_create(published_artifacts, batch_size=2000)

            # Write any metadata files to the file system, and the database.
            #
            # metadata = YourMetadataWriter.write(relative_path)
            # metadata = PublishedMetadata(
            #     relative_path=os.path.basename(manifest.relative_path),
            #     publication=publication,
            #     file=File(open(manifest.relative_path, "rb")))
            # metadata.save()

    log.info(_("Publication: {publication} created").format(publication=publication.pk))
