# Browse the package catalog

Pulp CLI commands for these endpoints are generated from the OpenAPI spec in a separate package; until that is updated, use HTTP.

The content list (`/pulp/api/v3/content/npm/packages/`) returns **one row per `(name, version)`**. For catalog UIs and automation that need **one row per package name**, plus repository metrics, use the repository package index.

These endpoints default to the **latest complete repository version**. `{pulp_id}` is the repository UUID. Pass `repository_version` (HREF or PRN) to read a specific version of that repository.

Scoped packages use the full name string (`@types/node`). There is no separate scope field.

## List packages

```bash
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/repositories/npm/npm/${REPO_PK}/packages/?limit=10"
```

Pagination `count` is the number of **distinct package names**, not `(name, version)` units.

Each row includes both a simple version list and per-version metadata:

```json
{
  "name": "lodash",
  "last_updated": "2026-08-11T08:00:00.000000Z",
  "versions": ["4.17.21", "1.0.0"],
  "latest_releases": [
    {
      "version": "4.17.21",
      "release": "rhlw-00001",
      "created_at": "2026-08-11T08:00:00.000000Z"
    },
    {
      "version": "1.0.0",
      "release": "",
      "created_at": "2026-08-10T10:45:08.099362Z"
    }
  ]
}
```

`set(versions)` is always the same as `set(latest_releases[].version)`. Both lists are newest-first using numeric-token version order (`1.10` before `1.9` before `1.2`). There is one `latest_releases` entry per **logical version** (after stripping a trailing rebuild suffix `\.[a-zA-Z]+-[^.]+$` at the end of `version`: a `.`, letters, a `-`, then the rest of that last segment).

`1.0.0.rhlw-00001`, `1.0.0.rhlw-00001-n0001`, and `1.0.0.lw-1` share base `1.0.0`. Versions that are not that last-segment shape are unchanged: `1.0.0-anything`, `1.0.0.anything`. `1.0.10` is a different version than `1.0.1`.

`version` is that base. `release` is the stripped suffix without the leading dot (`rhlw-00001` or `rhlw-00001-n0001`), otherwise empty.

`created_at` is when that logical version entered the repository: `RepositoryContent.pulp_created` of the selected newest rebuild, falling back to the content unit's `pulp_created`.

`last_updated` is when the **package** was last updated in this repository version: the latest `RepositoryContent.pulp_created` among **all** Package units for that `name` (any rebuild), falling back to the content unit's `pulp_created`. A rebuild of an older version uploaded yesterday updates `last_updated` even if a newer version number already exists.

There is no `…/builds/` endpoint. Rebuilds collapse via `collapse_builds` on the content list, or load on Get with exact `version=`.

### Ordering

Default order is `name`. Pass `ordering` to change it:

```bash
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/repositories/npm/npm/${REPO_PK}/packages/" \
  ordering==name
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/repositories/npm/npm/${REPO_PK}/packages/" \
  ordering==-last_updated
```

Allowed fields: `name`, `last_updated`. Prefix with `-` for descending. `last_updated` uses `name` as a stable pagination tiebreaker. Unknown fields return 400.

### Name search

```bash
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/repositories/npm/npm/${REPO_PK}/packages/" \
  name__istartswith==@types/
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/repositories/npm/npm/${REPO_PK}/packages/" \
  name__icontains==types
```

`name__istartswith` and `name__icontains` are case-insensitive (`ILIKE`) on the full name, including `@scope/…`. Prefix and substring search belong on this index, not on the flat content list.

## Repository metrics

```bash
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/repositories/npm/npm/${REPO_PK}/metrics/"
```

```json
{
  "package_count": 3,
  "version_count": 4,
  "build_count": 5
}
```

Counts use **Package** units in that repository version (the same identity as PackageList):

| Field | Identity |
|-------|----------|
| `package_count` | distinct `name` |
| `version_count` | distinct `(name, base_version)` after rebuild-suffix strip |
| `build_count` | distinct `(name, full version)` |

Until rebuild suffixes exist, `version_count` equals `build_count`.

## List versions of a package

Use the existing content API. `collapse_builds=true` keeps one unit per logical version (`name` + `base_version`), the one with the latest `pulp_created`. Do not nest rebuilds on this list. Clients can drain Pulp `next` if the page is full. Until Lightwell npm rebuilds exist, collapse is a no-op (identity).

```bash
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/content/npm/packages/" \
  name==lodash \
  collapse_builds==true \
  repository_version=="${LATEST_VERSION_HREF}"
```

Every content row includes `base_version` (stripped version; equal to `version` when there is no rebuild suffix).

## Get one version

Omit `collapse_builds`. Filter with exact `name` and `version`.

```bash
http GET "${BASE_ADDR}/pulp/{domain}/api/v3/content/npm/packages/" \
  name==lodash \
  version==4.17.21
```

`name` still supports `exact` and `in`. `version` is exact only.
