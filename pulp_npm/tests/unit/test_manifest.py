import unittest

from pulp_npm.app.utils import (
    MANIFEST_MAX_BYTES,
    PACKUMENT_MANIFEST_FIELDS,
    sanitize_manifest,
)


class TestSanitizeManifest(unittest.TestCase):
    """Only allow-listed, bounded values may reach the database and registry."""

    def test_keeps_allowed_fields(self):
        source = {
            "name": "example",
            "version": "1.0.0",
            "description": "An example",
            "license": "MIT",
            "type": "module",
            "dependencies": {"dep-a": "^1.0.0"},
            "optionalDependencies": {"native": "^2"},
            "peerDependencies": {"react": ">=18"},
            "engines": {"node": ">=20"},
            "os": ["linux"],
            "cpu": ["x64"],
            "libc": ["glibc"],
            "bin": {"example": "./bin/example.js"},
            "scripts": {"postinstall": "node install.js"},
            "hasInstallScript": True,
        }

        result = sanitize_manifest(source)

        for field in source:
            if field in ("name", "version"):
                self.assertNotIn(field, result)
            else:
                self.assertIn(field, result)
        self.assertEqual(result["dependencies"], {"dep-a": "^1.0.0"})
        self.assertEqual(result["libc"], ["glibc"])

    def test_drops_unknown_and_dist_fields(self):
        result = sanitize_manifest(
            {
                "description": "ok",
                "dist": {"tarball": "https://evil.example/pkg.tgz"},
                "_id": "example@1.0.0",
                "readme": "x" * 1000,
            }
        )

        self.assertEqual(result, {"description": "ok"})
        self.assertNotIn("dist", result)

    def test_drops_invalid_field_types(self):
        result = sanitize_manifest(
            {
                "description": 123,
                "dependencies": ["not", "a", "map"],
                "os": "linux",
                "hasInstallScript": "yes",
                "scripts": {"postinstall": ["not", "a", "string"]},
                "engines": {"node": ">=20"},
            }
        )

        self.assertEqual(result, {"engines": {"node": ">=20"}})

    def test_rejects_unsafe_bin_paths(self):
        for value in ("/usr/bin/evil", "../evil", "..\\evil"):
            with self.subTest(value=value):
                self.assertNotIn("bin", sanitize_manifest({"bin": value}))

    def test_normalizes_directories_bin(self):
        result = sanitize_manifest({"directories": {"bin": "./bin", "man": "./man"}})

        self.assertEqual(result["bin"], "./bin")
        self.assertEqual(result["directories"], {"bin": "./bin", "man": "./man"})

    def test_expands_boolean_bundle_dependencies(self):
        result = sanitize_manifest(
            {
                "dependencies": {"dep-a": "^1.0.0", "dep-b": "^2.0.0"},
                "bundleDependencies": True,
            }
        )

        self.assertEqual(sorted(result["bundleDependencies"]), ["dep-a", "dep-b"])

    def test_rejects_oversized_manifest(self):
        dependencies = {f"dep-{i}": "x" * 3000 for i in range(100)}
        self.assertGreater(len(str(dependencies)), MANIFEST_MAX_BYTES)

        with self.assertRaises(ValueError):
            sanitize_manifest({"dependencies": dependencies}, strict=True)
        self.assertEqual(sanitize_manifest({"dependencies": dependencies}), {})

    def test_non_object_manifest(self):
        with self.assertRaises(ValueError):
            sanitize_manifest(["not", "an", "object"], strict=True)
        self.assertEqual(sanitize_manifest(["not", "an", "object"]), {})

    def test_drops_nul_bytes(self):
        result = sanitize_manifest({"description": "bad\x00value"})
        self.assertNotIn("description", result)

    def test_allow_list_is_authoritative(self):
        # Every served key must also be accepted by the sanitizer.
        source = {
            "description": "ok",
            "license": "MIT",
            "main": "index.js",
            "type": "module",
            "bin": {"example": "./bin/example.js"},
            "directories": {"bin": "./bin"},
            "scripts": {"test": "node test.js"},
            "engines": {"node": ">=20"},
            "os": ["linux"],
            "cpu": ["x64"],
            "libc": ["glibc"],
            "dependencies": {"dep-a": "^1.0.0"},
            "devDependencies": {"pytest": "^7"},
            "peerDependencies": {"react": ">=18"},
            "peerDependenciesMeta": {"react": {"optional": True}},
            "optionalDependencies": {"native": "^2"},
            "bundleDependencies": ["dep-a"],
            "bundledDependencies": ["dep-a"],
            "exports": {".": "./index.js"},
            "dependenciesMeta": {"native": {"optional": True}},
            "deprecated": "use something else",
            "hasInstallScript": True,
        }

        result = sanitize_manifest(source)

        self.assertEqual(set(result), set(source))
        self.assertEqual(set(PACKUMENT_MANIFEST_FIELDS), set(source))

    def test_derives_has_install_script_from_lifecycle_scripts(self):
        for script in ("preinstall", "install", "postinstall"):
            with self.subTest(script=script):
                self.assertTrue(
                    sanitize_manifest({"scripts": {script: "node setup.js"}})["hasInstallScript"]
                )
        self.assertFalse(
            sanitize_manifest({"scripts": {"test": "node test.js"}})["hasInstallScript"]
        )

    def test_preserves_has_install_script_without_scripts(self):
        # Abbreviated upstream documents may carry the flag without the scripts.
        result = sanitize_manifest({"hasInstallScript": True})
        self.assertTrue(result["hasInstallScript"])

    def test_cleans_exports_and_dependencies_meta(self):
        result = sanitize_manifest(
            {
                "exports": {
                    ".": {"import": "./index.mjs", "require": "./index.cjs"},
                    "./package.json": "./package.json",
                },
                "dependenciesMeta": {"native": {"optional": True}},
            }
        )

        self.assertEqual(result["exports"]["."]["import"], "./index.mjs")
        self.assertTrue(result["dependenciesMeta"]["native"]["optional"])

    def test_drops_excessively_nested_json(self):
        value = "./index.js"
        for _ in range(6):
            value = {"nested": value}
        self.assertNotIn("exports", sanitize_manifest({"exports": value}))
