Added Role-Based Access Control (RBAC) to all npm viewsets and the npm publish API.
Users can now be assigned creator, owner, or viewer roles on repositories, remotes,
and distributions. The npm publish endpoint requires ``modify_npmrepository``
permission on the backing repository.
