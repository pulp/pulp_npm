# Synchronize a Repository

Users can populate their repositories with content from an external sources by syncing
their repository.

## Create a Repository

Start by creating a new repository named "foo":
```bash
curl -X POST $BASE_ADDR/pulp/api/v3/repositories/npm/npm/ -d '{"name": "foo"}' -H 'Content-Type: application/json'
```

=== "Response"
```json
{
    "pulp_href": "/pulp/{domain}/api/v3/repositories/npm/npm/9b19ceb7-11e1-4309-9f97-bcbab2ae38b6/",
    "description": "",
    "name": "foo"
}
```

## Create a Remote

Creating a remote object informs Pulp about an external content source.

=== "Create remote bar"
```bash
curl -X POST $BASE_ADDR/pulp/pulp/api/v3/remotes/npm/npm/ -d '{"name": "bar", "url": "http://some.url/somewhere/"}' -H 'Content-Type: application/json'
```

=== "Response"
```json
{
    "pulp_href": /pulp/{domain}/api/v3/remotes/npm/npm/9c757d65-3007-4884-ac5b-c2fd93873289/"
}
```


## Sync repository foo with remote bar

Use the remote object to kick off a synchronize task by specifying the repository to
sync with. You are telling pulp to fetch content from the remote and add to the repository:

=== "Sync repository foo with remote bar"
```bash
curl -X POST $BASE_ADDR/pulp/{domain}/api/v3/repositories/npm/npm/9b19ceb7-11e1-4309-9f97-bcbab2ae38b6/sync/' remote=$REMOTE_HREF
```

=== "Response"
```json
{
    "pulp_href": "http://localhost:24817/pulp/{domain}/api/v3/tasks/3896447a-2799-4818-a3e5-df8552aeb903/",
    "task_id": "3896447a-2799-4818-a3e5-df8552aeb903"
}
```

You can follow the progress of the task with a GET request to the task href. Notice that when the
synchronize task completes, it creates a new version, which is specified in `created_resources`:

=== "Follow the progress of the task"
```bash
curl -X GET $BASE_ADDR/pulp/{domain}/api/v3/tasks/3896447a-2799-4818-a3e5-df8552aeb903/
```

=== "Response"
```json
{
    "pulp_href": "/pulp/{domain}/api/v3/tasks/3896447a-2799-4818-a3e5-df8552aeb903/",
    "pulp_created": "2018-05-01T17:17:46.558997Z",
    "created_resources": [
        "/pulp/{domain}/api/v3/repositories/npm/npm/9b19ceb7-11e1-4309-9f97-bcbab2ae38b6/versions/6/"
    ],
    "error": null,
    "finished_at": "2018-05-01T17:17:47.149123Z",
    "parent": null,
    "progress_reports": [
        {
            "done": 0,
            "message": "Add Content",
            "state": "completed",
            "suffix": "",
            "total": 0
        },
        {
            "done": 0,
            "message": "Remove Content",
            "state": "completed",
            "suffix": "",
            "total": 0
        }
    ],
    "spawned_tasks": [],
    "started_at": "2018-05-01T17:17:46.644801Z",
    "state": "completed",
    "worker": "/pulp/{domain}/api/v3/workers/eaffe1be-111a-421d-a127-0b8fa7077cf7/"
}
```
