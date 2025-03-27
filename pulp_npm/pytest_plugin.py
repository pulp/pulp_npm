import pytest
import uuid
from collections import defaultdict

from pulpcore.tests.functional.utils import BindingsNamespace


@pytest.fixture(scope="session")
def npm_bindings(_api_client_set, bindings_cfg):
    """
    A namespace providing preconfigured pulp_npm api clients.

    e.g. `npm.RepositoriesNpmApi.list()`.
    """
    from pulpcore.client import pulp_npm as npm_bindings_module

    api_client = npm_bindings_module.ApiClient(bindings_cfg)
    _api_client_set.add(api_client)
    yield BindingsNamespace(npm_bindings_module, api_client)
    _api_client_set.remove(api_client)


@pytest.fixture(scope="class")
def npm_repository_factory(npm_bindings, gen_object_with_cleanup):
    def _npm_repository_factory(remote=None, pulp_domain=None, **body):
        name = body.get("name") or str(uuid.uuid4())
        body.update({"name": name})
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        return gen_object_with_cleanup(npm_bindings.RepositoriesNpmApi, body, **kwargs)

    return _npm_repository_factory


@pytest.fixture(scope="class")
def npm_remote_factory(npm_bindings, gen_object_with_cleanup):
    def _npm_remote_factory(url=None, policy="immediate", pulp_domain=None, **body):
        name = body.get("name") or str(uuid.uuid4())
        body.update({"url": str(url), "policy": policy, "name": name})
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        return gen_object_with_cleanup(npm_bindings.RemotesNpmApi, body, **kwargs)

    return _npm_remote_factory


@pytest.fixture(scope="class")
def npm_distribution_factory(npm_bindings, gen_object_with_cleanup):
    def _npm_distribution_factory(pulp_domain=None, **body):
        data = {"base_path": str(uuid.uuid4()), "name": str(uuid.uuid4())}
        data.update(body)
        kwargs = {}
        if pulp_domain:
            kwargs["pulp_domain"] = pulp_domain
        return gen_object_with_cleanup(npm_bindings.DistributionsNpmApi, data, **kwargs)

    return _npm_distribution_factory


@pytest.fixture(scope="function")
def npm_repo(npm_repository_factory):
    return npm_repository_factory()


@pytest.fixture(scope="function")
def npm_remote(npm_remote_factory):
    return npm_remote_factory()


@pytest.fixture
def get_npm_content_paths(npm_bindings):
    """Build closure for fetching content from a repository.

    :returns: A closure which returns content.
    """

    def _get_npm_content_paths(repo, version_href=None):
        """Read the content units of a given repository.

        :param repo: An instance of NpmRepository.
        :param version_href: The repository version to read. If none, read the
            latest repository version.
        :returns: A list of information about the content units present in a
            given repository version.
        """
        version_href = version_href or repo.latest_version_href

        if version_href is None:
            # Repository has no latest version, and therefore no content.
            return defaultdict(list)

        repo_version = npm_bindings.RepositoriesNpmVersionsApi.read(version_href)

        content = npm_bindings.ContentPackagesApi.list(
            repository_version=repo_version.pulp_href
        ).results

        return [content_unit.relative_path for content_unit in content]

    return _get_npm_content_paths
