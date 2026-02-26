from django.db import transaction
from drf_spectacular.utils import extend_schema

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from pulpcore.plugin import viewsets as core
from pulpcore.plugin.actions import ModifyRepositoryActionMixin
from pulpcore.plugin.serializers import (
    AsyncOperationResponseSerializer,
    RepositorySyncURLSerializer,
)
from pulpcore.plugin.tasking import dispatch

from . import models, serializers, tasks


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
    def upload(self, request):
        """
        Create an npm package content unit synchronously.
        """
        serializer = self.get_serializer(data=request.data)

        with transaction.atomic():
            serializer.is_valid(raise_exception=True)
            serializer.save()

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class NpmRemoteViewSet(core.RemoteViewSet):
    """
    A ViewSet for NpmRemote.

    Similar to the NpmPackageViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmRemote.objects.all()
    serializer_class = serializers.NpmRemoteSerializer


class NpmRepositoryViewSet(core.RepositoryViewSet, ModifyRepositoryActionMixin):
    """
    A ViewSet for NpmRepository.

    Similar to the NpmPackageViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmRepository.objects.all()
    serializer_class = serializers.NpmRepositorySerializer

    # This decorator is necessary since a sync operation is asyncrounous and returns
    # the id and href of the sync task.
    @extend_schema(
        description="Trigger an asynchronous task to sync content.",
        summary="Sync from remote",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=RepositorySyncURLSerializer)
    def sync(self, request, pk):
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


class NpmDistributionViewSet(core.DistributionViewSet):
    """
    ViewSet for NPM Distributions.
    """

    endpoint_name = "npm"
    queryset = models.NpmDistribution.objects.all()
    serializer_class = serializers.NpmDistributionSerializer
