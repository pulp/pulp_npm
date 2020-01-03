# coding=utf-8
"""Utilities for tests for the npm plugin."""
from functools import partial
from unittest import SkipTest

from pulp_smash import api, selectors
from pulp_smash.pulp3.utils import (
    gen_remote,
    gen_repo,
    get_content,
    require_pulp_3,
    require_pulp_plugins,
    sync,
)

from pulp_npm.tests.functional.constants import (
    NPM_CONTENT_NAME,
    NPM_CONTENT_PATH,
    NPM_FIXTURE_URL,
    NPM_REMOTE_PATH,
    NPM_REPO_PATH,
)


def set_up_module():
    """Skip tests Pulp 3 isn't under test or if pulp_npm isn't installed."""
    require_pulp_3(SkipTest)
    require_pulp_plugins({"pulp_npm"}, SkipTest)


def gen_npm_remote(url=NPM_FIXTURE_URL, **kwargs):
    """Return a semi-random dict for use in creating a npm Remote.

    :param url: The URL of an external content source.
    """
    # FIXME: Add any fields specific to a npm remote here
    return gen_remote(url, **kwargs)


def get_npm_content_paths(repo, version_href=None):
    """Return the relative path of content units present in a npm repository.

    :param repo: A dict of information about the repository.
    :param version_href: The repository version to read.
    :returns: A list with the paths of units present in a given repository.
    """
    # FIXME: The "relative_path" is actually a file path and name
    # It's just an example -- this needs to be replaced with an implementation that works
    # for repositories of this content type.
    return [
        content_unit["relative_path"]
        for content_unit in get_content(repo, version_href)[NPM_CONTENT_NAME]
    ]


def gen_npm_content_attrs(artifact):
    """Generate a dict with content unit attributes.

    :param artifact: A dict of info about the artifact.
    :returns: A semi-random dict for use in creating a content unit.
    """
    # FIXME: Add content specific metadata here.
    return {"_artifact": artifact["pulp_href"]}


def populate_pulp(cfg, url=NPM_FIXTURE_URL):
    """Add npm contents to Pulp.

    :param pulp_smash.config.PulpSmashConfig: Information about a Pulp application.
    :param url: The npm repository URL. Defaults to
        :data:`pulp_smash.constants.NPM_FIXTURE_URL`
    :returns: A list of dicts, where each dict describes one npm content in Pulp.
    """
    client = api.Client(cfg, api.json_handler)
    remote = {}
    repo = {}
    try:
        remote.update(client.post(NPM_REMOTE_PATH, gen_npm_remote(url)))
        repo.update(client.post(NPM_REPO_PATH, gen_repo()))
        sync(cfg, remote, repo)
    finally:
        if remote:
            client.delete(remote["pulp_href"])
        if repo:
            client.delete(repo["pulp_href"])
    return client.get(NPM_CONTENT_PATH)["results"]


skip_if = partial(selectors.skip_if, exc=SkipTest)  # pylint:disable=invalid-name
"""The ``@skip_if`` decorator, customized for unittest.

:func:`pulp_smash.selectors.skip_if` is test runner agnostic. This function is
identical, except that ``exc`` has been set to ``unittest.SkipTest``.
"""
