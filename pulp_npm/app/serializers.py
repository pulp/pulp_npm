from gettext import gettext as _
from rest_framework import serializers

from pulpcore.plugin import models as core_models
from pulpcore.plugin import serializers as core_serializers

from . import models


# FIXME: SingleArtifactContentSerializer might not be the right choice for you.
# If your content type has no artifacts per content unit, use "NoArtifactContentSerializer".
# If your content type has many artifacts per content unit, use "MultipleArtifactContentSerializer"
# If you want create content through upload, use "SingleArtifactContentUploadSerializer"
# If you change this, make sure to do so on "fields" below, also.
# Make sure your choice here matches up with the create() method of your viewset.
class PackageSerializer(core_serializers.SingleArtifactContentUploadSerializer):
    """
    A Serializer for Package.

    Add serializers for the new fields defined in Package and
    add those fields to the Meta class keeping fields from the parent class as well.

    For example::

    field1 = serializers.TextField()
    field2 = serializers.IntegerField()
    field3 = serializers.CharField()

    class Meta:
        fields = core_serializers.SingleArtifactContentSerializer.Meta.fields + (
            'field1', 'field2', 'field3'
        )
        model = models.Package
    """

    name = serializers.CharField()
    version = serializers.CharField()
    relative_path = serializers.CharField()

    class Meta:
        fields = core_serializers.SingleArtifactContentUploadSerializer.Meta.fields + (
            "name",
            "version",
            "relative_path",
        )
        model = models.Package


class NpmRemoteSerializer(core_serializers.RemoteSerializer):
    """
    A Serializer for NpmRemote.

    Add any new fields if defined on NpmRemote.
    Similar to the example above, in PackageSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = core_serializers.RemoteSerializer.Meta.validators + [myValidator1, ...]

    By default the 'policy' field in core_serializers.RemoteSerializer only validates the choice
    'immediate'. To add on-demand support for more 'policy' options, e.g. 'streamed' or 'on_demand',
    re-define the 'policy' option as follows::

    """

    policy = serializers.ChoiceField(
        help_text="The policy to use when downloading content. The possible values include: "
        "'immediate', 'on_demand', and 'streamed'. 'immediate' is the default.",
        choices=core_models.Remote.POLICY_CHOICES,
        required=False,
    )

    class Meta:
        fields = core_serializers.RemoteSerializer.Meta.fields
        model = models.NpmRemote


class NpmRepositorySerializer(core_serializers.RepositorySerializer):
    """
    A Serializer for NpmRepository.

    Add any new fields if defined on NpmRepository.
    Similar to the example above, in PackageSerializer.
    Additional validators can be added to the parent validators list

    For example::

    class Meta:
        validators = core_serializers.RepositorySerializer.Meta.validators + [myValidator1, ...]
    """

    class Meta:
        fields = core_serializers.RepositorySerializer.Meta.fields
        model = models.NpmRepository


class NpmDistributionSerializer(core_serializers.DistributionSerializer):
    """
    Serializer for NPM Distributions.
    """

    remote = core_serializers.DetailRelatedField(
        required=False,
        help_text=_("Remote that can be used to fetch content when using pull-through caching."),
        view_name_pattern=r"remotes(-.*/.*)?-detail",
        queryset=core_models.Remote.objects.all(),
        allow_null=True,
    )

    class Meta:
        fields = core_serializers.DistributionSerializer.Meta.fields + ("remote",)
        model = models.NpmDistribution
