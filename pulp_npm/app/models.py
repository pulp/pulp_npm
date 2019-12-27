"""
Check `Plugin Writer's Guide`_ for more details.

.. _Plugin Writer's Guide:
    http://docs.pulpproject.org/en/3.0/nightly/plugins/plugin-writer/index.html
"""

from logging import getLogger

from django.db import models

from pulpcore.plugin.models import Content, ContentArtifact, Remote, Repository, Publisher

logger = getLogger(__name__)


class NpmContent(Content):
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

    TYPE = "npm"


class NpmPublisher(Publisher):
    """
    A Publisher for NpmContent.

    Define any additional fields for your new publisher if needed.
    """

    TYPE = "npm"

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"


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

    CONTENT_TYPES = [NpmContent]

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
