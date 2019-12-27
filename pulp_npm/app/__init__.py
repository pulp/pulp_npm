from pulpcore.plugin import PulpPluginAppConfig


class PulpNpmPluginAppConfig(PulpPluginAppConfig):
    """Entry point for the npm plugin."""

    name = "pulp_npm.app"
    label = "npm"
