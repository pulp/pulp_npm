DRF_ACCESS_POLICY = {
    "dynaconf_merge_unique": True,
    "reusable_conditions": ["pulp_npm.app.global_access_conditions"],
}

# How long a publish request waits, in seconds, for its turn to add the package to the
# repository while other publishes to the same repository go first. After that it answers 429.
NPM_PUBLISH_TASK_TIMEOUT = 30
