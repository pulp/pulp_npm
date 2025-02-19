# Publish and Host

This section assumes that you have a repository with content in it. To do this, see the
[sync](site:/pulp_npm/docs/user/guides/sync.md).

## Create a Publication

Publications contain extra settings for how to publish.

=== "Create a publication"
```bash
curl -X POST $BASE_ADDR/pulp/{domain}/api/v3/publications/npm/npm/ -d '{"name": "bar"}' -H 'Content-Type: application/json'
```

=== "Response"
```json
{
    "pulp_href": "/pulp/{domain}/api/v3/publications/npm/npm/bar/",
}
```

## Host a Publication (Create a Distribution)

To host a publication, (which makes it consumable by a package manager),
users create a distribution which will serve the associated publication 
at `/pulp/content/{domain}/{distribution.base_path}`:

=== "Create a distribution"
```bash
curl -X POST $BASE_ADDR/pulp/{domain}/api/v3/distributions/npm/npm/ -d '{"name": "baz", "base_path": "foo", "publication": "$BASE_ADDR/publications/5fcb3a98-1bd1-445f-af94-801a1d563b9f/"}' -H 'Content-Type: application/json'
```

=== "Response"
```json
{
    "pulp_href": "/pulp/{domain}/api/v3/distributions/2ac41454-931c-41c7-89eb-a9d11e19b02a/",
}
```
