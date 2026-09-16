"""Helpers for the repository package list."""

import re
from collections import defaultdict
from urllib.parse import urlparse

from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.urls import Resolver404, resolve

from pulpcore.plugin.models import Repository, RepositoryContent, RepositoryVersion
from pulpcore.plugin.util import resolve_prn

from .models import Package


def _version_sort_key(version):
    """Order versions with numeric tokens compared as integers.

    Use with ``reverse=True`` for newest first.
    """
    if not version:
        return ()
    key = []
    for token in re.split(r"([.-])", version):
        if token.isdigit():
            key.append((0, int(token)))
        else:
            key.append((1, token))
    return tuple(key)


def _in_version_bounds_q(repository_version, prefix=""):
    """Version-added/removed bounds for rows present in ``repository_version``."""
    return Q(**{f"{prefix}version_added__number__lte": repository_version.number}) & (
        Q(**{f"{prefix}version_removed__isnull": True})
        | Q(**{f"{prefix}version_removed__number__gt": repository_version.number})
    )


def memberships_in_version(repository_version):
    """RepositoryContent rows contained in ``repository_version``.

    A subquery against this queryset keeps the content-id list in the database.
    ``RepositoryVersion.content`` inlines ``content_ids`` as one bound UUID per
    content unit whenever that array is shorter than 65535.
    """
    return RepositoryContent.objects.filter(
        repository_id=repository_version.repository_id,
    ).filter(_in_version_bounds_q(repository_version))


def npm_packages_in_version(repository_version):
    """Package content contained in ``repository_version``."""
    if repository_version is None:
        return Package.objects.none()
    content_ids = (
        memberships_in_version(repository_version)
        .filter(content__pulp_type=Package.get_pulp_type())
        .order_by()
        .values("content_id")
    )
    return Package.objects.filter(pk__in=content_ids)


def resolve_repository_version(href):
    """Load a repository version without selecting ``content_ids``.

    Accepts a repository-version or repository HREF/PRN. Domain-prefixed hrefs
    include ``pulp_domain`` in the resolved kwargs; that field lives on the
    repository, not ``RepositoryVersion``.
    """
    if not href:
        raise ValueError("No value supplied for repository version.")

    if href.startswith("prn:"):
        model, pk = resolve_prn(href)
        found_kwargs = {"pk": pk}
    else:
        try:
            match = resolve(urlparse(href).path)
        except Resolver404:
            raise ValueError(f"URI not valid: {href}") from None
        model = match.func.cls.queryset.model
        found_kwargs = match.kwargs

    if "pk" in found_kwargs:
        lookup = {"pk": found_kwargs["pk"]}
    else:
        lookup = {}
        for key, value in found_kwargs.items():
            if key.endswith("_pk"):
                lookup[f"{key[:-3]}__pk"] = value
            elif key == "pulp_domain":
                if hasattr(model, "pulp_domain"):
                    lookup["pulp_domain__name"] = value
            elif key in ("api_root", "version"):
                continue
            else:
                lookup[key] = value

    qs = model.objects.all()
    if issubclass(model, RepositoryVersion):
        qs = qs.defer("content_ids")
    try:
        obj = qs.get(**lookup)
    except model.DoesNotExist:
        raise ValueError(f"URI {href} not found.") from None
    except (model.MultipleObjectsReturned, DjangoValidationError, FieldError):
        raise ValueError(f"URI {href} is not a valid repository version.") from None

    if isinstance(obj, RepositoryVersion):
        return obj
    if isinstance(obj, Repository):
        try:
            return obj.versions.complete().defer("content_ids").latest()
        except RepositoryVersion.DoesNotExist:
            return None
    raise ValueError("Must be a repository version.")


def distinct_package_names_qs(content_qs):
    """One row per distinct ``name``, ordered for stable pagination."""
    return content_qs.order_by().values("name").distinct().order_by("name")


def assemble_package_index(content_qs, name_rows, repository_version):
    """One catalog row per package name, with one entry per stored version.

    Uniqueness is already ``(name, version, domain)``, so each stored version
    string is its own entry. ``1.0.0`` and ``1.0.0.rhlw-00001`` stay separate.
    Version strings are unchanged and ordered newest first.
    """
    if not name_rows or repository_version is None:
        return []

    names = [row["name"] for row in name_rows]
    by_name = defaultdict(list)
    for unit in content_qs.filter(name__in=names):
        by_name[unit.name].append(unit)

    result = []
    for row in name_rows:
        name = row["name"]
        versions = sorted(
            by_name.get(name, []),
            key=lambda unit: _version_sort_key(unit.version),
            reverse=True,
        )
        result.append(
            {
                "name": name,
                "versions": [{"version": unit.version} for unit in versions],
            }
        )
    return result
