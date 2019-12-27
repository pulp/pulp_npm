"""
Check `Plugin Writer's Guide`_ for more details.

.. _Plugin Writer's Guide:
    http://docs.pulpproject.org/en/3.0/nightly/plugins/plugin-writer/index.html
"""

from logging import getLogger

from django.contrib.postgres.fields import JSONField
from django.db import models

from pulpcore.plugin.models import Content, Remote, Repository

logger = getLogger(__name__)


class Package(Content):
    """
    The "npm" content type.

    Define fields you need for your new content type and
    specify uniqueness constraint to identify unit of this type.

    For example::

        field1 = models.TextField()
        field2 = models.IntegerField()
        field3 = models.CharField()

        class Meta:
            default_related_name = "%(app_label)s_%(model_name)s"
            unique_together = (field1, field2)
    """

    TYPE = 'package'
    repo_key_fields = ("_id", "_rev", "name")

    _id = models.CharField(max_length=214)
    _rev = models.CharField(max_length=64)
    name = models.CharField(max_length=214)
    description = models.TextField()
    dist_tags = JSONField(default=dict)
    versions = JSONField(default=dict)
    maintainers = JSONField(default=list)
    time = JSONField(default=dict)
    author = JSONField(default=dict)
    repository = JSONField(default=dict)
    readme = models.TextField()
    readmeFilename = models.CharField(max_length=255)
    homepage = models.CharField(max_length=255)
    keywords = JSONField(default=list)
    bugs = JSONField(default=dict)
    users = JSONField(default=dict)
    license = models.CharField(max_length=16)

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        unique_together = ("_id", "_rev", "name")


class NpmRemote(Remote):
    """
    A Remote for NpmContent.

    Define any additional fields for your new remote if needed.
    """

    TYPE = "npm"

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"


class NpmRepository(Repository):
    """
    A Repository for NpmContent.

    Define any additional fields for your new repository if needed.
    """

    TYPE = "npm"

    CONTENT_TYPES = [Package]

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
