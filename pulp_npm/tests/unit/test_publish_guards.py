import base64
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pulp_npm.app.npm_publish_api import (
    _artifact_matches,
    _expected_digests,
    _validate_against_existing,
)

SHA512_HEX = "ab" * 64
SHA512_SRI = "sha512-" + base64.b64encode(bytes.fromhex(SHA512_HEX)).decode()
SHA1_HEX = "cd" * 20


class TestExpectedDigests(unittest.TestCase):
    def test_reads_integrity_and_shasum(self):
        content = SimpleNamespace(integrity=SHA512_SRI, shasum=SHA1_HEX)
        self.assertEqual(
            _expected_digests(content, None),
            {"sha512": {SHA512_HEX}, "sha1": {SHA1_HEX}},
        )

    def test_empty_when_nothing_is_recorded(self):
        content = SimpleNamespace(integrity=None, shasum=None)
        self.assertEqual(_expected_digests(content, None), {})


class TestArtifactMatches(unittest.TestCase):
    def test_matches_sha512(self):
        artifact = SimpleNamespace(sha512=SHA512_HEX, sha1=None)
        self.assertTrue(_artifact_matches(artifact, {"sha512": {SHA512_HEX}}, b"data"))

    def test_rejects_mismatch(self):
        artifact = SimpleNamespace(sha512="ef" * 64, sha1=None)
        self.assertFalse(_artifact_matches(artifact, {"sha512": {SHA512_HEX}}, b"data"))

    def test_rejects_when_nothing_is_expected(self):
        artifact = SimpleNamespace(sha512=SHA512_HEX, sha1=None)
        self.assertFalse(_artifact_matches(artifact, {}, b"data"))

    def test_computes_sha1_when_the_artifact_does_not_store_it(self):
        data = b"tarball bytes"
        artifact = SimpleNamespace(sha512=None, sha1=None)
        expected = {"sha1": {hashlib.sha1(data).hexdigest()}}
        self.assertTrue(_artifact_matches(artifact, expected, data))

    def test_rejects_conflicting_expected_values(self):
        artifact = SimpleNamespace(sha512=SHA512_HEX, sha1=None)
        expected = {"sha512": {SHA512_HEX, "ef" * 64}}
        self.assertFalse(_artifact_matches(artifact, expected, b"data"))


class TestValidateAgainstExisting(unittest.TestCase):
    def _artifact(self, sha256="a" * 64):
        return SimpleNamespace(sha512=SHA512_HEX, sha1=None, sha256=sha256)

    def _content(self):
        return SimpleNamespace(name="pkg", version="1.0.0", integrity=None, shasum=None)

    def test_attaches_when_expected_digest_matches(self):
        ca = SimpleNamespace(artifact=None, save=Mock())
        artifact = self._artifact()

        with patch(
            "pulp_npm.app.npm_publish_api._expected_digests",
            return_value={"sha512": {SHA512_HEX}},
        ):
            error = _validate_against_existing(self._content(), ca, artifact, b"data")

        self.assertIsNone(error)
        self.assertIs(ca.artifact, artifact)
        ca.save.assert_called_once_with(update_fields=["artifact"])

    def test_rejects_when_expected_digest_differs(self):
        ca = SimpleNamespace(artifact=None, save=Mock())
        artifact = self._artifact()

        with patch(
            "pulp_npm.app.npm_publish_api._expected_digests",
            return_value={"sha512": {"ef" * 64}},
        ):
            error = _validate_against_existing(self._content(), ca, artifact, b"data")

        self.assertIn("different content", error)
        ca.save.assert_not_called()

    def test_rejects_when_existing_content_has_no_integrity(self):
        error = _validate_against_existing(self._content(), None, self._artifact(), b"data")
        self.assertIn("no recorded integrity", error)

    def test_allows_idempotent_existing_artifact(self):
        artifact = self._artifact()
        ca = SimpleNamespace(artifact=SimpleNamespace(sha256=artifact.sha256), save=Mock())
        self.assertIsNone(_validate_against_existing(self._content(), ca, artifact, b"data"))

    def test_rejects_existing_artifact_with_different_bytes(self):
        artifact = self._artifact(sha256="a" * 64)
        ca = SimpleNamespace(artifact=SimpleNamespace(sha256="b" * 64), save=Mock())
        error = _validate_against_existing(self._content(), ca, artifact, b"data")
        self.assertIn("different content", error)
