# coding=utf-8
"""Tests for npm package upload (async create and synchronous upload endpoint)."""

import io
import json
import tarfile
import uuid

import pytest

from pulpcore.client.pulp_npm.exceptions import ApiException


def _build_npm_tgz(name="test-pkg", version="1.0.0"):
    """Build a minimal npm .tgz tarball in-memory and return (bytes, name, version)."""
    package_json = json.dumps({"name": name, "version": version}).encode()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(package_json)
        tar.addfile(info, io.BytesIO(package_json))
    buf.seek(0)
    return buf.read(), name, version


def _write_tgz_to_file(tmp_path, tgz_bytes, filename="pkg.tgz"):
    p = tmp_path / filename
    p.write_bytes(tgz_bytes)
    return str(p)


# ---------------------------------------------------------------------------
# Async content create (POST /content/npm/packages/)
# ---------------------------------------------------------------------------


@pytest.mark.parallel
def test_create_content_from_file(npm_bindings, monitor_task, tmp_path):
    """Upload a .tgz via the async create endpoint with a file argument."""
    tgz_bytes, name, version = _build_npm_tgz(
        name=f"@test-scope/create-file-{uuid.uuid4().hex[:8]}", version="2.0.0"
    )
    tgz_path = _write_tgz_to_file(tmp_path, tgz_bytes)

    response = npm_bindings.ContentPackagesApi.create(file=tgz_path)
    task = monitor_task(response.task)
    assert task.state == "completed"
    assert len(task.created_resources) >= 1

    content_href = [r for r in task.created_resources if "content/npm/packages" in r][0]
    content = npm_bindings.ContentPackagesApi.read(content_href)
    assert content.name == name
    assert content.version == version


@pytest.mark.parallel
def test_create_content_with_explicit_name_version(npm_bindings, monitor_task, tmp_path):
    """Provide name and version explicitly, overriding what's in the tarball."""
    tgz_bytes, _, _ = _build_npm_tgz(name="inner-name", version="0.0.1")
    tgz_path = _write_tgz_to_file(tmp_path, tgz_bytes)

    override_name = f"explicit-{uuid.uuid4().hex[:8]}"
    override_version = "9.9.9"
    response = npm_bindings.ContentPackagesApi.create(
        file=tgz_path, name=override_name, version=override_version
    )
    task = monitor_task(response.task)
    assert task.state == "completed"

    content_href = [r for r in task.created_resources if "content/npm/packages" in r][0]
    content = npm_bindings.ContentPackagesApi.read(content_href)
    assert content.name == override_name
    assert content.version == override_version


@pytest.mark.parallel
def test_create_content_into_repository(
    npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """Upload content and associate it with a repository in one call."""
    repo = npm_repository_factory()
    tgz_bytes, name, version = _build_npm_tgz(
        name=f"repo-upload-{uuid.uuid4().hex[:8]}", version="1.0.0"
    )
    tgz_path = _write_tgz_to_file(tmp_path, tgz_bytes)

    response = npm_bindings.ContentPackagesApi.create(file=tgz_path, repository=repo.pulp_href)
    task = monitor_task(response.task)
    assert task.state == "completed"

    repo = npm_bindings.RepositoriesNpmApi.read(repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")

    version_detail = npm_bindings.RepositoriesNpmVersionsApi.read(repo.latest_version_href)
    assert version_detail.content_summary.present["npm.package"]["count"] == 1


@pytest.mark.parallel
def test_create_duplicate_content_is_idempotent(npm_bindings, monitor_task, tmp_path):
    """Uploading the same package twice should return the same content unit."""
    pkg_name = f"dup-{uuid.uuid4().hex[:8]}"
    tgz_bytes, name, version = _build_npm_tgz(name=pkg_name, version="1.0.0")
    path1 = _write_tgz_to_file(tmp_path, tgz_bytes, "pkg1.tgz")
    path2 = _write_tgz_to_file(tmp_path, tgz_bytes, "pkg2.tgz")

    task1 = monitor_task(npm_bindings.ContentPackagesApi.create(file=path1).task)
    task2 = monitor_task(npm_bindings.ContentPackagesApi.create(file=path2).task)

    href1 = [r for r in task1.created_resources if "content/npm/packages" in r][0]
    href2 = [r for r in task2.created_resources if "content/npm/packages" in r][0]
    assert href1 == href2


# ---------------------------------------------------------------------------
# Synchronous upload (POST /content/npm/packages/upload/)
# ---------------------------------------------------------------------------


@pytest.mark.parallel
def test_sync_upload(npm_bindings, tmp_path):
    """Upload a .tgz via the synchronous upload endpoint."""
    tgz_bytes, name, version = _build_npm_tgz(
        name=f"sync-upload-{uuid.uuid4().hex[:8]}", version="3.0.0"
    )
    tgz_path = _write_tgz_to_file(tmp_path, tgz_bytes)

    content = npm_bindings.ContentPackagesApi.upload(file=tgz_path)
    assert content.pulp_href is not None
    assert content.name == name
    assert content.version == version


@pytest.mark.parallel
def test_sync_upload_with_explicit_metadata(npm_bindings, tmp_path):
    """Synchronous upload with name and version provided explicitly."""
    tgz_bytes, _, _ = _build_npm_tgz(name="inner", version="0.1.0")
    tgz_path = _write_tgz_to_file(tmp_path, tgz_bytes)

    override_name = f"sync-explicit-{uuid.uuid4().hex[:8]}"
    content = npm_bindings.ContentPackagesApi.upload(
        file=tgz_path, name=override_name, version="7.7.7"
    )
    assert content.name == override_name
    assert content.version == "7.7.7"


@pytest.mark.parallel
def test_sync_upload_duplicate_is_idempotent(npm_bindings, tmp_path):
    """Uploading the same package twice via sync endpoint returns the same unit."""
    pkg_name = f"sync-dup-{uuid.uuid4().hex[:8]}"
    tgz_bytes, _, _ = _build_npm_tgz(name=pkg_name, version="1.0.0")
    path1 = _write_tgz_to_file(tmp_path, tgz_bytes, "s1.tgz")
    path2 = _write_tgz_to_file(tmp_path, tgz_bytes, "s2.tgz")

    c1 = npm_bindings.ContentPackagesApi.upload(file=path1)
    c2 = npm_bindings.ContentPackagesApi.upload(file=path2)
    assert c1.pulp_href == c2.pulp_href


@pytest.mark.parallel
def test_sync_upload_scoped_package(npm_bindings, tmp_path):
    """Synchronous upload of a scoped npm package (@scope/name)."""
    scope = uuid.uuid4().hex[:6]
    tgz_bytes, name, version = _build_npm_tgz(name=f"@{scope}/my-plugin", version="0.5.0")
    tgz_path = _write_tgz_to_file(tmp_path, tgz_bytes)

    content = npm_bindings.ContentPackagesApi.upload(file=tgz_path)
    assert content.name == f"@{scope}/my-plugin"
    assert content.version == "0.5.0"
    assert content.relative_path == f"@{scope}/my-plugin/-/my-plugin-0.5.0.tgz"


# ---------------------------------------------------------------------------
# Repository content modify after upload
# ---------------------------------------------------------------------------


@pytest.mark.parallel
def test_upload_then_add_to_repository(
    npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """Upload content via sync endpoint, then add it to a repository."""
    repo = npm_repository_factory()
    tgz_bytes, name, version = _build_npm_tgz(
        name=f"add-to-repo-{uuid.uuid4().hex[:8]}", version="1.0.0"
    )
    tgz_path = _write_tgz_to_file(tmp_path, tgz_bytes)

    content = npm_bindings.ContentPackagesApi.upload(file=tgz_path)

    task = monitor_task(
        npm_bindings.RepositoriesNpmApi.modify(
            repo.pulp_href,
            {"add_content_units": [content.pulp_href]},
        ).task
    )
    assert task.state == "completed"

    repo = npm_bindings.RepositoriesNpmApi.read(repo.pulp_href)
    assert repo.latest_version_href.endswith("/versions/1/")


@pytest.mark.parallel
def test_upload_multiple_then_batch_add(
    npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """Upload several packages, then add them all to a repo in one modify call."""
    repo = npm_repository_factory()
    hrefs = []
    for i in range(3):
        tgz_bytes, _, _ = _build_npm_tgz(name=f"batch-{uuid.uuid4().hex[:8]}", version=f"{i}.0.0")
        path = _write_tgz_to_file(tmp_path, tgz_bytes, f"batch-{i}.tgz")
        content = npm_bindings.ContentPackagesApi.upload(file=path)
        hrefs.append(content.pulp_href)

    task = monitor_task(
        npm_bindings.RepositoriesNpmApi.modify(
            repo.pulp_href,
            {"add_content_units": hrefs},
        ).task
    )
    assert task.state == "completed"

    version = npm_bindings.RepositoriesNpmVersionsApi.read(
        npm_bindings.RepositoriesNpmApi.read(repo.pulp_href).latest_version_href
    )
    assert version.content_summary.present["npm.package"]["count"] == 3


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.parallel
def test_sync_upload_without_file_fails(npm_bindings):
    """Calling the sync upload endpoint with no file should fail."""
    with pytest.raises(ApiException) as exc:
        npm_bindings.ContentPackagesApi.upload()
    assert exc.value.status in (400, 422)


@pytest.mark.parallel
def test_create_without_file_or_artifact_fails(npm_bindings):
    """Calling async create with no file/artifact should fail."""
    with pytest.raises(ApiException) as exc:
        npm_bindings.ContentPackagesApi.create()
    assert exc.value.status in (400, 422)
