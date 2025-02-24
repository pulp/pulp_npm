from gettext import gettext as _
import json
import logging

from collections import OrderedDict
from packaging.version import parse, InvalidVersion
from urllib.parse import urlparse

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
    return DeclarativeVersion(first_stage, repository, mirror=mirror).create()


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
        data = self.get_json_data(result.path)

        def parse_package_version(version):
            try:
                return parse(version)
            except InvalidVersion:
                return None

        async def extract_package_dependencies(package, previous_packages=None):
            if previous_packages is None:
                previous_packages = set()

            package_id = f"{package['name']}-{package['version']}"

            if package_id in previous_packages:
                return []

            previous_packages.add(package_id)

            flat_dependencies = []
            if dependencies := package.get("dependencies"):
                for name, version in dependencies.items():
                    url = self.remote.url
                    url_parsed = urlparse(url)
                    registry_url = f"{url_parsed.scheme}://{url_parsed.netloc}"
                    if name not in url_parsed.path:
                        version_normalized = version.replace("^", "")
                        package_url = f"{registry_url}/{name}/{version_normalized}"

                    downloader = self.remote.get_downloader(url=package_url)
                    result = await downloader.run()
                    metadata = self.get_json_data(result.path)
                    flat_dependencies.append(metadata)
                    flat_dependencies.extend(
                        await extract_package_dependencies(metadata, previous_packages)
                    )

            return flat_dependencies

        if versions := data.get("versions"):
            packages = []
            latest_version = parse(data["dist-tags"]["latest"])
            MAX_VERSIONS = 15
            # The packaging.parse module have some difficulties with some versions.
            versions = {
                version: parse_package_version(version)
                for version in versions.keys()
                if parse_package_version(version) is not None
            }
            # Could be there packages with higher versions than the latest stable one.
            versions = {
                version: parsed_version
                for version, parsed_version in versions.items()
                if parsed_version <= latest_version
            }
            versions = OrderedDict(
                sorted(versions.items(), key=lambda version: version[1], reverse=True)
            )

            versions_to_download = OrderedDict(list(versions.items())[:MAX_VERSIONS])
            for version in versions_to_download.keys():
                packages.append(data["versions"][str(version)])

            dependencies = []
            for package in packages:
                dependencies.extend(await extract_package_dependencies(package))

            packages.extend(dependencies)
        else:
            packages = [data]

        for pkg in packages:
            package = Package(name=pkg["name"], version=pkg["version"])
            artifact = Artifact()  # make Artifact in memory-only
            url = pkg["dist"]["tarball"]
            da = DeclarativeArtifact(
                artifact=artifact,
                url=url,
                relative_path=url.split("/")[-1],
                remote=self.remote,
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
