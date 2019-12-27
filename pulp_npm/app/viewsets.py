"""
Check `Plugin Writer's Guide`_ for more details.

.. _Plugin Writer's Guide:
    http://docs.pulpproject.org/en/3.0/nightly/plugins/plugin-writer/index.html
"""

from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from pulpcore.plugin import viewsets as core
from pulpcore.plugin.serializers import (
    AsyncOperationResponseSerializer,
    RepositoryPublishURLSerializer,
    RepositorySyncURLSerializer,
)
from pulpcore.plugin.tasking import enqueue_with_reservation
from pulpcore.plugin.models import ContentArtifact

from . import models, serializers, tasks


class NpmContentFilter(core.ContentFilter):
    """
    FilterSet for NpmContent.
    """

    class Meta:
        model = models.NpmContent
        fields = [
            # ...
        ]


class NpmContentViewSet(core.ContentViewSet):
    """
    A ViewSet for NpmContent.

    Define endpoint name which will appear in the API endpoint for this content type.
    For example::
        http://pulp.example.com/pulp/api/v3/content/npm/units/

    Also specify queryset and serializer for NpmContent.
    """

    endpoint_name = "npm"
    queryset = models.NpmContent.objects.all()
    serializer_class = serializers.NpmContentSerializer
    filterset_class = NpmContentFilter

    @transaction.atomic
    def create(self, request):
        """
        Perform bookkeeping when saving Content.

        "Artifacts" need to be popped off and saved indpendently, as they are not actually part
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


class NpmRemoteFilter(core.RemoteFilter):
    """
    A FilterSet for NpmRemote.
    """

    class Meta:
        model = models.NpmRemote
        fields = [
            # ...
        ]


class NpmRemoteViewSet(core.RemoteViewSet):
    """
    A ViewSet for NpmRemote.

    Similar to the NpmContentViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmRemote.objects.all()
    serializer_class = serializers.NpmRemoteSerializer


class NpmRepositoryViewSet(core.RepositoryViewSet):
    """
    A ViewSet for NpmRepository.

    Similar to the NpmContentViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmRepository.objects.all()
    serializer_class = serializers.NpmRepositorySerializer

    # This decorator is necessary since a sync operation is asyncrounous and returns
    # the id and href of the sync task.
    @swagger_auto_schema(
        operation_description="Trigger an asynchronous task to sync content.",
        operation_summary="Sync from remote",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=RepositorySyncURLSerializer)
    def sync(self, request, pk):
        """
        Dispatches a sync task.
        """
        repository = self.get_object()
        serializer = RepositorySyncURLSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        remote = serializer.validated_data.get("remote")

        result = enqueue_with_reservation(
            tasks.synchronize,
            [repository, remote],
            kwargs={"remote_pk": remote.pk, "repository_pk": repository.pk},
        )
        return OperationPostponedResponse(result, request)


class NpmRepositoryVersionViewSet(RepositoryVersionViewSet):
    """
    A ViewSet for a NpmRepositoryVersion represents a single
    Npm repository version.
    """

    parent_viewset = NpmRepositoryViewSet


class NpmPublisherViewSet(core.PublisherViewSet):
    """
    A ViewSet for NpmPublisher.

    Similar to the NpmContentViewSet above, define endpoint_name,
    queryset and serializer, at a minimum.
    """

    endpoint_name = "npm"
    queryset = models.NpmPublisher.objects.all()
    serializer_class = serializers.NpmPublisherSerializer

    # This decorator is necessary since a publish operation is asyncrounous and returns
    # the id and href of the publish task.
    @swagger_auto_schema(
        operation_description="Trigger an asynchronous task to publish content",
        responses={202: AsyncOperationResponseSerializer},
    )
    @detail_route(methods=("post",), serializer_class=RepositoryPublishURLSerializer)
    def publish(self, request, pk):
        """
        Publishes a repository.

        Either the ``repository`` or the ``repository_version`` fields can
        be provided but not both at the same time.
        """
        publisher = self.get_object()
        serializer = RepositoryPublishURLSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        repository_version = serializer.validated_data.get("repository_version")

        result = enqueue_with_reservation(
            tasks.publish,
            [repository_version.repository, publisher],
            kwargs={
                "publisher_pk": str(publisher.pk),
                "repository_version_pk": str(repository_version.pk),
            },
        )
        return core.OperationPostponedResponse(result, request)
