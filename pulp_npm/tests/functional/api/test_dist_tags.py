"""Tests that verify dist-tags.latest is resolved using semver, not lexicographic order."""

import asyncio
import base64
import io
import json
import os
import tarfile
import uuid
from urllib.parse import urljoin

import aiohttp
import pytest


def _pulp_base_url():
    protocol = os.environ.get("API_PROTOCOL", "https")
    host = os.environ.get("API_HOST", "pulp")
    port = os.environ.get("API_PORT", "443")
    return f"{protocol}://{host}:{port}"


def _pulp_auth():
    return aiohttp.BasicAuth(
        os.environ.get("ADMIN_USERNAME", "admin"),
        os.environ.get("ADMIN_PASSWORD", "password"),
    )


def _build_npm_tgz(name="test-pkg", version="1.0.0"):
    package_json = json.dumps({"name": name, "version": version}).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(package_json)
        tar.addfile(info, io.BytesIO(package_json))
    buf.seek(0)
    return buf.read()


def _build_publish_body(name, version, tgz_bytes):
    base_name = name.split("/")[-1] if "/" in name else name
    tarball_filename = f"{base_name}-{version}.tgz"
    return {
        "_id": name,
        "name": name,
        "dist-tags": {"latest": version},
        "versions": {
            version: {
                "name": name,
                "version": version,
                "dist": {"tarball": f"{name}/-/{tarball_filename}"},
            }
        },
        "_attachments": {
            tarball_filename: {
                "content_type": "application/octet-stream",
                "data": base64.b64encode(tgz_bytes).decode(),
                "length": len(tgz_bytes),
            }
        },
    }


def _npm_publish_url(base_path, package_name, domain=None):
    escaped = package_name.replace("/", "%2F")
    if domain:
        return f"{_pulp_base_url()}/npm/{domain}/{base_path}/{escaped}"
    return f"{_pulp_base_url()}/npm/{base_path}/{escaped}"


def _run(coro):
    return asyncio.run(coro)


async def _put_publish(url, body, auth=None):
    async with aiohttp.ClientSession(auth=auth or _pulp_auth()) as session:
        async with session.put(url, json=body, ssl=False) as resp:
            text = await resp.text()
            return resp.status, text


def _publish_versions(base_path, pkg_name, versions, domain=None):
    for ver in versions:
        tgz = _build_npm_tgz(name=pkg_name, version=ver)
        body = _build_publish_body(pkg_name, ver, tgz)
        url = _npm_publish_url(base_path, pkg_name, domain=domain)
        status, text = _run(_put_publish(url, body))
        assert status == 201, f"Publish {ver} failed ({status}): {text}"


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
    _publish_versions(distro.base_path, pkg_name, ["1.0.0", "9.0.0", "10.0.0"], domain=domain)

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
    _publish_versions(
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
    _publish_versions(distro.base_path, pkg_name, ["1.0.0-beta.1"], domain=domain)

    content_metadata = json.loads(http_get(urljoin(distro.base_url, pkg_name)))
    assert content_metadata["dist-tags"]["latest"] == "1.0.0-beta.1"
