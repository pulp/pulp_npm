# coding=utf-8
"""Tests for Pulp`s download policies."""
import json
import pytest
from urllib.parse import urljoin

from pulpcore.client.pulp_npm import RepositorySyncURL


@pytest.mark.parametrize("policy", ["on_demand", "immediate", "streamed"])
@pytest.mark.parallel
def test_sync(
    policy,
    npm_bindings,
    npm_remote_factory,
    npm_repository_factory,
    npm_distribution_factory,
    monitor_task,
    get_npm_content_paths,
    http_get,
):
    """Sync repositories with the different ``download_policy``.

    Do the following:

    1. Create a repository, and a remote.
    2. Assert that repository version is None.
    3. Sync the remote.
    4. Assert that repository version is not None.
    5. Assert that the correct number of possible units to be downloaded
        were shown.
    6. Try to download content using content metadata
    """
    remote = npm_remote_factory(url="https://registry.npmjs.org/commander/4.0.1", policy=policy)
    repository = npm_repository_factory(remote=remote.pulp_href)
    repository_version = int(repository.latest_version_href.split("/")[-2])
    assert repository_version == 0

    content = get_npm_content_paths(repository)
    assert len(content) == 0

    sync_payload = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(npm_bindings.RepositoriesNpmApi.sync(repository.pulp_href, sync_payload).task)

    first_synced_repository = npm_bindings.RepositoriesNpmApi.read(repository.pulp_href)
    first_synced_repository_version = int(
        first_synced_repository.latest_version_href.split("/")[-2]
    )
    assert first_synced_repository_version == 1

    content = get_npm_content_paths(first_synced_repository)
    assert len(content) == 1

    distribution = npm_distribution_factory(repository=first_synced_repository.pulp_href)
    content_metadata = json.loads(http_get(urljoin(distribution.base_url, "commander")))

    latest_version_available = content_metadata["dist-tags"]["latest"]
    tarball_path = content_metadata["versions"][latest_version_available]["dist"]["tarball"]

    http_get(tarball_path)
