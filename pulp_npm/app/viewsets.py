from django.db import transaction
from django_filters.rest_framework import BooleanFilter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import IntegerField, URLField, ValidationError

from pulpcore.plugin import viewsets as core
from pulpcore.plugin.actions import ModifyRepositoryActionMixin
from pulpcore.plugin.models import RepositoryVersion
from pulpcore.plugin.serializers import (
    AsyncOperationResponseSerializer,
    RepositorySyncURLSerializer,
)
from pulpcore.plugin.tasking import dispatch

from . import models, serializers, tasks
from .catalog import (
    apply_package_prefix_filters,
    assemble_package_index,
    collapse_npm_builds,
    distinct_name_qs,
    npm_packages_in_version,
    repository_metrics,
)
from .versions import BUILD_SUFFIX_PATTERN, normalize_package_index_ordering


class NpmPackageFilter(core.ContentFilter):
    """
    FilterSet for Package.
    """

    collapse_builds = BooleanFilter(
        method="filter_collapse_builds",
        help_text=(
            "When true, collapse rebuilds of the same logical version: strip a trailing "
            f"suffix matching {BUILD_SUFFIX_PATTERN} from version, then keep one Package "
            "per (name, base_version) with the latest pulp_created. "
            "Default false."
        ),
    )

    def filter_collapse_builds(self, qs, name, value):
        """Documented on the FilterSet; applied in the viewset after ordering.

        DISTINCT ON requires ORDER BY to start with the distinct columns. The
        viewset applies collapse after other filter backends so that ordering
        cannot break it.
        """
        return qs

    class Meta:
        model = models.Package
        fields = {"name": ["exact", "in"], "version": ["exact"]}


class NpmPackageViewSet(core.SingleArtifactContentUploadViewSet):
    """
    A ViewSet for NpmPackage.

    Define endpoint name which will appear in the API endpoint for this content type.
    For example::
        http://pulp.example.com/pulp/api/v3/content/npm/packages/

    Also specify queryset and serializer for NpmPackage.
    """

    endpoint_name = "packages"
    queryset = models.Package.objects.all()
    serializer_class = serializers.NpmPackageSerializer
    filterset_class = NpmPackageFilter
    queryset_filtering_required_permission = "npm.view_package"

    def filter_queryset(self, queryset):
        """Apply ``collapse_builds`` after other backends so DISTINCT ON stays valid."""
        queryset = super().filter_queryset(queryset)
        if getattr(self, "action", "") != "list":
            return queryset
        raw = self.request.query_params.get("collapse_builds")
        if raw is None or raw == "":
            return queryset
        if str(raw).lower() in ("true", "t", "yes", "y", "1"):
            return collapse_npm_builds(queryset)
        return queryset

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "retrieve"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_required_repo_perms_on_upload:npm.modify_npmrepository",
                    "has_required_repo_perms_on_upload:npm.view_npmrepository",
                    "has_upload_param_model_or_domain_or_obj_perms:core.change_upload",
                ],
            },
            {
                "action": ["upload"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_perms:npm.add_package",
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    @extend_schema(
        summary="Synchronous npm package upload",
        request=serializers.NpmPackageUploadSerializer,
        responses={201: serializers.NpmPackageSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        serializer_class=serializers.NpmPackageUploadSerializer,
    )
    def upload(self, request, **kwargs):
        """
        Create an npm package content unit synchronously.
        """
        serializer = self.get_serializer(data=request.data)

        with transaction.atomic():
            serializer.is_valid(raise_exception=True)
            serializer.save()

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class NpmRemoteViewSet(core.RemoteViewSet, core.RolesMixin):
    """
    A ViewSet for NpmRemote.

    Similar to the NpmPackageViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmRemote.objects.all()
    serializer_class = serializers.NpmRemoteSerializer
    queryset_filtering_required_permission = "npm.view_npmremote"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_perms:npm.add_npmremote",
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:npm.view_npmremote",
            },
            {
                "action": ["update", "partial_update", "set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.change_npmremote",
                    "has_model_or_domain_or_obj_perms:npm.view_npmremote",
                ],
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.delete_npmremote",
                    "has_model_or_domain_or_obj_perms:npm.view_npmremote",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:npm.manage_roles_npmremote",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "npm.npmremote_owner"},
            }
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    LOCKED_ROLES = {
        "npm.npmremote_creator": ["npm.add_npmremote"],
        "npm.npmremote_owner": [
            "npm.view_npmremote",
            "npm.change_npmremote",
            "npm.delete_npmremote",
            "npm.manage_roles_npmremote",
        ],
        "npm.npmremote_viewer": ["npm.view_npmremote"],
    }


class NpmRepositoryViewSet(core.RepositoryViewSet, ModifyRepositoryActionMixin, core.RolesMixin):
    """
    A ViewSet for NpmRepository.

    Similar to the NpmPackageViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmRepository.objects.all()
    serializer_class = serializers.NpmRepositorySerializer
    queryset_filtering_required_permission = "npm.view_npmrepository"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_perms:npm.add_npmrepository",
                    "has_remote_param_model_or_domain_or_obj_perms:npm.view_npmremote",
                ],
            },
            {
                "action": ["retrieve", "packages", "metrics"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:npm.view_npmrepository",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.change_npmrepository",
                    "has_model_or_domain_or_obj_perms:npm.view_npmrepository",
                    "has_remote_param_model_or_domain_or_obj_perms:npm.view_npmremote",
                ],
            },
            {
                "action": ["set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.change_npmrepository",
                    "has_model_or_domain_or_obj_perms:npm.view_npmrepository",
                ],
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.delete_npmrepository",
                    "has_model_or_domain_or_obj_perms:npm.view_npmrepository",
                ],
            },
            {
                "action": ["sync"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.sync_npmrepository",
                    "has_model_or_domain_or_obj_perms:npm.view_npmrepository",
                    "has_remote_param_model_or_domain_or_obj_perms:npm.view_npmremote",
                ],
            },
            {
                "action": ["modify"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.modify_npmrepository",
                    "has_model_or_domain_or_obj_perms:npm.view_npmrepository",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:npm.manage_roles_npmrepository",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "npm.npmrepository_owner"},
            }
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    LOCKED_ROLES = {
        "npm.npmrepository_creator": ["npm.add_npmrepository"],
        "npm.npmrepository_owner": [
            "npm.view_npmrepository",
            "npm.change_npmrepository",
            "npm.delete_npmrepository",
            "npm.sync_npmrepository",
            "npm.modify_npmrepository",
            "npm.manage_roles_npmrepository",
        ],
        "npm.npmrepository_viewer": ["npm.view_npmrepository"],
    }

    def filter_queryset(self, queryset):
        """Do not apply the repository FilterSet to package-index query params."""
        if getattr(self, "action", None) in ("packages", "metrics"):
            return queryset
        return super().filter_queryset(queryset)

    def _requested_repository_version(self, repository):
        """Resolve optional ``repository_version`` href/PRN, else latest complete version."""
        href = self.request.query_params.get("repository_version")
        if not href:
            return repository.latest_version()
        repo_version = self.get_resource(href, RepositoryVersion)
        if repo_version.repository_id != repository.pk:
            raise ValidationError({"repository_version": "Must be a version of this repository."})
        return repo_version

    @extend_schema(
        summary="List packages",
        description=(
            "Return one row per distinct package name in a repository version "
            "(latest complete version if repository_version is omitted). "
            "Pagination count is the number of distinct packages, not (name, version) rows. "
            "Each row includes last_updated (newest membership among any rebuild), "
            "versions (logical version keys after rebuild-suffix strip, newest first), "
            "and latest_releases (newest rebuild per logical version, same order). "
            "set(versions) === set(latest_releases[].version). "
            "Scoped packages use the full name string (e.g. @types/node)."
        ),
        parameters=[
            OpenApiParameter(
                name="repository_version",
                type=OpenApiTypes.URI,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "HREF or PRN of a version of this repository. "
                    "Defaults to the latest complete version."
                ),
            ),
            OpenApiParameter(
                name="name__istartswith",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description=(
                    "Case-insensitive prefix on the full package name, including scope "
                    "(e.g. @types/)."
                ),
            ),
            OpenApiParameter(
                name="name__icontains",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description=(
                    "Case-insensitive substring on the full package name, including scope."
                ),
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                many=True,
                description=(
                    "Order catalog rows. Allowed: name, last_updated. "
                    "Prefix with '-' for descending. Default is name."
                ),
            ),
            OpenApiParameter(
                name="limit",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Number of results to return per page.",
            ),
            OpenApiParameter(
                name="offset",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="The initial index from which to return the results.",
            ),
        ],
        responses={
            200: inline_serializer(
                name="PaginatedNpmRepositoryPackageList",
                fields={
                    "count": IntegerField(),
                    "next": URLField(allow_null=True),
                    "previous": URLField(allow_null=True),
                    "results": serializers.NpmRepositoryPackageSerializer(many=True),
                },
            )
        },
    )
    @action(
        detail=True,
        methods=["get"],
        serializer_class=serializers.NpmRepositoryPackageSerializer,
    )
    def packages(self, request, pk, **kwargs):
        """List distinct packages in a repository version."""
        repository = self.get_object()
        repo_version = self._requested_repository_version(repository)
        content_qs = npm_packages_in_version(repo_version)
        content_qs = apply_package_prefix_filters(
            content_qs,
            name_prefix=request.query_params.get("name__istartswith"),
            name_contains=request.query_params.get("name__icontains"),
        )
        try:
            ordering = normalize_package_index_ordering(request.query_params.getlist("ordering"))
        except ValueError as exc:
            raise ValidationError({"ordering": str(exc)}) from exc
        names_qs = distinct_name_qs(content_qs, repository, repo_version, ordering=ordering)
        page = self.paginate_queryset(names_qs)
        rows = assemble_package_index(
            content_qs,
            page if page is not None else list(names_qs),
            repository,
            repo_version,
        )
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(
        summary="Repository metrics",
        description=(
            "Distinct counts for Package content in a repository version "
            "(latest complete version if repository_version is omitted). "
            "package_count is distinct name. version_count is distinct "
            "(name, base_version) after rebuild-suffix strip. "
            "build_count is distinct (name, full version)."
        ),
        parameters=[
            OpenApiParameter(
                name="repository_version",
                type=OpenApiTypes.URI,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "HREF or PRN of a version of this repository. "
                    "Defaults to the latest complete version."
                ),
            ),
        ],
        responses={200: serializers.NpmRepositoryMetricsSerializer},
    )
    @action(
        detail=True,
        methods=["get"],
        serializer_class=serializers.NpmRepositoryMetricsSerializer,
    )
    def metrics(self, request, pk, **kwargs):
        """Return package / version / build counts for a repository version."""
        repository = self.get_object()
        repo_version = self._requested_repository_version(repository)
        counts = repository_metrics(npm_packages_in_version(repo_version))
        serializer = self.get_serializer(counts)
        return Response(serializer.data)

    # This decorator is necessary since a sync operation is asyncrounous and returns
    # the id and href of the sync task.
    @extend_schema(
        description="Trigger an asynchronous task to sync content.",
        summary="Sync from remote",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=RepositorySyncURLSerializer)
    def sync(self, request, pk, **kwargs):
        """
        Dispatches a sync task.
        """
        repository = self.get_object()
        serializer = RepositorySyncURLSerializer(
            data=request.data, context={"request": request, "repository_pk": pk}
        )
        serializer.is_valid(raise_exception=True)
        remote = serializer.validated_data.get("remote", repository.remote)

        result = dispatch(
            tasks.synchronize,
            kwargs={"remote_pk": remote.pk, "repository_pk": repository.pk},
            exclusive_resources=[repository],
            shared_resources=[remote],
        )
        return core.OperationPostponedResponse(result, request)


class NpmRepositoryVersionViewSet(core.RepositoryVersionViewSet):
    """
    A ViewSet for a NpmRepositoryVersion represents a single Npm repository version.
    """

    parent_viewset = NpmRepositoryViewSet

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_repository_model_or_domain_or_obj_perms:npm.view_npmrepository",
                ],
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_repository_model_or_domain_or_obj_perms:npm.delete_npmrepository",
                    "has_repository_model_or_domain_or_obj_perms:npm.view_npmrepository",
                ],
            },
            {
                "action": ["repair"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_repository_model_or_domain_or_obj_perms:npm.modify_npmrepository",
                    "has_repository_model_or_domain_or_obj_perms:npm.view_npmrepository",
                ],
            },
        ],
    }


class NpmDistributionViewSet(core.DistributionViewSet, core.RolesMixin):
    """
    ViewSet for NPM Distributions.
    """

    endpoint_name = "npm"
    queryset = models.NpmDistribution.objects.all()
    serializer_class = serializers.NpmDistributionSerializer
    queryset_filtering_required_permission = "npm.view_npmdistribution"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_perms:npm.add_npmdistribution",
                    "has_repo_or_repo_ver_param_model_or_domain_or_obj_perms:"
                    "npm.view_npmrepository",
                ],
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:npm.view_npmdistribution",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.change_npmdistribution",
                    "has_model_or_domain_or_obj_perms:npm.view_npmdistribution",
                    "has_repo_or_repo_ver_param_model_or_domain_or_obj_perms:"
                    "npm.view_npmrepository",
                ],
            },
            {
                "action": ["set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.change_npmdistribution",
                    "has_model_or_domain_or_obj_perms:npm.view_npmdistribution",
                ],
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:npm.delete_npmdistribution",
                    "has_model_or_domain_or_obj_perms:npm.view_npmdistribution",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:npm.manage_roles_npmdistribution",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "npm.npmdistribution_owner"},
            }
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    LOCKED_ROLES = {
        "npm.npmdistribution_creator": ["npm.add_npmdistribution"],
        "npm.npmdistribution_owner": [
            "npm.view_npmdistribution",
            "npm.change_npmdistribution",
            "npm.delete_npmdistribution",
            "npm.manage_roles_npmdistribution",
        ],
        "npm.npmdistribution_viewer": ["npm.view_npmdistribution"],
    }
