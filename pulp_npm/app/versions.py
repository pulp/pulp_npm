"""Catalog version helpers with no Django imports.

CI unit tests can run with ``pytest -p no:pulpcore``. Import this module, not
``catalog``: ``catalog`` pulls in Django models and fails collection with
AppRegistryNotReady.
"""

import re

# Last dot-segment is a rebuild if it is letters, dash, rest of that segment.
# POSIX string shared with SQL REGEXP_REPLACE. Not hard-coded to "rhlw".
BUILD_SUFFIX_PATTERN = r"\.[a-zA-Z]+-[^.]+$"
BUILD_SUFFIX_RE = re.compile(BUILD_SUFFIX_PATTERN)

PACKAGE_INDEX_ORDERING_FIELDS = frozenset({"name", "last_updated"})
DEFAULT_PACKAGE_INDEX_ORDERING = ("name",)


def strip_build_suffix(version):
    """Return ``version`` with a trailing rebuild suffix removed, else unchanged.

    A rebuild is the last dot-segment matching ``BUILD_SUFFIX_PATTERN``.
    """
    if not version:
        return version
    return BUILD_SUFFIX_RE.sub("", version)


def rebuild_release(version):
    """Return the rebuild qualifier without the leading dot, or an empty string."""
    if not version:
        return ""
    base = strip_build_suffix(version)
    if version == base:
        return ""
    if version.startswith(base + "."):
        return version[len(base) + 1 :]
    return ""


def version_sort_key(version):
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


def normalize_package_index_ordering(raw_values):
    """Turn ``ordering`` query values into ``order_by`` arguments.

    Default is ``name``. Unknown fields raise ``ValueError``. ``last_updated``
    keeps ``name`` as a stable pagination tiebreaker.
    """
    fields = []
    for item in raw_values:
        if not item:
            continue
        for part in str(item).split(","):
            part = part.strip()
            if part:
                fields.append(part)

    if not fields:
        return list(DEFAULT_PACKAGE_INDEX_ORDERING)

    normalized = []
    seen = set()
    for field in fields:
        descending = field.startswith("-")
        name = field[1:] if descending else field
        if name not in PACKAGE_INDEX_ORDERING_FIELDS:
            raise ValueError(f"Unknown ordering field: '{name}'.")
        if name in seen:
            continue
        seen.add(name)
        normalized.append(f"-{name}" if descending else name)

    have = {term.lstrip("-") for term in normalized}
    if "name" not in have:
        normalized.append("name")
    return normalized
