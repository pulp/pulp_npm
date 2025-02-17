# Pull-Through Cache

The pull-through cache feature allows Pulp to act as a cache for any package from a remote source.

!!! warning
    Support for pull-through caching is provided as a tech preview in Pulp 3.
    Functionality may not work or may be incomplete. Also, backwards compatibility when upgrading
    is not guaranteed.


=== "Create remote bar"
  ```bash
  curl -X POST $BASE_ADDR/pulp/pulp/api/v3/remotes/npm/npm/ -d '{"name": "bar", "url": "http://some.url/somewhere/"}' -H 'Content-Type: application/json'
  ```

=== "Create a distribution"
  ```bash
  curl -X POST $BASE_ADDR/pulp/api/v3/distributions/npm/npm/ -d '{"name": "baz", "base_path": "foo", "remote": $REMOTE_HREF"}' -H 'Content-Type: application/json'
  ```

=== "Point your CLI to the distribution"
  ```bash
  npm install --registry $BASE_ADDR/pulp/content/{domain}/foo react@19.0.0
  ```
