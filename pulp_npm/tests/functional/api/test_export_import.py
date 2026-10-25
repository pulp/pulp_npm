"""
Tests PulpExporter and PulpImporter functionality for npm repositories.

NOTE: assumes ALLOWED_EXPORT_PATHS and ALLOWED_IMPORT_PATHS settings contain "/tmp" - all tests
will be skipped if this is not the case.
"""

import uuid

import pytest
from django.conf import settings

from pulp_npm.tests.functional.constants import NPM_CONTENT_NAME

pytestmark = [
    pytest.mark.skipif(
        "/tmp" not in settings.ALLOWED_EXPORT_PATHS,
        reason="Cannot run export-tests unless /tmp is in ALLOWED_EXPORT_PATHS "
        f"({settings.ALLOWED_EXPORT_PATHS}).",
    ),
    pytest.mark.skipif(
        "/tmp" not in settings.ALLOWED_IMPORT_PATHS,
        reason="Cannot run import-tests unless /tmp is in ALLOWED_IMPORT_PATHS "
        f"({settings.ALLOWED_IMPORT_PATHS}).",
    ),
]


@pytest.mark.parallel
def test_export_then_import(
    npm_bindings,
    pulpcore_bindings,
    npm_repository_factory,
    npm_remote_factory,
    npm_package_url,
    npm_scoped_package_url,
    get_npm_content_paths,
    monitor_task,
    monitor_task_group,
    gen_object_with_cleanup,
):
    """Export npm repositories and import them back into fresh repositories."""
    # Prepare content: two repos with different packages so a wrong repo_mapping is detectable
    repo_a = npm_repository_factory()
    repo_b = npm_repository_factory()
    sync_tasks = [
        npm_bindings.RepositoriesNpmApi.sync(
            repo.pulp_href, {"remote": npm_remote_factory(url=url, policy="immediate").pulp_href}
        ).task
        for repo, url in ((repo_a, npm_package_url), (repo_b, npm_scoped_package_url))
    ]
    for task in sync_tasks:
        monitor_task(task)
    repo_ver_a = npm_bindings.RepositoriesNpmVersionsApi.read(f"{repo_a.versions_href}1/")
    repo_ver_b = npm_bindings.RepositoriesNpmVersionsApi.read(f"{repo_b.versions_href}1/")
    assert repo_ver_a.content_summary.present[NPM_CONTENT_NAME]["count"] == 1
    assert repo_ver_b.content_summary.present[NPM_CONTENT_NAME]["count"] == 1
    paths_a = set(get_npm_content_paths(repo_a, repo_ver_a.pulp_href))
    paths_b = set(get_npm_content_paths(repo_b, repo_ver_b.pulp_href))
    assert paths_a != paths_b

    # Prepare export
    exporter = gen_object_with_cleanup(
        pulpcore_bindings.ExportersPulpApi,
        {
            "name": str(uuid.uuid4()),
            "path": f"/tmp/{uuid.uuid4()}/",
            "repositories": [repo_a.pulp_href, repo_b.pulp_href],
        },
    )

    # Export
    task = monitor_task(
        pulpcore_bindings.ExportersPulpExportsApi.create(exporter.pulp_href, {}).task
    )
    assert len(task.created_resources) == 1
    export = pulpcore_bindings.ExportersPulpExportsApi.read(task.created_resources[0])
    assert len(exporter.repositories) == len(export.exported_resources)
    export_filename = next(
        f for f in export.output_file_info.keys() if f.endswith("tar.gz") or f.endswith("tar")
    )

    # Prepare import
    repo_c = npm_repository_factory()
    repo_d = npm_repository_factory()
    importer = gen_object_with_cleanup(
        pulpcore_bindings.ImportersPulpApi,
        {
            "name": str(uuid.uuid4()),
            "repo_mapping": {repo_a.name: repo_c.name, repo_b.name: repo_d.name},
        },
    )

    # Import
    import_response = pulpcore_bindings.ImportersPulpImportsApi.create(
        importer.pulp_href, {"path": export_filename}
    )
    monitor_task_group(import_response.task_group)
    repo_c = npm_bindings.RepositoriesNpmApi.read(repo_c.pulp_href)
    repo_d = npm_bindings.RepositoriesNpmApi.read(repo_d.pulp_href)
    assert repo_c.latest_version_href == f"{repo_c.versions_href}1/"
    assert repo_d.latest_version_href == f"{repo_d.versions_href}1/"
    repo_ver_c = npm_bindings.RepositoriesNpmVersionsApi.read(f"{repo_c.versions_href}1/")
    repo_ver_d = npm_bindings.RepositoriesNpmVersionsApi.read(f"{repo_d.versions_href}1/")
    assert (
        repo_ver_c.content_summary.added[NPM_CONTENT_NAME]["count"]
        == repo_ver_a.content_summary.present[NPM_CONTENT_NAME]["count"]
    )
    assert (
        repo_ver_d.content_summary.added[NPM_CONTENT_NAME]["count"]
        == repo_ver_b.content_summary.present[NPM_CONTENT_NAME]["count"]
    )

    # Each destination must hold exactly its own source's packages
    assert set(get_npm_content_paths(repo_c, repo_ver_c.pulp_href)) == paths_a
    assert set(get_npm_content_paths(repo_d, repo_ver_d.pulp_href)) == paths_b

    # Import a second time
    import_response = pulpcore_bindings.ImportersPulpImportsApi.create(
        importer.pulp_href, {"path": export_filename}
    )
    monitor_task_group(import_response.task_group)
    assert len(pulpcore_bindings.ImportersPulpImportsApi.list(importer.pulp_href).results) == 2
    for repo in (repo_c, repo_d):
        repo = npm_bindings.RepositoriesNpmApi.read(repo.pulp_href)
        # still only one version as pulp won't create a new version if nothing changed
        assert repo.latest_version_href == f"{repo.versions_href}1/"
