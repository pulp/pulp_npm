import pytest

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
