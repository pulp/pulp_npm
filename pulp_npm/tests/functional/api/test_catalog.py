"""Catalog API tests.

Generated client methods for packages/ are unavailable until the OpenAPI client is regenerated.
"""

import io
import json
import tarfile
import uuid
from types import SimpleNamespace
from urllib.parse import urljoin

import pytest
import requests


def _build_npm_tgz(name="test-pkg", version="1.0.0"):
    package_json = json.dumps({"name": name, "version": version}).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(package_json)
        tar.addfile(info, io.BytesIO(package_json))
    buf.seek(0)
    return buf.read()


def _api_get(bindings_cfg, path, **params):
    url = urljoin(bindings_cfg.host + "/", path.lstrip("/"))
    response = requests.get(url, params=params, auth=(bindings_cfg.username, bindings_cfg.password))
    assert response.status_code == 200, response.text
    return response.json()


def _assert_package_row(pkg):
    assert set(pkg) == {"name", "versions"}
    assert pkg["name"]
    versions = [item["version"] for item in pkg["versions"]]
    assert versions
    assert len(versions) == len(set(versions))
    for item in pkg["versions"]:
        assert set(item) == {"version"}
        assert item["version"]


def _add_packages(npm_bindings, monitor_task, tmp_path, repo, packages):
    hrefs = []
    for i, (name, version) in enumerate(packages):
        path = tmp_path / f"pkg-{uuid.uuid4().hex[:8]}-{i}.tgz"
        path.write_bytes(_build_npm_tgz(name=name, version=version))
        content = npm_bindings.ContentPackagesApi.upload(file=str(path), name=name, version=version)
        hrefs.append(content.pulp_href)
    monitor_task(
        npm_bindings.RepositoriesNpmApi.modify(repo.pulp_href, {"add_content_units": hrefs}).task
    )
    return npm_bindings.RepositoriesNpmApi.read(repo.pulp_href)


def _upload_packages(npm_bindings, npm_repository_factory, monitor_task, tmp_path, packages):
    repo = npm_repository_factory()
    return _add_packages(npm_bindings, monitor_task, tmp_path, repo, packages)


@pytest.fixture
def catalog_data(npm_bindings, npm_repository_factory, monitor_task, tmp_path):
    """Four names. aaa has two releases plus a rebuild; scoped keeps the full name."""
    suffix = uuid.uuid4().hex[:8]
    names = SimpleNamespace(
        aaa=f"aaa-{suffix}",
        mmm=f"mmm-{suffix}",
        zzz=f"zzz-{suffix}",
        scoped=f"@types/{suffix}-node",
    )
    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [
            (names.aaa, "1.0.0"),
            (names.aaa, "2.0.0"),
            (names.aaa, "1.0.0.rhlw-00001"),
            (names.mmm, "1.0.0"),
            (names.zzz, "9.0.0"),
            (names.scoped, "22.0.0"),
        ],
    )
    return SimpleNamespace(repo=repo, names=names)


@pytest.mark.parallel
def test_package_list_grouping_and_pagination(bindings_cfg, catalog_data):
    """Package index is one row per name, and count is distinct packages not units."""
    repo = catalog_data.repo
    names = catalog_data.names
    path = f"{repo.pulp_href}packages/"

    data = _api_get(bindings_cfg, path, limit=1)
    assert data["count"] == 4
    assert len(data["results"]) == 1
    _assert_package_row(data["results"][0])
    assert set(data) >= {"count", "next", "previous", "results"}

    page2 = _api_get(bindings_cfg, path, limit=1, offset=1)
    assert page2["count"] == 4
    assert page2["results"][0]["name"] != data["results"][0]["name"]

    all_rows = _api_get(bindings_cfg, path, limit=100)["results"]
    listed = [pkg["name"] for pkg in all_rows]
    assert set(listed) == {names.aaa, names.mmm, names.zzz, names.scoped}
    assert [name for name in listed if not name.startswith("@")] == [
        names.aaa,
        names.mmm,
        names.zzz,
    ]
    assert data["results"][0]["name"] == listed[0]
    assert page2["results"][0]["name"] == listed[1]

    scoped = next(pkg for pkg in all_rows if pkg["name"] == names.scoped)
    _assert_package_row(scoped)
    assert scoped["versions"] == [{"version": "22.0.0"}]

    aaa = next(pkg for pkg in all_rows if pkg["name"] == names.aaa)
    _assert_package_row(aaa)
    assert [item["version"] for item in aaa["versions"]] == [
        "2.0.0",
        "1.0.0.rhlw-00001",
        "1.0.0",
    ]


@pytest.mark.parallel
def test_package_list_empty_repository(bindings_cfg, npm_repository_factory):
    repo = npm_repository_factory()
    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")
    assert data["count"] == 0
    assert data["results"] == []


@pytest.mark.parallel
def test_packages_repository_version(bindings_cfg, catalog_data, npm_repository_factory):
    """repository_version selects a snapshot; omitted uses the latest complete version."""
    repo = catalog_data.repo
    latest_href = repo.latest_version_href
    v0_href = f"{repo.pulp_href}versions/0/"
    path = f"{repo.pulp_href}packages/"

    default_pkgs = _api_get(bindings_cfg, path)
    explicit_pkgs = _api_get(bindings_cfg, path, repository_version=latest_href)
    assert default_pkgs["count"] == explicit_pkgs["count"] == 4

    version = _api_get(bindings_cfg, latest_href)
    prn_pkgs = _api_get(bindings_cfg, path, repository_version=version["prn"])
    assert prn_pkgs["count"] == 4
    assert version["prn"].startswith("prn:core.repositoryversion:")

    v0_pkgs = _api_get(bindings_cfg, path, repository_version=v0_href)
    assert v0_pkgs["count"] == 0
    assert v0_pkgs["results"] == []

    other = npm_repository_factory()
    url = urljoin(bindings_cfg.host + "/", path.lstrip("/"))
    response = requests.get(
        url,
        params={"repository_version": other.latest_version_href},
        auth=(bindings_cfg.username, bindings_cfg.password),
    )
    assert response.status_code == 400, response.text


@pytest.mark.parallel
def test_package_list_keeps_stored_versions(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """A rebuild stays its own entry because its stored version string differs."""
    name = f"rebuild-{uuid.uuid4().hex[:8]}"
    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [
            (name, "1.0.0"),
            (name, "1.0.0.rhlw-00001"),
        ],
    )
    pkgs = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")
    assert pkgs["count"] == 1
    row = pkgs["results"][0]
    _assert_package_row(row)
    assert row["name"] == name
    assert {item["version"] for item in row["versions"]} == {"1.0.0", "1.0.0.rhlw-00001"}


@pytest.mark.parallel
def test_package_list_version_order(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """Stored versions are newest-first by numeric tokens, not lexicographically."""
    name = f"ordered-{uuid.uuid4().hex[:8]}"
    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [(name, "1.10"), (name, "1.9"), (name, "1.2")],
    )
    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")
    assert data["count"] == 1
    pkg = data["results"][0]
    _assert_package_row(pkg)
    assert [item["version"] for item in pkg["versions"]] == ["1.10", "1.9", "1.2"]
