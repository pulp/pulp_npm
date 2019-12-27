Publish and Host
================

This section assumes that you have a repository with content in it. To do this, see the
:doc:`sync` or :doc:`upload` documentation.

Create a Publisher
------------------

Publishers contain extra settings for how to publish. You can use a npm publisher on any
repository that contains npm content::

$ http POST $BASE_ADDR/pulp/api/v3/publishers/npm/npm/ name=bar

Response::

    {
        "pulp_href": "http://localhost:24817/pulp/api/v3/publishers/npm/npm/bar/",
        ...
    }


Publish a repository with a publisher
-------------------------------------

Use the remote object to kick off a publish task by specifying the repository version to publish.
Alternatively, you can specify repository, which will publish the latest version.

The result of a publish is a publication, which contains all the information needed for a external package manager
like ``pip`` or ``apt-get`` to use. Publications are not consumable until they are hosted by a distribution::

$ http POST $BASE_ADDR/pulp/api/v3/publishers/npm/npm/1/publish/ repository=$BASE_ADDR/pulp/api/v3/repositories/npm/npm/9b19ceb7-11e1-4309-9f97-bcbab2ae38b6/

Response::

    [
        {
            "pulp_href": "http://localhost:24817/pulp/api/v3/tasks/fd4cbecd-6c6a-4197-9cbe-4e45b0516309/",
            "task_id": "fd4cbecd-6c6a-4197-9cbe-4e45b0516309"
        }
    ]

Host a Publication (Create a Distribution)
--------------------------------------------

To host a publication, (which makes it consumable by a package manager), users create a distribution which
will serve the associated publication at ``/pulp/content/<distribution.base_path>``::

$ http POST $BASE_ADDR/pulp/api/v3/distributions/npm/npm/ name='baz' base_path='foo' publication=$BASE_ADDR/publications/5fcb3a98-1bd1-445f-af94-801a1d563b9f/

Response::

    {
        "pulp_href": "http://localhost:24817/pulp/api/v3/distributions/2ac41454-931c-41c7-89eb-a9d11e19b02a/",
       ...
    }

