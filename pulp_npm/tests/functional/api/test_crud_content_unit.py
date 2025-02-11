# coding=utf-8
"""Tests that perform actions over content unit."""
import pytest
import uuid


@pytest.mark.parallel
def test_repository_creation_with_remote(npm_bindings):
    remote = npm_bindings.RemotesNpmApi.create({"name": str(uuid.uuid4()), "url": "http://npm"})
    repository = npm_bindings.RepositoriesNpmApi.create(
        {"name": str(uuid.uuid4()), "remote": remote.pulp_href}
    )

    assert repository.remote == remote.pulp_href
