from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import AddIndexConcurrently, TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False  # required for CONCURRENTLY

    dependencies = [
        ("npm", "0006_add_rbac_permissions"),
    ]

    operations = [
        TrigramExtension(),
        AddIndexConcurrently(
            model_name="package",
            index=GinIndex(
                fields=["name"],
                name="npm_package_name_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]
