# Browse the package catalog

The package list returns **one row per package name**. It defaults to the
repository's latest complete version. Pass `repository_version` (HREF or PRN)
to read an older snapshot. `{pulp_id}` is the repository UUID.

Scoped packages use the full name string (`@types/node`).

## List packages

```bash
http GET "${BASE_ADDR}/pulp/api/v3/repositories/npm/npm/${REPO_PK}/packages/?limit=10"
```

`count` is the number of distinct packages, not `(name, version)` units. Each
row is one package name. `versions` has one entry per stored version string,
newest first. `1.0.0` and `1.0.0.rhlw-00001` are separate entries.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "name": "hello",
      "versions": [
        {"version": "2.0.0"},
        {"version": "1.0.0.rhlw-00001"},
        {"version": "1.0.0"}
      ]
    }
  ]
}
```

Results are ordered by `name`. Within a package, versions are newest first.
Page with `limit` and `offset`. Pass `repository_version` when the list must
stay on one snapshot.
