"""Catalog API tests.

Generated client methods for packages/, metrics/, collapse_builds, and version=
are unavailable until the OpenAPI client is regenerated.
"""

import io
import json
import tarfile
import uuid
from datetime import datetime
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


def _write_tgz(tmp_path, tgz_bytes, filename="pkg.tgz"):
    path = tmp_path / filename
    path.write_bytes(tgz_bytes)
    return str(path)


def _parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _api_get(bindings_cfg, path, **params):
    url = urljoin(bindings_cfg.host + "/", path.lstrip("/"))
    response = requests.get(url, params=params, auth=(bindings_cfg.username, bindings_cfg.password))
    assert response.status_code == 200, response.text
    return response.json()


def _content_package_path(repo_href):
    marker = "/api/v3/"
    idx = repo_href.find(marker)
    assert idx != -1, repo_href
    return f"{repo_href[: idx + len(marker)]}content/npm/packages/"


def _assert_package_row(pkg):
    assert pkg["name"]
    assert pkg["last_updated"]
    assert "latest_versions" not in pkg
    assert pkg["versions"] == [rel["version"] for rel in pkg["latest_releases"]]
    for rel in pkg["latest_releases"]:
        assert "version" in rel
        assert "release" in rel
        assert rel["created_at"]


def _add_packages(npm_bindings, monitor_task, tmp_path, repo, packages):
    hrefs = []
    for i, (name, version) in enumerate(packages):
        tgz_bytes = _build_npm_tgz(name=name, version=version)
        path = _write_tgz(tmp_path, tgz_bytes, f"pkg-{uuid.uuid4().hex[:8]}-{i}.tgz")
        content = npm_bindings.ContentPackagesApi.upload(file=path, name=name, version=version)
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
    """Three names; hello has two versions plus a Lightwell rebuild."""
    suffix = uuid.uuid4().hex[:8]
    names = SimpleNamespace(
        hello=f"hello-{suffix}",
        world=f"world-{suffix}",
        scoped=f"@types/{suffix}-node",
    )
    # Upload order sets pulp_created: unsuffixed 1.0.0 first, then the rebuild.
    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [
            (names.hello, "1.0.0"),
            (names.hello, "1.0.0.rhlw-00001"),
            (names.hello, "2.0.0"),
            (names.world, "1.0.0"),
            (names.scoped, "22.0.0"),
        ],
    )
    return SimpleNamespace(repo=repo, names=names)


@pytest.mark.parallel
def test_package_list_grouping_and_pagination(bindings_cfg, catalog_data):
    """Package index is one row per name, and count is distinct packages not units."""
    repo = catalog_data.repo
    names = catalog_data.names

    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", limit=1)
    assert data["count"] == 3
    assert len(data["results"]) == 1
    _assert_package_row(data["results"][0])

    page2 = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", limit=1, offset=1)
    assert page2["count"] == 3
    assert page2["results"][0]["name"] != data["results"][0]["name"]

    all_rows = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", limit=100)["results"]
    listed = {pkg["name"] for pkg in all_rows}
    assert listed == {names.hello, names.world, names.scoped}

    hello = next(pkg for pkg in all_rows if pkg["name"] == names.hello)
    _assert_package_row(hello)
    assert hello["versions"] == ["2.0.0", "1.0.0"]
    assert len(hello["latest_releases"]) == 2
    release_100 = next(rel for rel in hello["latest_releases"] if rel["version"] == "1.0.0")
    assert release_100["release"] == "rhlw-00001"
    release_200 = next(rel for rel in hello["latest_releases"] if rel["version"] == "2.0.0")
    assert release_200["release"] == ""

    scoped = next(pkg for pkg in all_rows if pkg["name"] == names.scoped)
    _assert_package_row(scoped)
    assert scoped["versions"] == ["22.0.0"]


@pytest.mark.parallel
def test_package_list_istartswith(bindings_cfg, catalog_data):
    """Prefix search is case-insensitive on the full package name, including scope."""
    repo = catalog_data.repo
    names = catalog_data.names

    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", name__istartswith=names.hello)
    assert data["count"] == 1
    assert data["results"][0]["name"] == names.hello

    data = _api_get(
        bindings_cfg, f"{repo.pulp_href}packages/", name__istartswith=names.hello[:5].upper()
    )
    assert data["count"] == 1
    assert data["results"][0]["name"] == names.hello

    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", name__istartswith="@types/")
    assert data["count"] == 1
    assert data["results"][0]["name"] == names.scoped

    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", name__istartswith="@TYPES/")
    assert data["count"] == 1
    assert data["results"][0]["name"] == names.scoped

    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", name__istartswith="missing-prefix")
    assert data["count"] == 0


@pytest.mark.parallel
def test_package_list_icontains(bindings_cfg, catalog_data):
    """Substring search is case-insensitive on the full package name."""
    repo = catalog_data.repo
    names = catalog_data.names
    path = f"{repo.pulp_href}packages/"

    data = _api_get(bindings_cfg, path, name__icontains="hello")
    assert data["count"] == 1
    assert data["results"][0]["name"] == names.hello

    data = _api_get(bindings_cfg, path, name__icontains="HELLO")
    assert data["count"] == 1
    assert data["results"][0]["name"] == names.hello

    data = _api_get(bindings_cfg, path, name__icontains="types/")
    assert data["count"] == 1
    assert data["results"][0]["name"] == names.scoped

    data = _api_get(bindings_cfg, path, name__icontains="missing-infix")
    assert data["count"] == 0

    blank = _api_get(bindings_cfg, path, name__icontains="")
    assert blank["count"] == 3
    blank_prefix = _api_get(bindings_cfg, path, name__istartswith="")
    assert blank_prefix["count"] == 3

    and_prefix = _api_get(
        bindings_cfg, path, name__icontains=names.hello[-8:], name__istartswith="hello"
    )
    assert and_prefix["count"] == 1
    assert and_prefix["results"][0]["name"] == names.hello

    miss = _api_get(bindings_cfg, path, name__icontains="hello", name__istartswith="@types/")
    assert miss["count"] == 0


@pytest.mark.parallel
def test_package_list_empty_repository(bindings_cfg, npm_repository_factory):
    repo = npm_repository_factory()
    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")
    assert data["count"] == 0
    assert data["results"] == []


@pytest.mark.parallel
def test_repository_metrics(bindings_cfg, catalog_data, npm_repository_factory):
    """Metrics count distinct names / base versions / full (name, version) units."""
    data = _api_get(bindings_cfg, f"{catalog_data.repo.pulp_href}metrics/")
    assert data["package_count"] == 3
    # hello: 1.0.0, 2.0.0; world 1.0.0; scoped 22.0.0
    assert data["version_count"] == 4
    # hello also has 1.0.0.rhlw-00001 as a separate full version
    assert data["build_count"] == 5

    empty = _api_get(bindings_cfg, f"{npm_repository_factory().pulp_href}metrics/")
    assert empty == {"package_count": 0, "version_count": 0, "build_count": 0}


@pytest.mark.parallel
def test_packages_and_metrics_repository_version(
    bindings_cfg, catalog_data, npm_repository_factory
):
    """repository_version selects a snapshot; omitted uses the latest complete version."""
    repo = catalog_data.repo
    latest_href = repo.latest_version_href
    v0_href = f"{repo.pulp_href}versions/0/"

    default_pkgs = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")
    explicit_pkgs = _api_get(
        bindings_cfg, f"{repo.pulp_href}packages/", repository_version=latest_href
    )
    assert default_pkgs["count"] == explicit_pkgs["count"] == 3

    v0_pkgs = _api_get(bindings_cfg, f"{repo.pulp_href}packages/", repository_version=v0_href)
    assert v0_pkgs["count"] == 0
    assert v0_pkgs["results"] == []

    default_metrics = _api_get(bindings_cfg, f"{repo.pulp_href}metrics/")
    explicit_metrics = _api_get(
        bindings_cfg, f"{repo.pulp_href}metrics/", repository_version=latest_href
    )
    assert default_metrics == explicit_metrics
    v0_metrics = _api_get(bindings_cfg, f"{repo.pulp_href}metrics/", repository_version=v0_href)
    assert v0_metrics == {"package_count": 0, "version_count": 0, "build_count": 0}

    other = npm_repository_factory()
    url = urljoin(bindings_cfg.host + "/", f"{repo.pulp_href}packages/".lstrip("/"))
    response = requests.get(
        url,
        params={"repository_version": other.latest_version_href},
        auth=(bindings_cfg.username, bindings_cfg.password),
    )
    assert response.status_code == 400, response.text
    metrics_url = urljoin(bindings_cfg.host + "/", f"{repo.pulp_href}metrics/".lstrip("/"))
    metrics_response = requests.get(
        metrics_url,
        params={"repository_version": other.latest_version_href},
        auth=(bindings_cfg.username, bindings_cfg.password),
    )
    assert metrics_response.status_code == 400, metrics_response.text


@pytest.mark.parallel
def test_collapse_builds_and_base_version(bindings_cfg, catalog_data):
    """collapse_builds keeps one unit per logical version; base_version is always present."""
    path = _content_package_path(catalog_data.repo.pulp_href)
    repo_version = catalog_data.repo.latest_version_href
    hello = catalog_data.names.hello

    expanded = _api_get(
        bindings_cfg,
        path,
        name=hello,
        repository_version=repo_version,
        collapse_builds="false",
        limit=100,
    )
    default = _api_get(
        bindings_cfg,
        path,
        name=hello,
        repository_version=repo_version,
        limit=100,
    )
    collapsed = _api_get(
        bindings_cfg,
        path,
        name=hello,
        repository_version=repo_version,
        collapse_builds="true",
        limit=100,
    )
    assert expanded["count"] == 3
    assert default["count"] == 3
    assert {item["version"] for item in default["results"]} == {
        "1.0.0",
        "1.0.0.rhlw-00001",
        "2.0.0",
    }
    assert collapsed["count"] == 2
    assert {item["base_version"] for item in collapsed["results"]} == {"1.0.0", "2.0.0"}
    collapsed_rebuild = next(
        item for item in collapsed["results"] if item["base_version"] == "1.0.0"
    )
    assert collapsed_rebuild["version"] == "1.0.0.rhlw-00001"
    for item in expanded["results"]:
        if item["version"] == "1.0.0.rhlw-00001":
            assert item["base_version"] == "1.0.0"
        else:
            assert item["base_version"] == item["version"]
        assert "builds" not in item

    # No rebuilds: collapse is an identity (one row, base_version == version).
    world = catalog_data.names.world
    world_default = _api_get(
        bindings_cfg, path, name=world, repository_version=repo_version, limit=100
    )
    world_collapsed = _api_get(
        bindings_cfg,
        path,
        name=world,
        repository_version=repo_version,
        collapse_builds="true",
        limit=100,
    )
    assert world_default["count"] == world_collapsed["count"] == 1
    assert world_collapsed["results"][0]["version"] == "1.0.0"
    assert world_collapsed["results"][0]["base_version"] == "1.0.0"

    # DISTINCT ON must still work when the client also sends ordering.
    ordered = _api_get(
        bindings_cfg,
        path,
        name=hello,
        repository_version=repo_version,
        collapse_builds="true",
        ordering="-pulp_created",
        limit=100,
    )
    assert ordered["count"] == 2
    assert {item["base_version"] for item in ordered["results"]} == {"1.0.0", "2.0.0"}

    # Whole-repo collapse: 5 units -> 4 logical versions (hello 1.0.0 + 2.0.0, world, scoped).
    whole = _api_get(
        bindings_cfg,
        path,
        repository_version=repo_version,
        collapse_builds="true",
        limit=100,
    )
    assert whole["count"] == 4


@pytest.mark.parallel
def test_package_get_version_exact(bindings_cfg, catalog_data):
    """PackageGet uses exact version=; omit collapse_builds."""
    path = _content_package_path(catalog_data.repo.pulp_href)
    hello = catalog_data.names.hello
    scoped = catalog_data.names.scoped

    exact = _api_get(bindings_cfg, path, name=hello, version="1.0.0", limit=100)
    assert exact["count"] == 1
    assert exact["results"][0]["version"] == "1.0.0"
    assert exact["results"][0]["name"] == hello
    assert exact["results"][0]["base_version"] == "1.0.0"

    rebuild = _api_get(bindings_cfg, path, name=hello, version="1.0.0.rhlw-00001", limit=100)
    assert rebuild["count"] == 1
    assert rebuild["results"][0]["version"] == "1.0.0.rhlw-00001"
    assert rebuild["results"][0]["base_version"] == "1.0.0"

    scoped_row = _api_get(bindings_cfg, path, name=scoped, version="22.0.0", limit=100)
    assert scoped_row["count"] == 1
    assert scoped_row["results"][0]["name"] == scoped
    assert scoped_row["results"][0]["version"] == "22.0.0"

    missing = _api_get(bindings_cfg, path, name=hello, version="9.9.9", limit=100)
    assert missing["count"] == 0


@pytest.mark.parallel
def test_content_list_name_in_still_works(bindings_cfg, catalog_data):
    """Existing name exact/in filters keep working alongside version=."""
    path = _content_package_path(catalog_data.repo.pulp_href)
    repo_version = catalog_data.repo.latest_version_href
    hello = catalog_data.names.hello
    world = catalog_data.names.world

    exact = _api_get(bindings_cfg, path, name=hello, repository_version=repo_version, limit=100)
    assert exact["count"] == 3
    assert {item["name"] for item in exact["results"]} == {hello}

    listed = _api_get(
        bindings_cfg,
        path,
        name__in=f"{hello},{world}",
        repository_version=repo_version,
        limit=100,
    )
    assert listed["count"] == 4
    assert {item["name"] for item in listed["results"]} == {hello, world}


@pytest.mark.parallel
def test_package_list_version_order(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """versions and latest_releases are newest-first by numeric tokens, not lexicographically."""
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
    assert pkg["versions"] == ["1.10", "1.9", "1.2"]
    assert [rel["version"] for rel in pkg["latest_releases"]] == ["1.10", "1.9", "1.2"]


@pytest.mark.parallel
def test_predisclosure_rebuild_suffix(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """Trailing .letters-... is a rebuild, including predisclosure -nNNNN."""
    name = f"hello-{uuid.uuid4().hex[:8]}"
    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [
            (name, "5.3.17"),
            (name, "5.3.17.rhlw-00001"),
            (name, "5.3.17.rhlw-00001-n0001"),
        ],
    )
    data = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")
    assert data["count"] == 1
    pkg = data["results"][0]
    _assert_package_row(pkg)
    assert pkg["versions"] == ["5.3.17"]
    assert pkg["latest_releases"][0]["version"] == "5.3.17"
    assert pkg["latest_releases"][0]["release"] == "rhlw-00001-n0001"

    metrics = _api_get(bindings_cfg, f"{repo.pulp_href}metrics/")
    assert metrics == {"package_count": 1, "version_count": 1, "build_count": 3}

    path = _content_package_path(repo.pulp_href)
    repo_version = repo.latest_version_href
    expanded = _api_get(
        bindings_cfg,
        path,
        name=name,
        repository_version=repo_version,
        collapse_builds="false",
        limit=100,
    )
    collapsed = _api_get(
        bindings_cfg,
        path,
        name=name,
        repository_version=repo_version,
        collapse_builds="true",
        limit=100,
    )
    assert expanded["count"] == 3
    assert {item["version"] for item in expanded["results"]} == {
        "5.3.17",
        "5.3.17.rhlw-00001",
        "5.3.17.rhlw-00001-n0001",
    }
    assert collapsed["count"] == 1
    assert collapsed["results"][0]["base_version"] == "5.3.17"
    assert collapsed["results"][0]["version"] == "5.3.17.rhlw-00001-n0001"


@pytest.mark.parallel
def test_package_list_created_at_is_membership(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """created_at is repository membership time, not the content unit's pulp_created."""
    name = f"timestamped-{uuid.uuid4().hex[:8]}"
    repo_a = _upload_packages(
        npm_bindings, npm_repository_factory, monitor_task, tmp_path, [(name, "1.0.0")]
    )
    units = _api_get(
        bindings_cfg,
        _content_package_path(repo_a.pulp_href),
        repository_version=repo_a.latest_version_href,
        limit=100,
    )["results"]
    assert len(units) == 1
    unit_created = _parse_dt(units[0]["pulp_created"])

    repo_b = npm_repository_factory()
    monitor_task(
        npm_bindings.RepositoriesNpmApi.modify(
            repo_b.pulp_href, {"add_content_units": [units[0]["pulp_href"]]}
        ).task
    )

    pkgs_a = _api_get(bindings_cfg, f"{repo_a.pulp_href}packages/")["results"]
    pkgs_b = _api_get(bindings_cfg, f"{repo_b.pulp_href}packages/")["results"]
    created_a = _parse_dt(pkgs_a[0]["latest_releases"][0]["created_at"])
    created_b = _parse_dt(pkgs_b[0]["latest_releases"][0]["created_at"])

    assert created_a >= unit_created
    assert created_b > created_a
    assert created_b > unit_created
    assert pkgs_a[0]["last_updated"] == pkgs_a[0]["latest_releases"][0]["created_at"]
    assert pkgs_b[0]["last_updated"] == pkgs_b[0]["latest_releases"][0]["created_at"]
    assert _parse_dt(pkgs_b[0]["last_updated"]) > _parse_dt(pkgs_a[0]["last_updated"])


@pytest.mark.parallel
def test_package_list_ordering_name(bindings_cfg, catalog_data):
    """Default order is name; -name reverses it.

    Do not compare to Python ``sorted()``: Postgres collation sorts ``@scope/…``
    differently from Unicode code points.
    """
    default = _api_get(bindings_cfg, f"{catalog_data.repo.pulp_href}packages/")["results"]
    names = [pkg["name"] for pkg in default]
    assert len(names) == 3
    explicit = _api_get(bindings_cfg, f"{catalog_data.repo.pulp_href}packages/", ordering="name")[
        "results"
    ]
    assert [pkg["name"] for pkg in explicit] == names

    reversed_rows = _api_get(
        bindings_cfg, f"{catalog_data.repo.pulp_href}packages/", ordering="-name"
    )["results"]
    assert [pkg["name"] for pkg in reversed_rows] == list(reversed(names))

    page1 = _api_get(
        bindings_cfg, f"{catalog_data.repo.pulp_href}packages/", ordering="-name", limit=1
    )
    page2 = _api_get(
        bindings_cfg,
        f"{catalog_data.repo.pulp_href}packages/",
        ordering="-name",
        limit=1,
        offset=1,
    )
    assert page1["count"] == page2["count"] == 3
    assert page1["results"][0]["name"] == reversed_rows[0]["name"]
    assert page2["results"][0]["name"] == reversed_rows[1]["name"]


@pytest.mark.parallel
def test_package_list_ordering_last_updated(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """last_updated is newest membership of any rebuild and is a sort key."""
    suffix = uuid.uuid4().hex[:8]
    later_name = f"zzz-later-{suffix}"
    earlier_name = f"aaa-earlier-{suffix}"

    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [(later_name, "2.0.0")],
    )
    first = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")["results"][0]
    first_updated = _parse_dt(first["last_updated"])
    assert first["name"] == later_name
    assert first["last_updated"] == first["latest_releases"][0]["created_at"]

    repo = _add_packages(npm_bindings, monitor_task, tmp_path, repo, [(earlier_name, "1.0.0")])
    rows = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")["results"]
    by_name = {pkg["name"]: pkg for pkg in rows}
    older = by_name[later_name]
    newer = by_name[earlier_name]
    assert _parse_dt(older["last_updated"]) == first_updated
    assert _parse_dt(newer["last_updated"]) > first_updated

    default_names = [pkg["name"] for pkg in rows]
    assert default_names == [earlier_name, later_name]

    oldest_first = _api_get(
        bindings_cfg, f"{repo.pulp_href}packages/", ordering="last_updated", limit=100
    )["results"]
    assert [pkg["name"] for pkg in oldest_first] == [later_name, earlier_name]

    by_updated = _api_get(
        bindings_cfg, f"{repo.pulp_href}packages/", ordering="-last_updated", limit=100
    )["results"]
    assert [pkg["name"] for pkg in by_updated] == [earlier_name, later_name]

    repo = _add_packages(
        npm_bindings, monitor_task, tmp_path, repo, [(later_name, "1.0.0.rhlw-00003")]
    )
    after_rebuild = _api_get(
        bindings_cfg, f"{repo.pulp_href}packages/", ordering="-last_updated", limit=100
    )["results"]
    assert [pkg["name"] for pkg in after_rebuild] == [later_name, earlier_name]
    zzz = after_rebuild[0]
    assert _parse_dt(zzz["last_updated"]) > _parse_dt(newer["last_updated"])
    assert set(zzz["versions"]) == {"2.0.0", "1.0.0"}
    assert zzz["versions"][0] == "2.0.0"
    rebuild_rel = next(rel for rel in zzz["latest_releases"] if rel["version"] == "1.0.0")
    assert rebuild_rel["release"] == "rhlw-00003"
    assert zzz["last_updated"] == rebuild_rel["created_at"]


@pytest.mark.parallel
def test_collapse_keeps_neighbor_versions(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """1.0.10 is not collapsed into 1.0.1 (same idea as Maven 5.3.180 vs 5.3.18)."""
    name = f"neighbor-{uuid.uuid4().hex[:8]}"
    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [
            (name, "1.0.1"),
            (name, "1.0.1.rhlw-00001"),
            (name, "1.0.10"),
        ],
    )
    pkgs = _api_get(bindings_cfg, f"{repo.pulp_href}packages/")
    assert pkgs["count"] == 1
    _assert_package_row(pkgs["results"][0])
    assert pkgs["results"][0]["versions"] == ["1.0.10", "1.0.1"]

    metrics = _api_get(bindings_cfg, f"{repo.pulp_href}metrics/")
    assert metrics == {"package_count": 1, "version_count": 2, "build_count": 3}

    path = _content_package_path(repo.pulp_href)
    collapsed = _api_get(
        bindings_cfg,
        path,
        name=name,
        repository_version=repo.latest_version_href,
        collapse_builds="true",
        limit=100,
    )
    assert collapsed["count"] == 2
    assert {item["base_version"] for item in collapsed["results"]} == {"1.0.1", "1.0.10"}
    rebuilt = next(item for item in collapsed["results"] if item["base_version"] == "1.0.1")
    assert rebuilt["version"] == "1.0.1.rhlw-00001"


@pytest.mark.parallel
def test_package_list_ordering_invalid(bindings_cfg, catalog_data):
    url = urljoin(bindings_cfg.host + "/", f"{catalog_data.repo.pulp_href}packages/".lstrip("/"))
    response = requests.get(
        url,
        params={"ordering": "group_id"},
        auth=(bindings_cfg.username, bindings_cfg.password),
    )
    assert response.status_code == 400, response.text


@pytest.mark.parallel
def test_package_list_ignores_repository_name_filter(bindings_cfg, catalog_data):
    """Repository FilterSet ``name`` must not be applied to packages/ or metrics/."""
    path = f"{catalog_data.repo.pulp_href}packages/"
    data = _api_get(bindings_cfg, path, name=catalog_data.names.hello)
    assert data["count"] == 3
    metrics = _api_get(bindings_cfg, f"{catalog_data.repo.pulp_href}metrics/", name="not-a-repo")
    assert metrics["package_count"] == 3


@pytest.mark.parallel
def test_collapse_keeps_newest_pulp_created(
    bindings_cfg, npm_bindings, npm_repository_factory, monitor_task, tmp_path
):
    """collapse_builds keeps the unit with the latest pulp_created, even if that is unsuffixed."""
    name = f"newest-{uuid.uuid4().hex[:8]}"
    repo = _upload_packages(
        npm_bindings,
        npm_repository_factory,
        monitor_task,
        tmp_path,
        [
            (name, "1.0.0.rhlw-00001"),
            (name, "1.0.0"),
        ],
    )
    path = _content_package_path(repo.pulp_href)
    collapsed = _api_get(
        bindings_cfg,
        path,
        name=name,
        repository_version=repo.latest_version_href,
        collapse_builds="true",
        limit=100,
    )
    assert collapsed["count"] == 1
    assert collapsed["results"][0]["version"] == "1.0.0"
    assert collapsed["results"][0]["base_version"] == "1.0.0"


@pytest.mark.parallel
def test_packages_and_metrics_require_view_permission(bindings_cfg, gen_user, catalog_data):
    """packages/ and metrics/ use the same view permission as retrieve."""
    viewer = gen_user(model_roles=["npm.npmrepository_viewer"])
    nobody = gen_user()
    packages_url = urljoin(
        bindings_cfg.host + "/", f"{catalog_data.repo.pulp_href}packages/".lstrip("/")
    )
    metrics_url = urljoin(
        bindings_cfg.host + "/", f"{catalog_data.repo.pulp_href}metrics/".lstrip("/")
    )
    with viewer:
        packages = requests.get(packages_url, auth=(bindings_cfg.username, bindings_cfg.password))
        metrics = requests.get(metrics_url, auth=(bindings_cfg.username, bindings_cfg.password))
    assert packages.status_code == 200, packages.text
    assert packages.json()["count"] == 3
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["package_count"] == 3

    with nobody:
        hidden_packages = requests.get(
            packages_url, auth=(bindings_cfg.username, bindings_cfg.password)
        )
        hidden_metrics = requests.get(
            metrics_url, auth=(bindings_cfg.username, bindings_cfg.password)
        )
    assert hidden_packages.status_code == 404, hidden_packages.text
    assert hidden_metrics.status_code == 404, hidden_metrics.text
