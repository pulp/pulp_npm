from gettext import gettext as _
import json
import logging

from pulpcore.plugin.models import Artifact, Remote, Repository
from pulpcore.plugin.stages import (
    DeclarativeArtifact,
    DeclarativeContent,
    DeclarativeVersion,
    Stage,
)

from pulp_npm.app.models import Package, NpmRemote


log = logging.getLogger(__name__)


def synchronize(remote_pk, repository_pk, mirror=False):
    """
    Sync content from the remote repository.

    Create a new version of the repository that is synchronized with the remote.

    Args:
        remote_pk (str): The remote PK.
        repository_pk (str): The repository PK.
        mirror (bool): True for mirror mode, False for additive.

    Raises:
        ValueError: If the remote does not specify a URL to sync

    """
    remote = NpmRemote.objects.get(pk=remote_pk)
    repository = Repository.objects.get(pk=repository_pk)

    if not remote.url:
        raise ValueError(_("A remote must have a url specified to synchronize."))

    # Interpret policy to download Artifacts or not
    deferred_download = remote.policy != Remote.IMMEDIATE
    first_stage = NpmFirstStage(remote, deferred_download)
    DeclarativeVersion(first_stage, repository, mirror=mirror).create()


class NpmFirstStage(Stage):
    """
    The first stage of a pulp_npm sync pipeline.
    """

    def __init__(self, remote, deferred_download):
        """
        The first stage of a pulp_npm sync pipeline.

        Args:
            remote (FileRemote): The remote data to be used when syncing
            deferred_download (bool): if True the downloading will not happen now. If False, it will
                happen immediately.

        """
        super().__init__()
        self.remote = remote
        self.deferred_download = deferred_download

    async def run(self):
        """
        Build and emit `DeclarativeContent` from the Manifest data.

        Args:
            in_q (asyncio.Queue): Unused because the first stage doesn't read from an input queue.
            out_q (asyncio.Queue): The out_q to send `DeclarativeContent` objects to

        """
        downloader = self.remote.get_downloader(url=self.remote.url)
        result = await downloader.run()
        data = [self.get_json_data(result.path)]
        dependencies = data[0].get("dependencies")
        to_download = []
        if dependencies:
            to_download.extend(dependencies.items())
            downloaded = []
            while to_download:
                next_batch = []
                for name, version in to_download:
                    new_url = self.remote.url.replace(data[0]["name"], name)
                    new_url = new_url.replace(data[0]["version"], version.replace("^", ""))
                    downloader = self.remote.get_downloader(url=new_url)
                    result = await downloader.run()
                    new_data = self.get_json_data(result.path)
                    data.append(new_data)
                    next_batch.extend(new_data.get("dependencies", {}).items())
                    downloaded.append((name, version))

                to_download.extend(next_batch)

                for dependency in downloaded:
                    if dependency in to_download:
                        to_download.remove(dependency)

        for pkg in data:
            package = Package(name=pkg["name"], version=pkg["version"])
            artifact = Artifact()  # make Artifact in memory-only
            url = pkg["dist"]["tarball"]
            da = DeclarativeArtifact(
                artifact,
                url,
                url.split("/")[-1],
                self.remote,
                deferred_download=self.deferred_download,
            )
            dc = DeclarativeContent(content=package, d_artifacts=[da])
            await self.put(dc)

    def get_json_data(self, path):
        """
        Parse the metadata for npm Content type.

        Args:
            path: Path to the metadata file
        """
        with open(path) as fd:
            return json.load(fd)
