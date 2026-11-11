from django.core.management.base import BaseCommand, CommandError
from django_guid import set_guid
from django_guid.utils import generate_guid

from pulpcore.plugin.tasking import dispatch

from pulp_npm.app.models import NpmRepository
from pulp_npm.app.tasks.backfill import backfill_repository_manifests


class Command(BaseCommand):
    help = "Backfill npm package manifests and checksums from stored tarballs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repository",
            required=True,
            help="NpmRepository pk or href.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing manifests instead of only filling empty ones.",
        )

    def handle(self, *args, **options):
        repository_pk = options["repository"].rstrip("/").split("/")[-1]
        try:
            repository = NpmRepository.objects.get(pk=repository_pk)
        except (NpmRepository.DoesNotExist, ValueError):
            raise CommandError(f"NpmRepository {options['repository']!r} does not exist.")

        set_guid(generate_guid())
        task = dispatch(
            backfill_repository_manifests,
            exclusive_resources=[repository],
            kwargs={
                "repository_pk": str(repository.pk),
                "overwrite": options["overwrite"],
            },
        )
        self.stdout.write(f"Dispatched backfill task {task.pk} for {repository.name}.")
