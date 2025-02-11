# coding=utf-8
"""Tests that sync npm plugin repositories."""
import pytest
import unittest
import uuid

from pulpcore.client.pulp_npm import RepositorySyncURL

from pulp_smash import api, cli, config
from pulp_smash.exceptions import TaskReportError
from pulp_smash.pulp3.constants import MEDIA_PATH
from pulp_smash.pulp3.utils import (
    gen_repo,
    sync,
)

from pulp_npm.tests.functional.constants import (
    NPM_INVALID_FIXTURE_URL,
    NPM_REMOTE_PATH,
    NPM_REPO_PATH,
)
from pulp_npm.tests.functional.utils import gen_npm_remote


class BasicSyncTestCase(unittest.TestCase):
    """Sync a repository with the npm plugin."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)

    # This test may not make sense for all plugins, but is likely to be useful
    # for most. Check that it makes sense for yours before enabling it.
    @unittest.skip("FIXME: plugin writer action required")
    def test_file_decriptors(self):
        """Test whether file descriptors are closed properly.

        This test targets the following issue:

        `Pulp #4073 <https://pulp.plan.io/issues/4073>`_

        Do the following:

        1. Check if 'lsof' is installed. If it is not, skip this test.
        2. Create and sync a repo.
        3. Run the 'lsof' command to verify that files in the
           path ``/var/lib/pulp/`` are closed after the sync.
        4. Assert that issued command returns `0` opened files.
        """
        cli_client = cli.Client(self.cfg, cli.echo_handler)

        # check if 'lsof' is available
        if cli_client.run(("which", "lsof")).returncode != 0:
            raise unittest.SkipTest("lsof package is not present")

        repo = self.client.post(NPM_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo["pulp_href"])

        remote = self.client.post(NPM_REMOTE_PATH, gen_npm_remote())
        self.addCleanup(self.client.delete, remote["pulp_href"])

        sync(self.cfg, remote, repo)

        cmd = "lsof -t +D {}".format(MEDIA_PATH).split()
        response = cli_client.run(cmd).stdout
        self.assertEqual(len(response), 0, response)


# Implement sync support before enabling this test.
@unittest.skip("FIXME: plugin writer action required")
class SyncInvalidTestCase(unittest.TestCase):
    """Sync a repository with a given url on the remote."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.json_handler)

    def test_invalid_url(self):
        """Sync a repository using a remote url that does not exist.

        Test that we get a task failure. See :meth:`do_test`.
        """
        context = self.do_test("http://i-am-an-invalid-url.com/invalid/")
        self.assertIsNotNone(context.exception.task["error"]["description"])

    # Provide an invalid repository and specify keywords in the anticipated error message
    @unittest.skip("FIXME: Plugin writer action required.")
    def test_invalid_npm_content(self):
        """Sync a repository using an invalid plugin_content repository.

        Assert that an exception is raised, and that error message has
        keywords related to the reason of the failure. See :meth:`do_test`.
        """
        context = self.do_test(NPM_INVALID_FIXTURE_URL)
        for key in ("mismatched", "empty"):
            self.assertIn(key, context.exception.task["error"]["description"])

    def do_test(self, url):
        """Sync a repository given ``url`` on the remote."""
        repo = self.client.post(NPM_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo["pulp_href"])

        body = gen_npm_remote(url=url)
        remote = self.client.post(NPM_REMOTE_PATH, body)
        self.addCleanup(self.client.delete, remote["pulp_href"])

        with self.assertRaises(TaskReportError) as context:
            sync(self.cfg, remote, repo)
        return context


@pytest.mark.parallel
def test_sync_endpoint_demanding_remote_payload(
    npm_bindings, gen_object_with_cleanup, monitor_task
):
    remote = gen_object_with_cleanup(
        npm_bindings.RemotesNpmApi,
        {"name": str(uuid.uuid4()), "url": "https://registry.npmjs.org/commander/4.0.1"},
    )
    repository = gen_object_with_cleanup(
        npm_bindings.RepositoriesNpmApi, {"name": str(uuid.uuid4()), "remote": remote.pulp_href}
    )

    versions = npm_bindings.RepositoriesNpmVersionsApi.list(repository.pulp_href)
    assert versions.count == 1

    sync_url = RepositorySyncURL()
    monitor_task(npm_bindings.RepositoriesNpmApi.sync(repository.pulp_href, sync_url).task)

    new_versions = npm_bindings.RepositoriesNpmVersionsApi.list(repository.pulp_href)
    assert new_versions.count > 1
