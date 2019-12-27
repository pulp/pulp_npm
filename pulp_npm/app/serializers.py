"""
Check `Plugin Writer's Guide`_ for more details.

.. _Plugin Writer's Guide:
    http://docs.pulpproject.org/en/3.0/nightly/plugins/plugin-writer/index.html
"""
from rest_framework import serializers

from pulpcore.plugin import serializers as platform

from . import models


# FIXME: SingleArtifactContentSerializer might not be the right choice for you.
# If your content type has no artifacts per content unit, use "NoArtifactContentSerializer".
# If your content type has many artifacts per content unit, use "MultipleArtifactContentSerializer"
# If you want create content through upload, use "SingleArtifactContentUploadSerializer"
# If you change this, make sure to do so on "fields" below, also.
# Make sure your choice here matches up with the create() method of your viewset.
class NpmContentSerializer(platform.SingleArtifactContentSerializer):
    """
    A Serializer for NpmContent.

    Add serializers for the new fields defined in NpmContent and
    add those fields to the Meta class keeping fields from the parent class as well.

    For example::

    field1 = serializers.TextField()
    field2 = serializers.IntegerField()
    field3 = serializers.CharField()

    class Meta:
        fields = platform.SingleArtifactContentSerializer.Meta.fields + (
            'field1', 'field2', 'field3'
        )
        model = models.NpmContent
    """

    class Meta:
        fields = platform.SingleArtifactContentSerializer.Meta.fields
        model = models.NpmContent


class NpmRemoteSerializer(platform.RemoteSerializer):
    """
    A Serializer for NpmRemote.

    Add any new fields if defined on NpmRemote.
    Similar to the example above, in NpmContentSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = platform.RemoteSerializer.Meta.validators + [myValidator1, myValidator2]

    By default the 'policy' field in platform.RemoteSerializer only validates the choice
    'immediate'. To add on-demand support for more 'policy' options, e.g. 'streamed' or 'on_demand',
    re-define the 'policy' option as follows::

    policy = serializers.ChoiceField(
        help_text="The policy to use when downloading content. The possible values include: "
                  "'immediate', 'on_demand', and 'streamed'. 'immediate' is the default.",
        choices=models.Remote.POLICY_CHOICES,
        default=models.Remote.IMMEDIATE
    )
    """

    class Meta:
        fields = platform.RemoteSerializer.Meta.fields
        model = models.NpmRemote


class NpmRepositorySerializer(platform.RepositorySerializer):
    """
    A Serializer for NpmRepository.

    Add any new fields if defined on NpmRepository.
    Similar to the example above, in NpmContentSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = platform.RepositorySerializer.Meta.validators + [myValidator1, myValidator2]
    """

    class Meta:
        fields = platform.RepositorySerializer.Meta.fields
        model = models.NpmRepository


class NpmPublisherSerializer(platform.PublisherSerializer):
    """
    A Serializer for NpmPublisher.

    Add any new fields if defined on NpmPublisher.
    Similar to the example above, in NpmContentSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = platform.PublisherSerializer.Meta.validators + [myValidator1, myValidator2]
    """

    class Meta:
        fields = platform.PublisherSerializer.Meta.fields
        model = models.NpmPublisher
