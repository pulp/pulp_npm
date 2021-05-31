# Generated by Django 2.2.19 on 2021-02-23 18:05

from django.db import migrations, models, transaction
import django.db.models.deletion


def migrate_data_from_old_model_to_new_model_up(apps, schema_editor):
    """ Move objects from NpmDistribution to NewNpmDistribution."""
    NpmDistribution = apps.get_model('npm', 'NpmDistribution')
    NewNpmDistribution = apps.get_model('npm', 'NewNpmDistribution')
    for npm_distribution in NpmDistribution.objects.all():
        with transaction.atomic():
            NewNpmDistribution(
                pulp_id=npm_distribution.pulp_id,
                pulp_created=npm_distribution.pulp_created,
                pulp_last_updated=npm_distribution.pulp_last_updated,
                pulp_type=npm_distribution.pulp_type,
                name=npm_distribution.name,
                base_path=npm_distribution.base_path,
                content_guard=npm_distribution.content_guard,
                remote=npm_distribution.remote,
                repository_version=npm_distribution.repository_version,
                repository=npm_distribution.repository
            ).save()
            npm_distribution.delete()


def migrate_data_from_old_model_to_new_model_down(apps, schema_editor):
    """ Move objects from NewNpmDistribution to NpmDistribution."""
    NpmDistribution = apps.get_model('npm', 'NpmDistribution')
    NewNpmDistribution = apps.get_model('npm', 'NewNpmDistribution')
    for npm_distribution in NewNpmDistribution.objects.all():
        with transaction.atomic():
            NpmDistribution(
                pulp_id=npm_distribution.pulp_id,
                pulp_created=npm_distribution.pulp_created,
                pulp_last_updated=npm_distribution.pulp_last_updated,
                pulp_type=npm_distribution.pulp_type,
                name=npm_distribution.name,
                base_path=npm_distribution.base_path,
                content_guard=npm_distribution.content_guard,
                remote=npm_distribution.remote,
                repository_version=npm_distribution.repository_version,
                repository=npm_distribution.repository
            ).save()
            npm_distribution.delete()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('npm', '0001_initial'),
        ('core', '0062_add_new_distribution_mastermodel'),
    ]

    operations = [
        migrations.CreateModel(
            name='NewNpmDistribution',
            fields=[
                ('distribution_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, related_name='npm_npmdistribution', serialize=False, to='core.Distribution')),
            ],
            options={
                'default_related_name': '%(app_label)s_%(model_name)s',
            },
            bases=('core.distribution',),
        ),
        migrations.RunPython(
            code=migrate_data_from_old_model_to_new_model_up,
            reverse_code=migrate_data_from_old_model_to_new_model_down,
        ),
        migrations.DeleteModel(
            name='NpmDistribution',
        ),
        migrations.RenameModel(
            old_name='NewNpmDistribution',
            new_name='NpmDistribution',
        ),
    ]
