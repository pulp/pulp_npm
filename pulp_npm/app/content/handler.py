from pulpcore.plugin.content import Handler
from pulp_npm.app.models import NpmDistribution


class NpmContentHandler(Handler):
    """
    Serve npm repositories.

    """

    distribution_model = NpmDistribution
