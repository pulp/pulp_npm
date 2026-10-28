from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

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
    assemble_package_index,
    distinct_package_names_qs,
    npm_packages_in_version,
    resolve_repository_version,
)


class NpmPackageFilter(core.ContentFilter):
    """
    FilterSet for Package.
    """

    class Meta:
        model = models.Package
        fields = {"name": ["exact", "in"]}


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
            {
                "action": ["set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_domain_perms:core.manage_content_labels"],
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
                "action": ["retrieve", "packages"],
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

    @property
    def filter_backends(self):
        """Repository filters apply to the repository list, not the package index.

        ``packages`` is a detail GET that returns a list. Spectacular treats that
        as a list operation and would otherwise document ``RepositoryFilter``.
        """
        if getattr(self, "action", None) == "packages":
            return []
        return super().filter_backends

    def filter_queryset(self, queryset):
        """Do not apply the repository FilterSet to package-index query params."""
        if getattr(self, "action", None) == "packages":
            return queryset
        return super().filter_queryset(queryset)

    def _repository_version_from_href(self, href):
        """Load a repository version without selecting ``content_ids``."""
        try:
            return resolve_repository_version(href)
        except ValueError as exc:
            raise ValidationError({"repository_version": str(exc)}) from exc

    def _requested_repository_version(self, repository):
        """Resolve optional ``repository_version`` href/PRN, else latest complete version."""
        href = self.request.query_params.get("repository_version")
        if not href:
            try:
                # content_ids is a UUID per content unit. The catalog never reads it.
                return repository.versions.complete().defer("content_ids").latest()
            except RepositoryVersion.DoesNotExist:
                return None
        repo_version = self._repository_version_from_href(href)
        if repo_version is None:
            return None
        if repo_version.repository_id != repository.pk:
            raise ValidationError({"repository_version": "Must be a version of this repository."})
        return repo_version

    @extend_schema(
        summary="List packages",
        description=(
            "Return one row per distinct package name in a repository version "
            "(latest complete version if repository_version is omitted). "
            "Pagination count is the number of distinct packages, not (name, version) rows. "
            "versions lists stored version strings, newest first. "
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
        ],
        responses={200: serializers.NpmRepositoryPackageSerializer(many=True)},
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
        names_qs = distinct_package_names_qs(content_qs)
        page = self.paginate_queryset(names_qs)
        rows = assemble_package_index(
            content_qs,
            page if page is not None else list(names_qs),
            repo_version,
        )
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
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
