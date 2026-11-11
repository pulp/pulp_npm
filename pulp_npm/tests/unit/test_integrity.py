import base64
import unittest
from types import SimpleNamespace

from pulp_npm.app.utils import (
    parse_shasum,
    parse_sri,
    sri_from_artifact,
    validate_upstream_integrity,
)

SHA512_HEX = "ab" * 64
SHA512_SRI = "sha512-" + base64.b64encode(bytes.fromhex(SHA512_HEX)).decode()
SHA256_HEX = "cd" * 32
SHA256_SRI = "sha256-" + base64.b64encode(bytes.fromhex(SHA256_HEX)).decode()
SHA1_HEX = "ef" * 20


class TestIntegrity(unittest.TestCase):
    def test_sri_from_artifact(self):
        artifact = SimpleNamespace(sha512=SHA512_HEX)
        self.assertEqual(sri_from_artifact(artifact), SHA512_SRI)

    def test_sri_from_artifact_missing_or_invalid(self):
        self.assertIsNone(sri_from_artifact(SimpleNamespace(sha512=None)))
        self.assertIsNone(sri_from_artifact(SimpleNamespace(sha512="not-hex")))
        self.assertIsNone(sri_from_artifact(SimpleNamespace(sha512="ab" * 20)))

    def test_parse_sri(self):
        self.assertEqual(parse_sri(SHA512_SRI), ("sha512", SHA512_HEX))
        self.assertEqual(parse_sri(SHA256_SRI), ("sha256", SHA256_HEX))

    def test_parse_sri_prefers_strongest_token(self):
        combined = f"{SHA256_SRI} {SHA512_SRI}"
        self.assertEqual(parse_sri(combined), ("sha512", SHA512_HEX))

    def test_parse_sri_rejects_invalid(self):
        for value in (
            None,
            "",
            "sha512-not-base64!",
            "sha512-" + base64.b64encode(b"short").decode(),
            "md5-" + base64.b64encode(b"x" * 16).decode(),
        ):
            with self.subTest(value=value):
                self.assertIsNone(parse_sri(value))

    def test_parse_shasum(self):
        self.assertEqual(parse_shasum(SHA1_HEX.upper()), SHA1_HEX)
        self.assertIsNone(parse_shasum("not-a-sha1"))
        self.assertIsNone(parse_shasum(None))

    def test_validate_upstream_integrity(self):
        integrity, shasum = validate_upstream_integrity(
            {"integrity": SHA512_SRI, "shasum": SHA1_HEX}
        )
        self.assertEqual(integrity, SHA512_SRI)
        self.assertEqual(shasum, SHA1_HEX)

    def test_validate_upstream_integrity_drops_invalid(self):
        integrity, shasum = validate_upstream_integrity(
            {"integrity": "garbage", "shasum": "garbage"}
        )
        self.assertIsNone(integrity)
        self.assertIsNone(shasum)
        self.assertEqual(validate_upstream_integrity(None), (None, None))
