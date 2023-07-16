# Generated by Django 4.2.1 on 2023-05-25 13:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0106_alter_artifactdistribution_distribution_ptr_and_more"),
        ("npm", "0002_swap_distribution_model"),
    ]

    operations = [
        migrations.AlterField(
            model_name="npmdistribution",
            name="distribution_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="core.distribution",
            ),
        ),
        migrations.AlterField(
            model_name="npmremote",
            name="remote_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="core.remote",
            ),
        ),
        migrations.AlterField(
            model_name="npmrepository",
            name="repository_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="core.repository",
            ),
        ),
        migrations.AlterField(
            model_name="package",
            name="content_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="core.content",
            ),
        ),
    ]