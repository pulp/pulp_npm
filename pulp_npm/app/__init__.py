from pulpcore.plugin import PulpPluginAppConfig


class PulpNpmPluginAppConfig(PulpPluginAppConfig):
    """Entry point for the npm plugin."""

    name = "pulp_npm.app"
    label = "npm"
    version = "0.4.0.dev"
    python_package_name = "pulp-npm"
    domain_compatible = True
