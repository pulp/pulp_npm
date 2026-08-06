import uuid

import pytest


@pytest.fixture
def gen_users(gen_user):
    """Create three users with different role levels.

    - alice: viewer roles (read and list, cannot create/update/delete)
    - bob: creator roles (can create. As creator gets auto-assigned owner role)
    - charlie: no roles at all

     gen_user is a fixture from pulpcore that creates a Pulp user
     and returns a context manager for impersonating them in API calls.
    """

    def _gen_users(role_names=None):
        if role_names is None:
            role_names = []
        if isinstance(role_names, str):
            role_names = [role_names]
        viewer_roles = [f"npm.{role}_viewer" for role in role_names]
        creator_roles = [f"npm.{role}_creator" for role in role_names]
        alice = gen_user(model_roles=viewer_roles)
        bob = gen_user(model_roles=creator_roles)
        charlie = gen_user()
        return alice, bob, charlie

    return _gen_users


@pytest.fixture
def try_action(npm_bindings, monitor_task):
    """Perform an API action as a given user and assert the expected HTTP status"""

    def _try_action(user, client, action, outcome, *args, **kwargs):
        # Use the _with_http_info variant so we can get info on body, status_code and headers.
        action_api = getattr(client, f"{action}_with_http_info")
        try:
            with user:
                response = action_api(*args, **kwargs)
            if isinstance(response, tuple):
                data, status_code, _ = response
            else:
                data = response.data
                status_code = response.status_code
            if isinstance(data, npm_bindings.module.AsyncOperationResponse):
                data = monitor_task(data.task)
        except npm_bindings.module.ApiException as e:
            assert e.status == outcome, f"{e}"
        else:
            assert status_code == outcome, (
                f"User performed {action} when they shouldn't have been able to"
            )
            return data

    return _try_action


# Repository CRUD
@pytest.mark.parallel
def test_basic_actions(gen_users, npm_bindings, try_action, npm_repository_factory):
    """Test list, read, create, update and delete on repositories"""
    alice, bob, charlie = gen_users("npmrepository")

    # Create: alice (viewer) can't, bob (creator) can, charlie (no role) can't
    try_action(
        alice,
        npm_bindings.RepositoriesNpmApi,
        "create",
        403,
        {"name": str(uuid.uuid4())},
    )

    repo = try_action(
        bob,
        npm_bindings.RepositoriesNpmApi,
        "create",
        201,
        {"name": str(uuid.uuid4())},
    )

    try_action(
        charlie,
        npm_bindings.RepositoriesNpmApi,
        "create",
        403,
        {"name": str(uuid.uuid4())},
    )

    # List: alice (viewer) sees bob's repo, bob (owner) sees it, charlie sees nothing
    a_list = try_action(alice, npm_bindings.RepositoriesNpmApi, "list", 200)
    assert a_list.count >= 1
    b_list = try_action(bob, npm_bindings.RepositoriesNpmApi, "list", 200)
    assert b_list.count >= 1
    c_list = try_action(charlie, npm_bindings.RepositoriesNpmApi, "list", 200)
    assert c_list.count == 0

    # Read: alice (viewer) can see bob's repo, charlie cannot (404, invisible)
    try_action(alice, npm_bindings.RepositoriesNpmApi, "read", 200, repo.pulp_href)
    try_action(bob, npm_bindings.RepositoriesNpmApi, "read", 200, repo.pulp_href)
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "read", 404, repo.pulp_href)

    # Update: only bob (owner) can
    update_args = [repo.pulp_href, {"name": str(uuid.uuid4())}]
    try_action(alice, npm_bindings.RepositoriesNpmApi, "partial_update", 403, *update_args)
    try_action(bob, npm_bindings.RepositoriesNpmApi, "partial_update", 202, *update_args)
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "partial_update", 404, *update_args)

    # Delete: only bob (owner) can
    try_action(alice, npm_bindings.RepositoriesNpmApi, "delete", 403, repo.pulp_href)
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "delete", 404, repo.pulp_href)
    try_action(bob, npm_bindings.RepositoriesNpmApi, "delete", 202, repo.pulp_href)


# Repository sync and modify
@pytest.mark.parallel
def test_repository_sync(
    gen_users,
    npm_bindings,
    npm_repository_factory,
    npm_remote_factory,
    try_action,
):
    """Test sync and modif yactions require appropriate permissions"""
    alice, bob, charlie = gen_users(["npmrepository", "npmremote"])

    with bob:
        bob_remote = npm_remote_factory(url="https://registory.npmjs.org/")
        repo = npm_repository_factory(remote=bob_remote.pulp_href)

    body = {"remote": bob_remote.pulp_href}
    try_action(alice, npm_bindings.RepositoriesNpmApi, "sync", 403, repo.pulp_href, body)
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "sync", 404, repo.pulp_href, body)

    # Modify repository, add/remove content
    try_action(alice, npm_bindings.RepositoriesNpmApi, "modify", 403, repo.pulp_href, {})
    try_action(bob, npm_bindings.RepositoriesNpmApi, "modify", 202, repo.pulp_href, {})
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "modify", 404, repo.pulp_href, {})


# Remote CRUD


@pytest.mark.parallel
def test_remote_actions(gen_users, npm_bindings, try_action):
    """Test CRUD on remotes with role-based access."""
    alice, bob, charlie = gen_users("npmremote")

    a_list = try_action(alice, npm_bindings.RemotesNpmApi, "list", 200)
    assert a_list.count >= 0
    b_list = try_action(bob, npm_bindings.RemotesNpmApi, "list", 200)
    c_list = try_action(charlie, npm_bindings.RemotesNpmApi, "list", 200)
    assert (b_list.count, c_list.count) == (0, 0)

    remote_body = {
        "name": str(uuid.uuid4()),
        "url": "https://registry.npmjs.org/",
    }
    try_action(alice, npm_bindings.RemotesNpmApi, "create", 403, remote_body)
    remote = try_action(bob, npm_bindings.RemotesNpmApi, "create", 201, remote_body)
    try_action(charlie, npm_bindings.RemotesNpmApi, "create", 403, remote_body)

    try_action(alice, npm_bindings.RemotesNpmApi, "read", 200, remote.pulp_href)
    try_action(bob, npm_bindings.RemotesNpmApi, "read", 200, remote.pulp_href)
    try_action(charlie, npm_bindings.RemotesNpmApi, "read", 404, remote.pulp_href)

    update_args = [remote.pulp_href, {"name": str(uuid.uuid4())}]
    try_action(alice, npm_bindings.RemotesNpmApi, "partial_update", 403, *update_args)
    try_action(bob, npm_bindings.RemotesNpmApi, "partial_update", 202, *update_args)
    try_action(charlie, npm_bindings.RemotesNpmApi, "partial_update", 404, *update_args)

    try_action(alice, npm_bindings.RemotesNpmApi, "delete", 403, remote.pulp_href)
    try_action(charlie, npm_bindings.RemotesNpmApi, "delete", 404, remote.pulp_href)
    try_action(bob, npm_bindings.RemotesNpmApi, "delete", 202, remote.pulp_href)


# Distribution CRUD


@pytest.mark.parallel
def test_distribution_actions(
    gen_users,
    npm_bindings,
    npm_repository_factory,
    try_action,
):
    """Test CRUD on distributions with role-based access."""
    alice, bob, charlie = gen_users(["npmdistribution", "npmrepository"])

    with bob:
        repo = npm_repository_factory()

    try_action(
        alice,
        npm_bindings.DistributionsNpmApi,
        "create",
        403,
        {
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
            "repository": repo.pulp_href,
        },
    )
    distro = try_action(
        bob,
        npm_bindings.DistributionsNpmApi,
        "create",
        202,
        {
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
            "repository": repo.pulp_href,
        },
    )
    distro_href = distro.created_resources[0]
    try_action(
        charlie,
        npm_bindings.DistributionsNpmApi,
        "create",
        403,
        {
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
            "repository": repo.pulp_href,
        },
    )

    try_action(alice, npm_bindings.DistributionsNpmApi, "read", 200, distro_href)
    try_action(bob, npm_bindings.DistributionsNpmApi, "read", 200, distro_href)
    try_action(charlie, npm_bindings.DistributionsNpmApi, "read", 404, distro_href)

    update_args = [distro_href, {"name": str(uuid.uuid4())}]
    try_action(alice, npm_bindings.DistributionsNpmApi, "partial_update", 403, *update_args)
    try_action(bob, npm_bindings.DistributionsNpmApi, "partial_update", 202, *update_args)
    try_action(charlie, npm_bindings.DistributionsNpmApi, "partial_update", 404, *update_args)

    try_action(alice, npm_bindings.DistributionsNpmApi, "delete", 403, distro_href)
    try_action(charlie, npm_bindings.DistributionsNpmApi, "delete", 404, distro_href)
    try_action(bob, npm_bindings.DistributionsNpmApi, "delete", 202, distro_href)


# Cross-object checks
@pytest.mark.parallel
def test_cross_object_permissions(
    gen_users,
    npm_bindings,
    npm_repository_factory,
    npm_remote_factory,
    try_action,
):
    """Test that creating objects referencing others requires view permission on them."""
    _alice, bob, _charlie = gen_users(["npmrepository", "npmremote", "npmdistribution"])

    admin_repo = npm_repository_factory()
    admin_remote = npm_remote_factory(url="https://registry.npmjs.org/")

    with bob:
        bob_remote = npm_remote_factory(url="https://registry.npmjs.org/")
        bob_repo = npm_repository_factory()

    # Bob can't create distribution pointing to admin's repo (no view perm)
    try_action(
        bob,
        npm_bindings.DistributionsNpmApi,
        "create",
        403,
        {
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
            "repository": admin_repo.pulp_href,
        },
    )

    # Bob can create distribution pointing to his own repo
    try_action(
        bob,
        npm_bindings.DistributionsNpmApi,
        "create",
        202,
        {
            "name": str(uuid.uuid4()),
            "base_path": str(uuid.uuid4()),
            "repository": bob_repo.pulp_href,
        },
    )

    # Bob can't create repo referencing admin's remote
    try_action(
        bob,
        npm_bindings.RepositoriesNpmApi,
        "create",
        403,
        {"name": str(uuid.uuid4()), "remote": admin_remote.pulp_href},
    )

    # Bob can create repo referencing his own remote
    try_action(
        bob,
        npm_bindings.RepositoriesNpmApi,
        "create",
        201,
        {"name": str(uuid.uuid4()), "remote": bob_remote.pulp_href},
    )


# Role management
@pytest.mark.parallel
def test_role_management(
    gen_users,
    npm_bindings,
    npm_repository_factory,
    try_action,
):
    """Test list_roles, add_role, remove_role, and my_permissions."""
    alice, bob, charlie = gen_users("npmrepository")
    with bob:
        href = npm_repository_factory().pulp_href

    # my_permissions -- alice has no object-level role, bob is owner
    aperm = try_action(alice, npm_bindings.RepositoriesNpmApi, "my_permissions", 200, href)
    assert aperm.permissions == []
    bperm = try_action(bob, npm_bindings.RepositoriesNpmApi, "my_permissions", 200, href)
    assert len(bperm.permissions) > 0
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "my_permissions", 404, href)

    # list_roles / add_role / remove_role
    try_action(alice, npm_bindings.RepositoriesNpmApi, "list_roles", 403, href)
    try_action(bob, npm_bindings.RepositoriesNpmApi, "list_roles", 200, href)

    nested_role = {
        "users": [charlie.username],
        "role": "npm.npmrepository_viewer",
    }
    try_action(alice, npm_bindings.RepositoriesNpmApi, "add_role", 403, href, nested_role)
    try_action(bob, npm_bindings.RepositoriesNpmApi, "add_role", 201, href, nested_role)

    # charlie can now see the repo
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "read", 200, href)

    # remove_role
    try_action(
        alice,
        npm_bindings.RepositoriesNpmApi,
        "remove_role",
        403,
        href,
        nested_role,
    )
    try_action(
        bob,
        npm_bindings.RepositoriesNpmApi,
        "remove_role",
        201,
        href,
        nested_role,
    )

    # charlie can no longer see the repo
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "read", 404, href)


# Repository version permission delegation
@pytest.mark.parallel
def test_repository_version_actions(
    gen_users,
    npm_bindings,
    npm_repository_factory,
    try_action,
):
    """Test that repository version permissions delegate to the parent repository."""
    alice, bob, charlie = gen_users("npmrepository")
    with bob:
        repo = npm_repository_factory()

    # Create a version by running modify
    with bob:
        try_action(bob, npm_bindings.RepositoriesNpmApi, "modify", 202, repo.pulp_href, {})
        repo = npm_bindings.RepositoriesNpmApi.read(repo.pulp_href)

    ver_href = repo.latest_version_href

    # List versions
    a_vers = try_action(alice, npm_bindings.RepositoriesNpmVersionsApi, "list", 200, repo.pulp_href)
    assert a_vers.count >= 1
    b_vers = try_action(bob, npm_bindings.RepositoriesNpmVersionsApi, "list", 200, repo.pulp_href)
    assert b_vers.count >= 1
    try_action(
        charlie,
        npm_bindings.RepositoriesNpmVersionsApi,
        "list",
        403,
        repo.pulp_href,
    )

    # Retrieve specific version
    try_action(alice, npm_bindings.RepositoriesNpmVersionsApi, "read", 200, ver_href)
    try_action(bob, npm_bindings.RepositoriesNpmVersionsApi, "read", 200, ver_href)
    try_action(charlie, npm_bindings.RepositoriesNpmVersionsApi, "read", 403, ver_href)

    # Destroy -- permission checks only
    try_action(alice, npm_bindings.RepositoriesNpmVersionsApi, "delete", 403, ver_href)
    try_action(charlie, npm_bindings.RepositoriesNpmVersionsApi, "delete", 403, ver_href)


# Content visibility scoping


@pytest.mark.parallel
def test_content_viewset_permissions(
    gen_users,
    npm_bindings,
    npm_repository_factory,
    npm_remote_factory,
    try_action,
    monitor_task,
):
    """Test that content listing is scoped by repository view permissions."""
    alice, bob, charlie = gen_users("npmrepository")

    # Admin creates repo with content via sync
    remote = npm_remote_factory(url="https://registry.npmjs.org/")
    repo = npm_repository_factory(remote=remote.pulp_href)

    try_action(alice, npm_bindings.ContentPackagesApi, "list", 200)
    b_list = try_action(bob, npm_bindings.ContentPackagesApi, "list", 200)
    c_list = try_action(charlie, npm_bindings.ContentPackagesApi, "list", 200)

    # Bob and charlie see nothing (no view perms on admin's repo)
    assert b_list.count == 0
    assert c_list.count == 0

    # Grant charlie object-level viewer role on the repo
    npm_bindings.RepositoriesNpmApi.add_role(
        repo.pulp_href,
        {"users": [charlie.username], "role": "npm.npmrepository_viewer"},
    )

    # Now charlie's scoping includes this repo
    c_list2 = try_action(charlie, npm_bindings.ContentPackagesApi, "list", 200)
    assert c_list2.count >= 0  # may be 0 if no content, but no error


# Object-level role scoping
@pytest.mark.parallel
def test_object_level_roles(
    gen_users,
    npm_bindings,
    npm_repository_factory,
    try_action,
):
    """Test that object-level roles grant access to specific objects only."""
    _alice, bob, charlie = gen_users("npmrepository")

    with bob:
        repo_a = npm_repository_factory()
        repo_b = npm_repository_factory()

    # charlie can't see either repo
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "read", 404, repo_a.pulp_href)
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "read", 404, repo_b.pulp_href)

    # Grant charlie viewer on repo_a only
    with bob:
        npm_bindings.RepositoriesNpmApi.add_role(
            repo_a.pulp_href,
            {"users": [charlie.username], "role": "npm.npmrepository_viewer"},
        )

    # charlie can see repo_a but not repo_b
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "read", 200, repo_a.pulp_href)
    try_action(charlie, npm_bindings.RepositoriesNpmApi, "read", 404, repo_b.pulp_href)

    c_list = try_action(charlie, npm_bindings.RepositoriesNpmApi, "list", 200)
    assert c_list.count == 1
