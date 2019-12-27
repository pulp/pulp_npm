import unittest
from django.test import TestCase

from pulp_npm.app.serializers import NpmContentSerializer
from pulp_npm.app.models import NpmContent

from pulpcore.plugin.models import Artifact


# Fill data with sufficient information to create NpmContent
# Provide sufficient parameters to create the NpmContent object
# Depending on the base class of the serializer, provide either "_artifact" or "_artifacts"
@unittest.skip("FIXME: plugin writer action required")
class TestNpmContentSerializer(TestCase):
    """Test NpmContentSerializer."""

    def setUp(self):
        """Set up the NpmContentSerializer tests."""
        self.artifact = Artifact.objects.create(
            md5="ec0df26316b1deb465d2d18af7b600f5",
            sha1="cf6121b0425c2f2e3a2fcfe6f402d59730eb5661",
            sha224="9a6297eb28d91fad5277c0833856031d0e940432ad807658bd2b60f4",
            sha256="c8ddb3dcf8da48278d57b0b94486832c66a8835316ccf7ca39e143cbfeb9184f",
            sha384="53a8a0cebcb7780ed7624790c9d9a4d09ba74b47270d397f5ed7bc1c46777a0fbe362aaf2bbe7f0966a350a12d76e28d",  # noqa
            sha512="a94a65f19b864d184a2a5e07fa29766f08c6d49b6f624b3dd3a36a98267b9137d9c35040b3e105448a869c23c2aec04c9e064e3555295c1b8de6515eed4da27d",  # noqa
            size=1024,
        )

    def test_valid_data(self):
        """Test that the NpmContentSerializer accepts valid data."""
        data = {"_artifact": "/pulp/api/v3/artifacts/{}/".format(self.artifact.pk)}
        serializer = NpmContentSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_duplicate_data(self):
        """Test that the NpmContentSerializer does not accept data."""
        NpmContent.objects.create(artifact=self.artifact)
        data = {"_artifact": "/pulp/api/v3/artifacts/{}/".format(self.artifact.pk)}
        serializer = NpmContentSerializer(data=data)
        self.assertFalse(serializer.is_valid())
