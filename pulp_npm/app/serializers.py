from gettext import gettext as _
from logging import getLogger

from django.db import DatabaseError
from rest_framework import serializers

from pulpcore.plugin import models as core_models
from pulpcore.plugin import serializers as core_serializers
from pulpcore.plugin.util import get_domain_pk

from . import models
from .utils import extract_npm_metadata_from_artifact, sanitize_manifest, sri_from_artifact

logger = getLogger(__name__)


def _apply_artifact_metadata(data, artifact):
    """Populate ``name``, ``version`` and ``manifest`` from the uploaded tarball.

    The tarball's ``package.json`` is authoritative for the *manifest*. The
    generic content upload API has always allowed callers to supply ``name`` and
    ``version`` explicitly (overriding what the tarball says); keep that
    behaviour for compatibility. The publish API is stricter and validates the
    identity itself. When the tarball cannot be read and explicit values were
    supplied, keep the old degraded behaviour (content is created without a
    manifest) instead of rejecting the upload; otherwise raise, as before.
    """
    provided_name = data.get("name")
    provided_version = data.get("version")
    data["integrity"] = sri_from_artifact(artifact)
    data["shasum"] = getattr(artifact, "sha1", None) or None

    try:
        metadata = extract_npm_metadata_from_artifact(artifact)
    except ValueError as e:
        if provided_name and provided_version:
            logger.warning(
                "Could not read package.json from uploaded tarball (%s); "
                "creating content without a manifest.",
                e,
            )
            return
        raise serializers.ValidationError(
            _(
                "Could not extract metadata from npm tarball: {}. "
                "Please provide 'name' and 'version' explicitly."
            ).format(e)
        )

    if provided_name and provided_name != metadata["name"]:
        logger.warning(
            "Uploaded tarball package.json name %r differs from the explicit name %r.",
            metadata["name"],
            provided_name,
        )
    else:
        data["name"] = metadata["name"]

    if provided_version and provided_version != metadata["version"]:
        logger.warning(
            "Uploaded tarball package.json version %r differs from the explicit version %r.",
            metadata["version"],
            provided_version,
        )
    else:
        data["version"] = metadata["version"]

    try:
        data["manifest"] = sanitize_manifest(metadata.get("manifest") or {}, strict=True)
    except ValueError as e:
        if provided_name and provided_version:
            logger.warning(
                "Could not sanitize package.json from uploaded tarball (%s); "
                "creating content without a manifest.",
                e,
            )
            data["manifest"] = {}
        else:
            raise serializers.ValidationError(
                _("Could not sanitize metadata from npm tarball: {}").format(e)
            )


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
            raise serializers.ValidationError(
                _("An artifact is required to create npm package content.")
            )

        _apply_artifact_metadata(data, artifact)

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

        _apply_artifact_metadata(data, artifact)

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
