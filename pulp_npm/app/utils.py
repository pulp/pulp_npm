from django.conf import settings


def pulp_npm_content_path():
    """Get base cotent path from configuration."""
    components = settings.CONTENT_PATH_PREFIX.split("/")
    components[1] = "pulp_npm"
    return "/".join(components)
