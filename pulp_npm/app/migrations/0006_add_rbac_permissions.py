from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("npm", "0005_alter_package_version"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="npmremote",
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "permissions": [
                    ("manage_roles_npmremote", "Can manage roles on npm remotes"),
                ],
            }
        ),
        migrations.AlterModelOptions(
            name="npmrepository",
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "permissions": [
                    ("sync_npmrepository", "Can start a sync task"),
                    ("modify_npmrepository", "Can modify content of the repository"),
                    ("manage_roles_npmrepository", "Can manage roles on npm repositories"),
                ]
            }
        ),
        migrations.AlterModelOptions(
            name="npmdistribution",
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "permissions": [
                    ("manage_roles_npmdistribution", "Can manage roles on npm distributions"),
                ]
            }
        ),
    ]
