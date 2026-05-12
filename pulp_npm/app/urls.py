from django.conf import settings
from django.urls import re_path

from pulp_npm.app.npm_publish_api import NpmPingView, NpmPublishView, NpmWhoamiView

if settings.DOMAIN_ENABLED:
    _base = r"npm/(?P<pulp_domain>[-a-zA-Z0-9_]+)/(?P<path>.+?)/"
else:
    _base = r"npm/(?P<path>.+?)/"

# Matches both scoped (@scope%2Fname) and unscoped package names in a single group.
_pkg = r"(?P<package_name>@[^/]+%2[Ff][^/]+|@[^/]+/[^/]+|[^/@][^/]*)"

urlpatterns = [
    re_path(rf"^{_base}-/ping$", NpmPingView.as_view()),
    re_path(rf"^{_base}-/whoami$", NpmWhoamiView.as_view()),
    re_path(rf"^{_base}{_pkg}$", NpmPublishView.as_view()),
]
