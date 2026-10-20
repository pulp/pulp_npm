import json
import time
import uuid

import pytest
from aiohttp.client_exceptions import ClientResponseError

from pulp_npm.tests.functional.constants import NPM_FIXTURE_URL
from pulp_npm.tests.functional.utils import http_get_with_headers, publish_npm_versions


def test_pull_through_install(
    npm_bindings, npm_remote_factory, npm_distribution_factory, http_get, delete_orphans_pre
):
    """Test that a pull-through distro can be installed from."""
    remote = npm_remote_factory(url=NPM_FIXTURE_URL)
    distro = npm_distribution_factory(remote=remote.pulp_href)
    PACKAGE = "react"

    package_metadata = json.loads(http_get(f"{distro.base_url}{PACKAGE}"))
    assert package_metadata["name"] == PACKAGE

    latest_package_version = package_metadata["dist-tags"]["latest"]
    latest_package_metadata = package_metadata["versions"][latest_package_version]
    tarball_url = latest_package_metadata["dist"]["tarball"]

    # The tarball URL should resolve through Pulp, not the upstream remote.
    assert tarball_url.startswith(distro.base_url)
    assert not tarball_url.startswith(NPM_FIXTURE_URL)
    package_filename = tarball_url.removeprefix(distro.base_url)

    package_download = http_get(f"{distro.base_url}{package_filename}")

    assert len(package_download) > 100

    content = npm_bindings.ContentPackagesApi.list(name=PACKAGE)
    assert content.count == 1


def test_pull_through_install_scoped_package(
    npm_bindings, npm_remote_factory, npm_distribution_factory, http_get, delete_orphans_pre
):
    """Test that a scoped package can be installed from a pull-through distro.

    The scope separator is a slash in both the packument path and the rewritten
    tarball URL, so this exercises the parts of the path handling that a flat
    package name cannot.
    """
    remote = npm_remote_factory(url=NPM_FIXTURE_URL)
    distro = npm_distribution_factory(remote=remote.pulp_href)
    PACKAGE = "@babel/code-frame"

    package_metadata = json.loads(http_get(f"{distro.base_url}{PACKAGE}"))
    assert package_metadata["name"] == PACKAGE

    latest_package_version = package_metadata["dist-tags"]["latest"]
    latest_package_metadata = package_metadata["versions"][latest_package_version]
    tarball_url = latest_package_metadata["dist"]["tarball"]

    assert tarball_url.startswith(distro.base_url)
    assert not tarball_url.startswith(NPM_FIXTURE_URL)

    # The scope must survive the rewrite: "@babel/code-frame/-/code-frame-<version>.tgz".
    relative_path = tarball_url.removeprefix(distro.base_url)
    assert relative_path == f"{PACKAGE}/-/code-frame-{latest_package_version}.tgz"

    package_download = http_get(tarball_url)

    assert len(package_download) > 100

    content = npm_bindings.ContentPackagesApi.list(name=PACKAGE)
    assert content.count == 1
    assert content.results[0].version == latest_package_version


@pytest.mark.parallel
@pytest.mark.parametrize("scope", ["", "@pulp-npm-test/"], ids=["unscoped", "scoped"])
def test_packument_from_local_packages(
    npm_repository_factory, npm_distribution_factory, pulp_settings, http_get, scope
):
    """A distribution backed by a repository serves a packument built from its content."""
    domain = "default" if pulp_settings.DOMAIN_ENABLED else None
    repo = npm_repository_factory()
    distro = npm_distribution_factory(repository=repo.pulp_href)

    pkg_name = f"{scope}local-packument-{uuid.uuid4().hex[:8]}"
    base_name = pkg_name.split("/")[-1]
    publish_npm_versions(distro.base_path, pkg_name, ["1.0.0", "1.1.0"], domain=domain)

    body, headers = http_get_with_headers(f"{distro.base_url}{pkg_name}")
    assert headers["Content-Type"].startswith("application/json")

    packument = json.loads(body)
    assert packument["name"] == pkg_name
    assert set(packument["versions"]) == {"1.0.0", "1.1.0"}
    assert packument["dist-tags"]["latest"] == "1.1.0"

    for version, version_metadata in packument["versions"].items():
        assert version_metadata["name"] == pkg_name
        assert version_metadata["_id"] == f"{pkg_name}@{version}"
        tarball_url = version_metadata["dist"]["tarball"]
        assert tarball_url == f"{distro.base_url}{pkg_name}/-/{base_name}-{version}.tgz"
        assert len(http_get(tarball_url)) > 0


def test_pull_through_with_repository_keeps_upstream_listing(
    npm_bindings,
    npm_remote_factory,
    npm_repository_factory,
    npm_distribution_factory,
    http_get,
    delete_orphans_pre,
):
    """A distro with both a repository and a remote keeps listing every upstream version.

    Pulling a tarball through adds that one version to the repository. The packument
    must still list everything upstream has, or every version not cached yet would
    stop being installable through this distribution.
    """
    remote = npm_remote_factory(url=NPM_FIXTURE_URL)
    repo = npm_repository_factory()
    distro = npm_distribution_factory(repository=repo.pulp_href, remote=remote.pulp_href)
    PACKAGE = "commander"

    before = json.loads(http_get(f"{distro.base_url}{PACKAGE}"))
    assert before["name"] == PACKAGE
    assert len(before["versions"]) > 1

    version = before["dist-tags"]["latest"]
    tarball_url = before["versions"][version]["dist"]["tarball"]
    assert tarball_url.startswith(distro.base_url)

    assert len(http_get(tarball_url)) > 100

    _wait_for_cached_version(npm_bindings, repo, PACKAGE, version)

    after = json.loads(http_get(f"{distro.base_url}{PACKAGE}"))
    assert set(after["versions"]) >= set(before["versions"])
    assert after["dist-tags"]["latest"] == before["dist-tags"]["latest"]
    # The cached version keeps upstream's entry: same tarball URL, same integrity.
    assert after["versions"][version]["dist"]["tarball"] == tarball_url
    assert after["versions"][version]["dist"].get("integrity") == before["versions"][version][
        "dist"
    ].get("integrity")


def _wait_for_cached_version(npm_bindings, repo, package, version, timeout=60):
    """Wait until pull-through has added ``package@version`` to the repository.

    Adding the pulled-through package is dispatched as a task, so it is not
    necessarily visible on the request right after the download.
    """
    deadline = time.monotonic() + timeout
    while True:
        latest = npm_bindings.RepositoriesNpmApi.read(repo.pulp_href).latest_version_href
        cached = npm_bindings.ContentPackagesApi.list(name=package, repository_version=latest)
        if any(package_unit.version == version for package_unit in cached.results):
            return
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"'{package}@{version}' was not added to the repository within {timeout}s"
            )
        time.sleep(1)


@pytest.mark.parallel
def test_packument_lists_local_only_versions_next_to_upstream(
    npm_remote_factory, npm_repository_factory, npm_distribution_factory, pulp_settings, http_get
):
    """A version held only in the repository is listed with upstream's, without moving a tag."""
    domain = "default" if pulp_settings.DOMAIN_ENABLED else None
    remote = npm_remote_factory(url=NPM_FIXTURE_URL)
    repo = npm_repository_factory()
    distro = npm_distribution_factory(repository=repo.pulp_href, remote=remote.pulp_href)
    PACKAGE = "commander"
    local_version = f"0.0.0-local.{uuid.uuid4().hex[:8]}"
    publish_npm_versions(distro.base_path, PACKAGE, [local_version], domain=domain)

    packument = json.loads(http_get(f"{distro.base_url}{PACKAGE}"))

    assert local_version in packument["versions"]
    assert len(packument["versions"]) > 1
    assert packument["dist-tags"]["latest"] != local_version
    tarball_url = packument["versions"][local_version]["dist"]["tarball"]
    assert tarball_url.startswith(distro.base_url)
    assert len(http_get(tarball_url)) > 0


@pytest.mark.parallel
def test_packument_served_from_local_content_when_remote_unreachable(
    npm_remote_factory, npm_repository_factory, npm_distribution_factory, pulp_settings, http_get
):
    """Versions held in the repository stay installable while the remote is down."""
    domain = "default" if pulp_settings.DOMAIN_ENABLED else None
    remote = npm_remote_factory(url="http://npm-unreachable-fixture/")
    repo = npm_repository_factory()
    distro = npm_distribution_factory(repository=repo.pulp_href, remote=remote.pulp_href)
    pkg_name = f"local-while-remote-down-{uuid.uuid4().hex[:8]}"
    publish_npm_versions(distro.base_path, pkg_name, ["1.0.0"], domain=domain)

    packument = json.loads(http_get(f"{distro.base_url}{pkg_name}"))

    assert set(packument["versions"]) == {"1.0.0"}
    assert packument["dist-tags"]["latest"] == "1.0.0"


@pytest.mark.parallel
def test_pull_through_packument_missing_upstream(
    npm_remote_factory, npm_distribution_factory, http_get
):
    """A packument the remote does not have results in a 404, not a server error."""
    remote = npm_remote_factory(url=NPM_FIXTURE_URL)
    distro = npm_distribution_factory(remote=remote.pulp_href)

    with pytest.raises(ClientResponseError) as exp:
        http_get(f"{distro.base_url}pulp-npm-nonexistent-{uuid.uuid4().hex}")

    assert exp.value.status == 404


@pytest.mark.parallel
def test_pull_through_packument_unreachable_remote(
    npm_remote_factory, npm_distribution_factory, http_get
):
    """An unreachable remote fails the request instead of raising out of the handler."""
    remote = npm_remote_factory(url="http://npm-unreachable-fixture/")
    distro = npm_distribution_factory(remote=remote.pulp_href)

    with pytest.raises(ClientResponseError) as exp:
        http_get(f"{distro.base_url}react")

    assert exp.value.status >= 400
