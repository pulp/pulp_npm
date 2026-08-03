from django.conf import settings


def npm_has_repository_perm(request, view, action, perm="npm.view_npmrepository"):
    """
    Check if the user has ``perm`` on the distribution's backing repository.

    Used by the npm publish API views where the distribution (and its
    repository) is resolved from the URL path rather than from a viewset
    querset. Returns ``True`` if the distribution has no repository.
    """
    if request.user.has_perm(perm):
        return True
    if settings.DOMAIN_ENABLED:
        if request.user.has_perm(perm, obj=request.pulp_domain):
            return True
    if repo := view.distribution.repository:
        # Cast repo, need NpmRepository instead of Repository
        return request.user.has_perm(perm, obj=repo.cast())
    return True
