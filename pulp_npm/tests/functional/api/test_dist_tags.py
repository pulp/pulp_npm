"""Tests that verify dist-tags.latest is resolved using semver, not lexicographic order."""

import json
import uuid
from urllib.parse import urljoin

import pytest

from pulp_npm.tests.functional.utils import publish_npm_versions


@pytest.mark.parallel
def test_dist_tags_latest_is_highest_semver(
    npm_bindings,
    npm_repository_factory,
    npm_distribution_factory,
    pulp_settings,
    http_get,
):
    """dist-tags.latest must use semver ordering, not lexicographic.

    Lexicographic sort would pick "9.0.0" over "10.0.0".
    """
    domain = "default" if pulp_settings.DOMAIN_ENABLED else None
    repo = npm_repository_factory()
    distro = npm_distribution_factory(repository=repo.pulp_href)

    pkg_name = f"semver-order-{uuid.uuid4().hex[:8]}"
    publish_npm_versions(distro.base_path, pkg_name, ["1.0.0", "9.0.0", "10.0.0"], domain=domain)

    content_metadata = json.loads(http_get(urljoin(distro.base_url, pkg_name)))
    assert content_metadata["dist-tags"]["latest"] == "10.0.0"


@pytest.mark.parallel
def test_dist_tags_latest_excludes_prerelease(
    npm_bindings,
    npm_repository_factory,
    npm_distribution_factory,
    pulp_settings,
    http_get,
):
    """dist-tags.latest must exclude pre-release versions when stable versions exist."""
    domain = "default" if pulp_settings.DOMAIN_ENABLED else None
    repo = npm_repository_factory()
    distro = npm_distribution_factory(repository=repo.pulp_href)

    pkg_name = f"no-prerelease-{uuid.uuid4().hex[:8]}"
    publish_npm_versions(
        distro.base_path, pkg_name, ["1.0.0", "2.0.0", "3.0.0-alpha.1"], domain=domain
    )

    content_metadata = json.loads(http_get(urljoin(distro.base_url, pkg_name)))
    assert content_metadata["dist-tags"]["latest"] == "2.0.0"


@pytest.mark.parallel
def test_dist_tags_latest_falls_back_to_prerelease(
    npm_bindings,
    npm_repository_factory,
    npm_distribution_factory,
    pulp_settings,
    http_get,
):
    """When only pre-release versions exist, dist-tags.latest should fall back to the highest."""
    domain = "default" if pulp_settings.DOMAIN_ENABLED else None
    repo = npm_repository_factory()
    distro = npm_distribution_factory(repository=repo.pulp_href)

    pkg_name = f"only-pre-{uuid.uuid4().hex[:8]}"
    publish_npm_versions(distro.base_path, pkg_name, ["1.0.0-beta.1"], domain=domain)

    content_metadata = json.loads(http_get(urljoin(distro.base_url, pkg_name)))
    assert content_metadata["dist-tags"]["latest"] == "1.0.0-beta.1"
