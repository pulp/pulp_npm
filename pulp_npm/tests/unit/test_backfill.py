import base64
import io
import json
import tarfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pulp_npm.app.tasks.backfill import _backfill_package, _chunks

SHA512_HEX = "ab" * 64


class _FakeFile:
    def __init__(self, data):
        self.data = data

    def open(self, mode):
        return self

    def chunks(self):
        yield self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _tarball(**manifest):
    payload = json.dumps(manifest).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _artifact(data=None, sha1=None):
    return SimpleNamespace(
        file=_FakeFile(data if data is not None else _tarball(name="pkg", version="1.0.0")),
        sha512=SHA512_HEX,
        sha1=sha1,
    )


class TestBackfillPackage(unittest.TestCase):
    def test_fills_empty_manifest_and_integrity(self):
        package = SimpleNamespace(manifest={}, integrity=None, shasum=None, save=Mock())
        artifact = _artifact(
            _tarball(
                name="pkg",
                version="1.0.0",
                dependencies={"dep-a": "^1.0.0"},
                scripts={"postinstall": "node setup.js"},
            )
        )

        updated, reason = _backfill_package(package, artifact)

        self.assertTrue(updated)
        self.assertIsNone(reason)
        self.assertEqual(package.manifest["dependencies"], {"dep-a": "^1.0.0"})
        self.assertTrue(package.manifest["hasInstallScript"])
        self.assertEqual(
            package.integrity,
            "sha512-" + base64.b64encode(bytes.fromhex(SHA512_HEX)).decode(),
        )
        package.save.assert_called_once()

    def test_does_not_replace_manifest_without_overwrite(self):
        existing = {"dependencies": {"old": "^1.0.0"}}
        package = SimpleNamespace(manifest=existing, integrity=None, shasum=None, save=Mock())

        updated, reason = _backfill_package(
            package, _artifact(_tarball(name="pkg", version="1.0.0", description="new"))
        )

        self.assertTrue(updated)  # integrity was filled
        self.assertEqual(package.manifest, existing)
        self.assertIsNone(reason)

    def test_overwrite_replaces_manifest(self):
        package = SimpleNamespace(
            manifest={"dependencies": {"old": "^1.0.0"}},
            integrity=None,
            shasum=None,
            save=Mock(),
        )

        _backfill_package(
            package,
            _artifact(_tarball(name="pkg", version="1.0.0", dependencies={"new": "^2.0.0"})),
            overwrite=True,
        )

        self.assertEqual(package.manifest["dependencies"], {"new": "^2.0.0"})

    def test_skips_missing_artifact(self):
        updated, reason = _backfill_package(
            SimpleNamespace(manifest={}, integrity=None, shasum=None, save=Mock()), None
        )
        self.assertFalse(updated)
        self.assertEqual(reason, "no_artifact")

    def test_skips_invalid_tarball(self):
        updated, reason = _backfill_package(
            SimpleNamespace(manifest={}, integrity=None, shasum=None, save=Mock()),
            _artifact(b"not a tarball"),
        )
        self.assertFalse(updated)
        self.assertEqual(reason, "invalid")

    def test_keeps_existing_checksums(self):
        package = SimpleNamespace(
            manifest={"dependencies": {"dep": "^1"}},
            integrity="sha512-existing",
            shasum="a" * 40,
            save=Mock(),
        )

        updated, reason = _backfill_package(
            package,
            _artifact(
                _tarball(name="pkg", version="1.0.0"),
                sha1="b" * 40,
            ),
        )

        self.assertFalse(updated)
        self.assertIsNone(reason)
        package.save.assert_not_called()


class TestChunks(unittest.TestCase):
    def test_splits_into_batches(self):
        self.assertEqual(list(_chunks(range(5), 2)), [[0, 1], [2, 3], [4]])
        self.assertEqual(list(_chunks([], 2)), [])
