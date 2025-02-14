# coding=utf-8
"""Tests that CRUD npm remotes."""
from random import choice
import pytest
import uuid

from pulpcore.client.pulp_npm.exceptions import ApiException


ON_DEMAND_DOWNLOAD_POLICIES = ("on_demand", "streamed")


@pytest.mark.parallel
def test_create_remote(npm_bindings, gen_object_with_cleanup):
    """Create a remote."""
    body = {
        "name": str(uuid.uuid4()),
        "url": "http://something",
        "policy": choice(ON_DEMAND_DOWNLOAD_POLICIES),
    }
    remote = gen_object_with_cleanup(npm_bindings.RemotesNpmApi, body)

    for key, val in body.items():
        assert getattr(remote, key) == body[key]


@pytest.mark.parallel
def test_retrieve_remote_by_pulp_href(npm_remote_factory, npm_bindings):
    """Read a remote by its href."""

    remote = npm_remote_factory()
    remote_retrieved = npm_bindings.RemotesNpmApi.read(remote.pulp_href)

    for key, val in remote.to_dict().items():
        assert getattr(remote, key) == getattr(remote_retrieved, key)


@pytest.mark.parallel
def test_retrieve_remote_by_name(npm_remote_factory, npm_bindings):
    """Read a remote by its href."""

    remote = npm_remote_factory()
    remote_search = npm_bindings.RemotesNpmApi.list(name=remote.name)

    assert remote_search.count == 1
    remote_retrieved = remote_search.results[0]

    for key, val in remote.to_dict().items():
        assert getattr(remote, key) == getattr(remote_retrieved, key)


@pytest.mark.parallel
def test_partially_update_remote(npm_remote_factory, npm_bindings):
    """Update a remote using HTTP PATCH."""
    remote = npm_remote_factory()
    body = {"policy": choice(ON_DEMAND_DOWNLOAD_POLICIES)}

    npm_bindings.RemotesNpmApi.partial_update(remote.pulp_href, body)

    updated_remote = npm_bindings.RemotesNpmApi.read(remote.pulp_href)

    assert updated_remote.pulp_href == remote.pulp_href

    for key, val in body.items():
        assert getattr(updated_remote, key) == body[key]


@pytest.mark.parallel
def test_delete_remote(npm_remote_factory, npm_bindings):
    """Delete a remote."""
    remote = npm_remote_factory()

    npm_bindings.RemotesNpmApi.delete(remote.pulp_href)

    with pytest.raises(ApiException) as exp:
        npm_bindings.RemotesNpmApi.read(remote.pulp_href)

    assert exp.value.status == 404


@pytest.mark.parallel
def test_default_remote_policy(npm_remote_factory, npm_bindings):
    """Verify the default policy `immediate`.

    When no policy is defined, the default policy of `immediate`
    is applied.
    """
    remote = npm_remote_factory()
    body = {
        "name": str(uuid.uuid4()),
        "url": "http://something",
        "policy": choice(ON_DEMAND_DOWNLOAD_POLICIES),
    }
    del body["policy"]

    npm_bindings.RemotesNpmApi.update(remote.pulp_href, body)

    updated_remote = npm_bindings.RemotesNpmApi.read(remote.pulp_href)

    assert updated_remote.policy == "immediate"


@pytest.mark.parallel
def test_change_remote_policy(npm_remote_factory, npm_bindings):
    """Verify ability to change policy to value other than the default.

    Update the remote policy to a valid value other than `immediate`
    and verify the new set value.
    """
    changed_policy = choice([item for item in ON_DEMAND_DOWNLOAD_POLICIES if item != "immediate"])

    remote = npm_remote_factory()

    npm_bindings.RemotesNpmApi.partial_update(remote.pulp_href, {"policy": changed_policy})

    updated_remote = npm_bindings.RemotesNpmApi.read(remote.pulp_href)

    assert updated_remote.policy == changed_policy


@pytest.mark.parallel
def test_invalid_remote_policy(npm_remote_factory, npm_bindings):
    """Verify an invalid policy does not update the remote policy.

    Get the current remote policy.
    Attempt to update the remote policy to an invalid value.
    Verify the policy remains the same.
    """
    remote = npm_remote_factory()
    with pytest.raises(Exception):
        npm_bindings.RemotesNpmApi.partial_update(remote.pulp_href, {"policy": str(uuid.uuid4())})

    remote = npm_bindings.RemotesNpmApi.read(remote.pulp_href)
    assert remote.policy == "immediate"
