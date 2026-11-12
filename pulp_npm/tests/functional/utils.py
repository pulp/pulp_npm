# coding=utf-8
"""Utilities for tests for the npm plugin."""

import asyncio
import base64
import io
import json
import os
import tarfile

import aiohttp


def gen_npm_content_attrs(artifact):
    """Generate a dict with content unit attributes.

    :param artifact: A dict of info about the artifact.
    :returns: A semi-random dict for use in creating a content unit.
    """
    # FIXME: Add content specific metadata here.
    return {"_artifact": artifact["pulp_href"]}


def pulp_base_url():
    """Base URL of the Pulp instance under test."""
    protocol = os.environ.get("API_PROTOCOL", "https")
    host = os.environ.get("API_HOST", "pulp")
    port = os.environ.get("API_PORT", "443")
    return f"{protocol}://{host}:{port}"


def pulp_auth():
    """Admin credentials for the Pulp instance under test."""
    return aiohttp.BasicAuth(
        os.environ.get("ADMIN_USERNAME", "admin"),
        os.environ.get("ADMIN_PASSWORD", "password"),
    )


def build_npm_tgz(name="test-pkg", version="1.0.0"):
    """Build a minimal npm tarball containing only ``package/package.json``."""
    package_json = json.dumps({"name": name, "version": version}).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(package_json)
        tar.addfile(info, io.BytesIO(package_json))
    buf.seek(0)
    return buf.read()


def build_publish_body(name, version, tgz_bytes):
    """Build the body of an ``npm publish`` request for a single version."""
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


def npm_publish_url(base_path, package_name, domain=None):
    """URL an ``npm publish`` request is sent to, with the scope separator escaped."""
    escaped = package_name.replace("/", "%2F")
    if domain:
        return f"{pulp_base_url()}/npm/{domain}/{base_path}/{escaped}"
    return f"{pulp_base_url()}/npm/{base_path}/{escaped}"


async def _put_publish(url, body, auth=None):
    async with aiohttp.ClientSession(auth=auth or pulp_auth()) as session:
        async with session.put(url, json=body, ssl=False) as resp:
            text = await resp.text()
            return resp.status, text


def publish_npm_versions(base_path, pkg_name, versions, domain=None):
    """Publish each of ``versions`` of ``pkg_name`` into the distribution's repository."""
    for ver in versions:
        tgz = build_npm_tgz(name=pkg_name, version=ver)
        body = build_publish_body(pkg_name, ver, tgz)
        url = npm_publish_url(base_path, pkg_name, domain=domain)
        status, text = asyncio.run(_put_publish(url, body))
        assert status == 201, f"Publish {ver} failed ({status}): {text}"


def http_get_with_headers(url):
    """Like the ``http_get`` fixture, but returns ``(body, headers)``."""

    async def _send_request():
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(url, ssl=False) as response:
                return await response.content.read(), dict(response.headers)

    return asyncio.run(_send_request())
