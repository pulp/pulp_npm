from gettext import gettext as _

from django.db import DatabaseError
from rest_framework import serializers

from pulpcore.plugin import models as core_models
from pulpcore.plugin import serializers as core_serializers
from pulpcore.plugin.util import get_domain_pk

from . import models
from .exceptions import MetadataExtractionError, MissingArtifactError
from .utils import extract_npm_metadata_from_artifact


class NpmPackageSerializer(core_serializers.SingleArtifactContentUploadSerializer):
    """
    A Serializer for NpmPackage.
    """

    name = serializers.CharField(
        help_text=_("The name of the npm package."),
        required=False,
    )
    version = serializers.CharField(
        help_text=_("The version of the npm package."),
        required=False,
    )
    relative_path = serializers.CharField(
        help_text=_(
            "Path where the artifact is located relative to distributions base_path. "
            "If not provided, it will be computed from name and version."
        ),
        required=False,
    )

    def deferred_validate(self, data):
        """
        Extract npm metadata from the uploaded artifact.

        If name and version are not provided in the request, they are extracted
        from the tarball's package.json.
        """
        data = super().deferred_validate(data)

        artifact = data.get("artifact")
        if artifact is None:
            raise MissingArtifactError()

        needs_name = "name" not in data or not data["name"]
        needs_version = "version" not in data or not data["version"]

        if needs_name or needs_version:
            try:
                metadata = extract_npm_metadata_from_artifact(artifact)
            except ValueError as e:
                raise MetadataExtractionError(str(e))
            if needs_name:
                data["name"] = metadata["name"]
            if needs_version:
                data["version"] = metadata["version"]

        if "relative_path" not in data or not data["relative_path"]:
            base_name = data["name"].split("/")[-1] if "/" in data["name"] else data["name"]
            data["relative_path"] = f"{data['name']}/-/{base_name}-{data['version']}.tgz"

        return data

    def get_artifacts(self, validated_data):
        # Package.relative_path is a @property, not a DB field. The base class uses
        # .get() instead of .pop() when it detects the model has a relative_path
        # attribute, but it can't distinguish properties from DB fields. We must pop
        # it here so it doesn't leak into Package.objects.create().
        artifact = validated_data.pop("artifact")
        relative_path = validated_data.pop("relative_path")
        return {relative_path: artifact}

    def retrieve(self, validated_data):
        content = models.Package.objects.filter(
            name=validated_data["name"],
            version=validated_data["version"],
            _pulp_domain=get_domain_pk(),
        )
        return content.first()

    class Meta:
        fields = core_serializers.SingleArtifactContentUploadSerializer.Meta.fields + (
            "name",
            "version",
            "relative_path",
        )
        model = models.Package


class NpmPackageUploadSerializer(NpmPackageSerializer):
    """
    A serializer for synchronous npm package uploads.

    Handles file-to-artifact conversion and metadata extraction in a single
    request instead of dispatching an async task.
    """

    def validate(self, data):
        data = super().validate(data)

        if file := data.pop("file", None):
            try:
                artifact = core_models.Artifact.objects.get(
                    sha256=file.hashers["sha256"].hexdigest(),
                    pulp_domain=get_domain_pk(),
                )
                if not artifact.pulp_domain.get_storage().exists(artifact.file.name):
                    artifact.file = file
                    artifact.save()
                else:
                    artifact.touch()
            except (core_models.Artifact.DoesNotExist, DatabaseError):
                artifact_serializer = core_serializers.ArtifactSerializer(data={"file": file})
                artifact_serializer.is_valid(raise_exception=True)
                artifact = artifact_serializer.save()
            data["artifact"] = artifact

        artifact = data.get("artifact")
        if artifact is None:
            raise serializers.ValidationError(
                _("A file or artifact is required to upload npm package content.")
            )

        needs_name = "name" not in data or not data["name"]
        needs_version = "version" not in data or not data["version"]

        if needs_name or needs_version:
            try:
                metadata = extract_npm_metadata_from_artifact(artifact)
            except ValueError as e:
                raise serializers.ValidationError(
                    _(
                        "Could not extract metadata from npm tarball: {}. "
                        "Please provide 'name' and 'version' explicitly."
                    ).format(e)
                )
            if needs_name:
                data["name"] = metadata["name"]
            if needs_version:
                data["version"] = metadata["version"]

        if "relative_path" not in data or not data["relative_path"]:
            base_name = data["name"].split("/")[-1] if "/" in data["name"] else data["name"]
            data["relative_path"] = f"{data['name']}/-/{base_name}-{data['version']}.tgz"

        return data

    class Meta(NpmPackageSerializer.Meta):
        fields = tuple(f for f in NpmPackageSerializer.Meta.fields if f not in ["repository"])
        ref_name = "NpmPackageUpload"


class NpmRemoteSerializer(core_serializers.RemoteSerializer):
    """
    A Serializer for NpmRemote.

    Add any new fields if defined on NpmRemote.
    Similar to the example above, in NpmPackageSerializer.
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
    Similar to the example above, in NpmPackageSerializer.
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
