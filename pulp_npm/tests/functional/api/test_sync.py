# coding=utf-8
"""Tests that sync npm plugin repositories."""
import pytest

from pulpcore.client.pulp_npm import RepositorySyncURL

from pulpcore.tests.functional.utils import PulpTaskError

from pulp_npm.tests.functional.constants import (
    NPM_INVALID_FIXTURE_URL,
)


@pytest.mark.parallel
def test_sync_endpoint_demanding_remote_payload(
    npm_bindings, npm_remote_factory, npm_repository_factory, monitor_task
):
    remote = npm_remote_factory(url="https://registry.npmjs.org/commander/4.0.1")
    repository = npm_repository_factory(remote=remote.pulp_href)

    versions = npm_bindings.RepositoriesNpmVersionsApi.list(repository.pulp_href)
    assert versions.count == 1

    monitor_task(npm_bindings.RepositoriesNpmApi.sync(repository.pulp_href, {}).task)

    new_versions = npm_bindings.RepositoriesNpmVersionsApi.list(repository.pulp_href)
    assert new_versions.count > 1


@pytest.mark.parallel
def test_sync_invalid_url(npm_bindings, npm_remote_factory, npm_repository_factory, monitor_task):
    """Sync a repository using a remote url that does not exist.

    Test that we get a task failure.
    """
    remote = npm_remote_factory(url="http://npminvalid")
    repository = npm_repository_factory(remote=remote.pulp_href)

    sync_payload = RepositorySyncURL(remote=remote.pulp_href)
    with pytest.raises(PulpTaskError) as exp:
        monitor_task(npm_bindings.RepositoriesNpmApi.sync(repository.pulp_href, sync_payload).task)

    assert exp.value.task.state == "failed"
    assert "Cannot connect to host npminvalid:80" in exp.value.task.error["description"]


@pytest.mark.skip(reason="Needs npm-invalid fixture on fixtures.pulpproject.org")
@pytest.mark.parallel
def test_invalid_npm_content(
    npm_bindings, npm_remote_factory, npm_repository_factory, monitor_task
):
    """Sync a repository using an invalid plugin_content repository.

    Assert that an exception is raised, and that error message has
    keywords related to the reason of the failure.
    """
    remote = npm_remote_factory(url=NPM_INVALID_FIXTURE_URL)
    repository = npm_repository_factory(remote=remote.pulp_href)

    sync_payload = RepositorySyncURL(remote=remote.pulp_href)
    with pytest.raises(PulpTaskError) as exp:
        monitor_task(npm_bindings.RepositoriesNpmApi.sync(repository.pulp_href, sync_payload).task)

    assert exp.value.task.state == "failed"
    assert "mismatched" in exp.value.task.error["description"]
    assert "empty" in exp.value.task.error["description"]
