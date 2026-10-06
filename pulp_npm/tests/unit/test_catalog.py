"""Unit tests for the repository package index helpers."""

import re
import uuid

import pytest
from django.db import connection

from pulpcore.plugin.models import RepositoryContent

from pulp_npm.app.catalog import (
    _version_sort_key,
    assemble_package_index,
    distinct_package_names_qs,
    npm_packages_in_version,
)
from pulp_npm.app.models import NpmRepository, Package

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _bound_id_count(sql):
    """How many ids the statement binds, whether mogrified or left as ``%s``."""
    lowered = sql.lower()
    return max(len(_UUID_RE.findall(lowered)), lowered.count("%s"))


@pytest.mark.parametrize(
    "versions,expected",
    [
        (["1.10", "1.9", "1.2"], ["1.10", "1.9", "1.2"]),
        (["2.0.0", "1.0.0", "1.0.0.rhlw-00001"], ["2.0.0", "1.0.0.rhlw-00001", "1.0.0"]),
        ([], []),
    ],
)
def test_version_sort_key_newest_first(versions, expected):
    assert sorted(versions, key=_version_sort_key, reverse=True) == expected


@pytest.mark.django_db
def test_package_list_sql_does_not_expand_content_ids():
    """The package index must filter through RepositoryContent, not content_ids.

    A paged list used to inline every content UUID in the version. The name
    page is a distinct name query with LIMIT. Package rows for that page are
    loaded through the membership subquery.
    """
    repository = NpmRepository.objects.create(name=str(uuid.uuid4()))
    created = [
        Package.objects.create(name=name, version=f"1.0.{number}")
        for name in ("alpha", "beta", "gamma", "delta")
        for number in range(5)
    ]
    with repository.new_version() as version:
        version.add_content(Package.objects.filter(pk__in=[item.pk for item in created]))

    repo_version = repository.versions.complete().defer("content_ids").latest()
    content_count = RepositoryContent.objects.filter(
        repository_id=repository.pk, version_removed__isnull=True
    ).count()
    content_qs = npm_packages_in_version(repo_version)
    default_qs = distinct_package_names_qs(content_qs)
    count_qs = content_qs.order_by().values("name").distinct()

    connection.force_debug_cursor = True
    start = len(connection.queries)

    def _since():
        nonlocal start
        sqls = [query["sql"] for query in connection.queries[start:]]
        start = len(connection.queries)
        return sqls

    try:
        count_qs.count()
        count_sqls = _since()
        page = list(default_qs[:20])
        default_sqls = _since()
        rows = assemble_package_index(content_qs, page, repo_version)
        assembled = _since()
    finally:
        connection.force_debug_cursor = False

    assert rows
    assert rows[0]["versions"]
    assert content_count == len(created)
    membership_sql = [
        sql
        for sql in count_sqls + default_sqls + assembled
        if "core_repositorycontent" in sql.lower()
    ]
    assert membership_sql
    for sql in membership_sql:
        lowered = sql.lower()
        assert "content_id" in lowered, sql
        assert _bound_id_count(sql) < content_count, sql
    assert len(count_sqls) == 1, count_sqls
    assert len(default_sqls) == 1, default_sqls
    count_sql, default_sql = count_sqls[0], default_sqls[0]
    assert "max(" not in count_sql.lower()
    assert "max(" not in default_sql.lower()
    assert "distinct" in default_sql.lower()
    assert "limit" in default_sql.lower()
