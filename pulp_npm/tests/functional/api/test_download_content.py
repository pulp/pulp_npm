# coding=utf-8
"""Tests that verify download of content served by Pulp."""
import hashlib
import pytest
from random import choice
from urllib.parse import urljoin

from aiohttp.client_exceptions import ClientResponseError

from pulpcore.client.pulp_npm import RepositorySyncURL

from pulp_npm.tests.functional.constants import NPM_FIXTURE_URL


@pytest.mark.parallel
def test_download_content(
    npm_bindings,
    npm_remote_factory,
    npm_repository_factory,
    npm_distribution_factory,
    monitor_task,
    get_npm_content_paths,
    http_get,
):
    """
    Verify whether content served by pulp can be downloaded.
    Given a repository, the process is as follows:

    1. Create a publication from the repository. (The latest repository
        version is selected if no version is specified.) A publication is a
        repository version plus metadata.
    2. Create a distribution from the publication. The distribution defines
        at which URLs a publication is available, e.g.
        ``http://example.com/content/foo/`` and
        ``http://example.com/content/bar/``.

    Do the following:

    1. Create, populate, publish, and distribute a repository.
    2. Select a random content unit in the distribution. Download that
        content unit from Pulp, and verify that the content unit has the
        same checksum when fetched directly from Pulp-Fixtures.
    """

    remote = npm_remote_factory(url="https://registry.npmjs.org/commander/4.0.1")
    repository = npm_repository_factory(remote=remote.pulp_href)

    sync_payload = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(npm_bindings.RepositoriesNpmApi.sync(repository.pulp_href, sync_payload).task)

    distribution = npm_distribution_factory(repository=repository.pulp_href)

    # Request the updated repository
    repository = npm_bindings.RepositoriesNpmApi.read(repository.pulp_href)

    unit_path = choice(get_npm_content_paths(repository))

    fixture_hash = hashlib.sha256(http_get(urljoin(NPM_FIXTURE_URL, unit_path))).hexdigest()

    pulp_hash = hashlib.sha256(
        http_get(urljoin(distribution.base_url, unit_path.split("/")[-1]))
    ).hexdigest()

    assert fixture_hash == pulp_hash


@pytest.mark.parallel
def test_wrong_package_name_search(
    npm_bindings,
    npm_remote_factory,
    npm_repository_factory,
    npm_distribution_factory,
    monitor_task,
    http_get,
):
    remote = npm_remote_factory(url="https://registry.npmjs.org/commander/4.0.1")
    repository = npm_repository_factory(remote=remote.pulp_href)

    sync_payload = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(npm_bindings.RepositoriesNpmApi.sync(repository.pulp_href, sync_payload).task)

    distribution = npm_distribution_factory(repository=repository.pulp_href)

    # Request the updated repository
    repository = npm_bindings.RepositoriesNpmApi.read(repository.pulp_href)

    with pytest.raises(ClientResponseError) as exp:
        http_get(urljoin(distribution.base_url, "somewhere/something"))

    assert exp.value.status == 404
