# coding=utf-8
"""Constants for Pulp Npm plugin tests."""
from urllib.parse import urljoin

PULP_FIXTURES_BASE_URL = "https://fixtures.pulpproject.org/"

# FIXME: list any download policies supported by your plugin type here.
DOWNLOAD_POLICIES = ["immediate", "streamed", "on_demand"]

NPM_CONTENT_NAME = "npm.package"

NPM_FIXTURE_URL = "https://registry.npmjs.org/"
"""The URL to a npm repository."""

# FIXME: replace this with the actual number of content units in your test fixture
NPM_FIXTURE_COUNT = 1
"""The number of content units available at :data:`NPM_FIXTURE_URL`."""

NPM_FIXTURE_SUMMARY = {NPM_CONTENT_NAME: NPM_FIXTURE_COUNT}
"""The desired content summary after syncing :data:`NPM_FIXTURE_URL`."""

# FIXME: replace this with the location of one specific content unit of your choosing
NPM_URL = urljoin(NPM_FIXTURE_URL, "")
"""The URL to an npm file at :data:`NPM_FIXTURE_URL`."""

# FIXME: replace this with your own fixture repository URL and metadata
NPM_INVALID_FIXTURE_URL = urljoin(PULP_FIXTURES_BASE_URL, "npm-invalid/")
"""The URL to an invalid npm repository."""

# FIXME: replace this with your own fixture repository URL and metadata
NPM_LARGE_FIXTURE_URL = urljoin(PULP_FIXTURES_BASE_URL, "npm_large/")
"""The URL to a npm repository containing a large number of content units."""

# FIXME: replace this with the actual number of content units in your test fixture
NPM_LARGE_FIXTURE_COUNT = 25
"""The number of content units available at :data:`NPM_LARGE_FIXTURE_URL`."""
