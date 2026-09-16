"""Helpers for repository package catalog, metrics, and rebuild collapse."""

from collections import defaultdict

from django.db.models import CharField, Func, Max, Min, Q, Value
from django.db.models.functions import Coalesce

from .models import Package
from .versions import (
    BUILD_SUFFIX_PATTERN,
    normalize_package_index_ordering,
    rebuild_release,
    version_sort_key,
)


def base_version_annotation(field_name="version"):
    """SQL expression that strips a trailing rebuild suffix from ``version``.

    Uses ``versions.BUILD_SUFFIX_PATTERN`` (POSIX) so Python ``strip_build_suffix``
    and this ``REGEXP_REPLACE`` stay aligned. Implemented with ``REGEXP_REPLACE``
    so it does not depend on Django's ``RegexpReplace`` (not present in every
    Django 4.2/5.2 packaging Pulp uses).
    """
    return Func(
        field_name,
        Value(BUILD_SUFFIX_PATTERN),
        Value(""),
        function="REGEXP_REPLACE",
        output_field=CharField(),
    )


def collapse_npm_builds(queryset):
    """Keep one Package per ``(name, base_version)``.

    ``base_version`` is ``version`` with a trailing rebuild suffix stripped.
    The unit with the latest ``pulp_created`` is kept.
    """
    return (
        queryset.prefetch_related(None)
        .annotate(_collapse_base_version=base_version_annotation())
        .order_by("name", "_collapse_base_version", "-pulp_created")
        .distinct("name", "_collapse_base_version")
    )


def npm_packages_in_version(repository_version):
    """Package content contained in ``repository_version``."""
    if repository_version is None:
        return Package.objects.none()
    return Package.objects.filter(pk__in=repository_version.content)


def apply_package_prefix_filters(queryset, name_prefix=None, name_contains=None):
    """Apply case-insensitive name filters used by the package index."""
    if name_prefix:
        queryset = queryset.filter(name__istartswith=name_prefix)
    if name_contains:
        queryset = queryset.filter(name__icontains=name_contains)
    return queryset


def membership_in_version_q(repository, repository_version):
    """Q-object matching RepositoryContent rows present in ``repository_version``."""
    return Q(
        version_memberships__repository=repository,
        version_memberships__version_added__number__lte=repository_version.number,
    ) & (
        Q(version_memberships__version_removed__isnull=True)
        | Q(version_memberships__version_removed__number__gt=repository_version.number)
    )


def last_updated_annotation(repository, repository_version):
    """Newest repository-membership time among all Package units for a name.

    Uses ``RepositoryContent.pulp_created`` (any rebuild), falling back to the
    content unit's ``pulp_created``.
    """
    return Coalesce(
        Max(
            "version_memberships__pulp_created",
            filter=membership_in_version_q(repository, repository_version),
        ),
        Max("pulp_created"),
    )


def distinct_name_qs(content_qs, repository, repository_version, ordering=None):
    """One row per distinct ``name``, ordered for stable pagination."""
    if ordering is None:
        ordering = normalize_package_index_ordering([])
    qs = content_qs.order_by().values("name")
    if repository_version is None:
        qs = qs.annotate(last_updated=Max("pulp_created"))
    else:
        qs = qs.annotate(last_updated=last_updated_annotation(repository, repository_version))
    return qs.order_by(*ordering)


def assemble_package_index(content_qs, name_rows, repository, repository_version):
    """Build package-index dicts for ``name_rows``.

    Each row is one ``name``. ``versions`` are distinct base versions, newest
    first (numeric-token order). ``latest_releases`` keeps the newest rebuild
    (latest ``pulp_created``) per base version in the same order. ``created_at``
    is that unit's repository-membership time (``RepositoryContent.pulp_created``),
    falling back to the content unit's ``pulp_created``. ``last_updated`` is the
    newest membership among all units for the package (any rebuild), taken from
    ``name_rows`` when annotated.
    """
    if not name_rows or repository_version is None:
        return []

    names = [row["name"] for row in name_rows]
    in_this_version = membership_in_version_q(repository, repository_version)

    newest_units = list(
        content_qs.filter(name__in=names)
        .prefetch_related(None)
        .annotate(_base_version=base_version_annotation())
        .order_by("name", "_base_version", "-pulp_created")
        .distinct("name", "_base_version")
    )
    newest = [
        {
            "pk": unit.pk,
            "name": unit.name,
            "version": unit.version,
            "_base_version": unit._base_version,
            "pulp_created": unit.pulp_created,
        }
        for unit in newest_units
    ]

    memberships = {}
    if newest:
        memberships = dict(
            Package.objects.filter(pk__in=[row["pk"] for row in newest])
            .annotate(
                membership_created=Min(
                    "version_memberships__pulp_created",
                    filter=in_this_version,
                )
            )
            .values_list("pk", "membership_created")
        )

    releases_by_name = defaultdict(list)
    for row in newest:
        releases_by_name[row["name"]].append(row)

    result = []
    for row in name_rows:
        rels = sorted(
            releases_by_name.get(row["name"], []),
            key=lambda item: version_sort_key(item["_base_version"]),
            reverse=True,
        )
        versions = [item["_base_version"] for item in rels]
        latest_releases = [
            {
                "version": item["_base_version"],
                "release": rebuild_release(item["version"]),
                "created_at": memberships.get(item["pk"]) or item["pulp_created"],
            }
            for item in rels
        ]
        result.append(
            {
                "name": row["name"],
                "last_updated": row.get("last_updated"),
                "versions": versions,
                "latest_releases": latest_releases,
            }
        )
    return result


def repository_metrics(content_qs):
    """Distinct package / logical-version / build counts for Package.

    Identity is always ``Package`` (one unit per ``(name, version)``):

    * ``package_count``: distinct ``name``
    * ``version_count``: distinct ``(name, base_version)`` after rebuild-suffix strip
    * ``build_count``: distinct ``(name, version)`` (full version string)
    """
    content_qs = content_qs.order_by()
    return {
        "package_count": content_qs.values("name").distinct().count(),
        "version_count": (
            content_qs.annotate(_base_version=base_version_annotation())
            .values("name", "_base_version")
            .distinct()
            .count()
        ),
        "build_count": content_qs.values("name", "version").distinct().count(),
    }
