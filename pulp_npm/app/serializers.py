"""
Check `Plugin Writer's Guide`_ for more details.

.. _Plugin Writer's Guide:
    http://docs.pulpproject.org/en/3.0/nightly/plugins/plugin-writer/index.html
"""
from gettext import gettext as _

from django.conf import settings
from rest_framework import serializers

from pulpcore.plugin import models as core_models
from pulpcore.plugin import serializers as platform

from .utils import pulp_npm_content_path
from . import models


# FIXME: SingleArtifactContentSerializer might not be the right choice for you.
# If your content type has no artifacts per content unit, use "NoArtifactContentSerializer".
# If your content type has many artifacts per content unit, use "MultipleArtifactContentSerializer"
# If you want create content through upload, use "SingleArtifactContentUploadSerializer"
# If you change this, make sure to do so on "fields" below, also.
# Make sure your choice here matches up with the create() method of your viewset.
class PackageSerializer(platform.SingleArtifactContentUploadSerializer):
    """
    A Serializer for Package.

    Add serializers for the new fields defined in Package and
    add those fields to the Meta class keeping fields from the parent class as well.

    For example::

    field1 = serializers.TextField()
    field2 = serializers.IntegerField()
    field3 = serializers.CharField()

    class Meta:
        fields = platform.SingleArtifactContentSerializer.Meta.fields + (
            'field1', 'field2', 'field3'
        )
        model = models.Package
    """

    name = serializers.CharField()
    version = serializers.CharField()
    relative_path = serializers.CharField()

    class Meta:
        fields = platform.SingleArtifactContentUploadSerializer.Meta.fields + (
            "name",
            "version",
            "relative_path",
        )
        model = models.Package


class NpmRemoteSerializer(platform.RemoteSerializer):
    """
    A Serializer for NpmRemote.

    Add any new fields if defined on NpmRemote.
    Similar to the example above, in PackageSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = platform.RemoteSerializer.Meta.validators + [myValidator1, myValidator2]

    By default the 'policy' field in platform.RemoteSerializer only validates the choice
    'immediate'. To add on-demand support for more 'policy' options, e.g. 'streamed' or 'on_demand',
    re-define the 'policy' option as follows::

    """

    policy = serializers.ChoiceField(
        help_text="The policy to use when downloading content. The possible values include: "
        "'immediate', 'on_demand', and 'streamed'. 'immediate' is the default.",
        choices=core_models.Remote.POLICY_CHOICES,
        default=core_models.Remote.IMMEDIATE,
    )

    class Meta:
        fields = platform.RemoteSerializer.Meta.fields
        model = models.NpmRemote


class NpmRepositorySerializer(platform.RepositorySerializer):
    """
    A Serializer for NpmRepository.

    Add any new fields if defined on NpmRepository.
    Similar to the example above, in PackageSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = platform.RepositorySerializer.Meta.validators + [myValidator1, myValidator2]
    """

    class Meta:
        fields = platform.RepositorySerializer.Meta.fields
        model = models.NpmRepository


class NpmBaseURLField(serializers.CharField):
    """
    Field for the base_url field pointing to the npm content app.
    """

    def to_representation(self, value):
        """
        Field representation.
        """
        base_path = value
        origin = settings.CONTENT_ORIGIN
        prefix = pulp_npm_content_path()
        return "/".join((origin.strip("/"), prefix.strip("/"), base_path.lstrip("/")))


class NpmDistributionSerializer(platform.RepositoryVersionDistributionSerializer):
    """
    Serializer for NPM Distributions.
    """

    base_url = NpmBaseURLField(
        source="base_path",
        read_only=True,
        help_text=_("The URL for accessing the universe API as defined by this distribution."),
    )

    class Meta:
        fields = platform.RepositoryVersionDistributionSerializer.Meta.fields
        model = models.NpmDistribution
