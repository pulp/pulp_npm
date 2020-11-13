from django.conf import settings
from django.urls import path

from pulp_npm.app.viewsets import PublishedPackageViewSet


PACKAGE_API_ROOT = getattr(settings, "PACKAGE_API_ROOT", "pulp_npm/packages/<path:name>/")

urlpatterns = [path(PACKAGE_API_ROOT, PublishedPackageViewSet.as_view())]
