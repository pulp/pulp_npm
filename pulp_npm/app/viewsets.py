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


class PackageFilter(core.ContentFilter):
    """
    FilterSet for Package.
    """

    class Meta:
        model = models.Package
        fields = {"name": ["exact", "in"]}


class PackageViewSet(core.SingleArtifactContentUploadViewSet):
    """
    A ViewSet for Package.

    Define endpoint name which will appear in the API endpoint for this content type.
    For example::
        http://pulp.example.com/pulp/api/v3/content/npm/units/

    Also specify queryset and serializer for Package.
    """

    endpoint_name = "packages"
    queryset = models.Package.objects.all()
    serializer_class = serializers.PackageSerializer
    filterset_class = PackageFilter

    @transaction.atomic
    def create(self, request):
        """
        Perform bookkeeping when saving Content.

        "Artifacts" need to be popped off and saved independently, as they are not actually part
        of the Content model.
        """
        raise NotImplementedError("FIXME")
        # This requires some choice. Depending on the properties of your content type - whether it
        # can have zero, one, or many artifacts associated with it, and whether any properties of
        # the artifact bleed into the content type (such as the digest), you may want to make
        # those changes here.

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # A single artifact per content, serializer subclasses SingleArtifactContentSerializer
        # ======================================
        # _artifact = serializer.validated_data.pop("_artifact")
        # # you can save model fields directly, e.g. .save(digest=_artifact.sha256)
        # content = serializer.save()
        #
        # if content.pk:
        #     ContentArtifact.objects.create(
        #         artifact=artifact,
        #         content=content,
        #         relative_path= ??
        #     )
        # =======================================

        # Many artifacts per content, serializer subclasses MultipleArtifactContentSerializer
        # =======================================
        # _artifacts = serializer.validated_data.pop("_artifacts")
        # content = serializer.save()
        #
        # if content.pk:
        #   # _artifacts is a dictionary of {"relative_path": "artifact"}
        #   for relative_path, artifact in _artifacts.items():
        #       ContentArtifact.objects.create(
        #           artifact=artifact,
        #           content=content,
        #           relative_path=relative_path
        #       )
        # ========================================

        # No artifacts, serializer subclasses NoArtifactContentSerialier
        # ========================================
        # content = serializer.save()
        # ========================================

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class NpmRemoteViewSet(core.RemoteViewSet):
    """
    A ViewSet for NpmRemote.

    Similar to the PackageViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmRemote.objects.all()
    serializer_class = serializers.NpmRemoteSerializer


class NpmRepositoryViewSet(core.RepositoryViewSet, ModifyRepositoryActionMixin):
    """
    A ViewSet for NpmRepository.

    Similar to the PackageViewSet above, define endpoint_name,
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
