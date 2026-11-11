import logging

from pulpcore.plugin.models import ContentArtifact

from pulp_npm.app.models import NpmRepository, Package
from pulp_npm.app.utils import (
    extract_npm_metadata_from_artifact,
    sanitize_manifest,
    sri_from_artifact,
)

log = logging.getLogger(__name__)

BATCH_SIZE = 500


def _chunks(iterable, size):
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _backfill_package(package, artifact, overwrite=False):
    """
    Populate one package's manifest and checksums from its stored artifact.

    Returns ``(updated, reason)`` where reason is one of ``None``,
    ``"no_artifact"`` or ``"invalid"``.
    """
    if artifact is None:
        return False, "no_artifact"

    try:
        metadata = extract_npm_metadata_from_artifact(artifact)
        manifest = sanitize_manifest(metadata.get("manifest") or {})
    except ValueError as exc:
        log.warning("Could not backfill %s: %s", package, exc)
        return False, "invalid"

    update_fields = []
    if (overwrite or not package.manifest) and manifest != package.manifest:
        package.manifest = manifest
        update_fields.append("manifest")

    integrity = sri_from_artifact(artifact)
    if integrity and not package.integrity:
        package.integrity = integrity
        update_fields.append("integrity")

    shasum = artifact.sha1 or None
    if shasum and not package.shasum:
        package.shasum = shasum
        update_fields.append("shasum")

    if not update_fields:
        return False, None

    package.save(update_fields=update_fields)
    return True, None


def backfill_repository_manifests(repository_pk, overwrite=False):
    """
    Backfill manifests and checksums for the latest version of an npm repository.

    Deferred content (no local artifact) and unreadable tarballs are skipped and
    reported. The task is idempotent and only fills missing fields unless
    ``overwrite`` is set.
    """
    repository = NpmRepository.objects.get(pk=repository_pk)
    repository_version = repository.latest_version()
    counts = {
        "scanned": 0,
        "updated": 0,
        "skipped_no_artifact": 0,
        "skipped_invalid": 0,
    }
    if repository_version is None:
        return counts

    content_ids = repository_version.content.values_list("pk", flat=True)
    for batch in _chunks(content_ids.iterator(chunk_size=BATCH_SIZE), BATCH_SIZE):
        artifacts = {}
        for content_artifact in (
            ContentArtifact.objects.filter(content_id__in=batch, artifact__isnull=False)
            .select_related("artifact")
            .order_by("pk")
        ):
            artifacts.setdefault(content_artifact.content_id, content_artifact.artifact)

        for package in Package.objects.filter(pk__in=batch):
            counts["scanned"] += 1
            updated, reason = _backfill_package(
                package, artifacts.get(package.pk), overwrite=overwrite
            )
            if updated:
                counts["updated"] += 1
            if reason == "no_artifact":
                counts["skipped_no_artifact"] += 1
            elif reason == "invalid":
                counts["skipped_invalid"] += 1

    return counts
