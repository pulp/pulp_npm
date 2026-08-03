from gettext import gettext as _

from django.db.models.signals import post_migrate

from pulpcore.plugin import PulpPluginAppConfig


class PulpNpmPluginAppConfig(PulpPluginAppConfig):
    """Entry point for the npm plugin."""

    name = "pulp_npm.app"
    label = "npm"
    version = "0.10.0.dev"
    python_package_name = "pulp-npm"
    domain_compatible = True

    def ready(self):
        super().ready()
        post_migrate.connect(
            _populate_npm_publish_access_policies,
            sender=self,
            dispatch_uid="populate_npm_publish_access_policies",
        )


def _populate_npm_publish_access_policies(sender, apps, verbosity, **kwargs):
    """
    Create or update AccessPolicy records for plain APIViews that
    pulpcore can't auto-discover (`NpmPublishView`, `NpmPingView`, `NpmWhoamiView`).

    On first run: creates the DB record from each view's `DEFAULT_ACCESS_POLICY`.
    On subsequent runs: updates the record to match the code **unless** an admin
    has customized it, in which case it's left alone.
    """

    from pulp_npm.app.npm_publish_api import NpmPingView, NpmPublishView, NpmWhoamiView

    try:
        AccessPolicy = apps.get_model("core", "AccessPolicy")
    except LookupError:
        if verbosity >= 1:
            print(_("AccessPolicy model does not exist. Skipping initialization."))
        return

    for viewset in (NpmPublishView, NpmPingView, NpmWhoamiView):
        access_policy = getattr(viewset, "DEFAULT_ACCESS_POLICY", None)
        if access_policy is None:
            continue
        viewset_name = viewset.urlpattern()
        db_access_policy, created = AccessPolicy.objects.get_or_create(
            viewset_name=viewset_name, defaults=access_policy
        )
        if created:
            if verbosity >= 1:
                print(f"Access policy for {viewset_name} created.")
        elif not db_access_policy.customized:
            dirty = False
            for key in ["statements", "creation_hooks", "queryset_scoping"]:
                value = access_policy.get(key)
                if getattr(db_access_policy, key, None) != value:
                    setattr(db_access_policy, key, value)
                    dirty = True
            if dirty:
                db_access_policy.save()
                if verbosity >= 1:
                    print(f"Access policy for {viewset_name} updated.")
