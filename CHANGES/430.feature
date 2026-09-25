Added repository package catalog and metrics endpoints, plus ``collapse_builds``,
``base_version``, and exact ``version`` filtering on the npm package content API.
PackageList includes ``last_updated``, ``ordering`` (``name``, ``last_updated``),
``name__icontains``, and newest-first versions. Rebuild suffixes match
``\.[a-zA-Z]+-[^.]+$`` (including predisclosure ``-nNNNN``). Existing installs
pick up access policy for the new actions on migrate unless the policy was
customized.
