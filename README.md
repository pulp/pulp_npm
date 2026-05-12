# pulp-npm

<!--toc:start-->
- [pulp-npm](#pulp-npm)
  - [About Pulp](#about-pulp)
  - [About pulp_npm](#about-pulp_npm)
  - [License](#license)
<!--toc:end-->

A Pulp plugin to support npm packages.

For more information, please see the [documentation](docs/index.md) or the [Pulp project page](https://pulpproject.org/).

## About Pulp
Pulp is a platform for managing repositories of content, such as software
packages, and pushing that content out to large numbers of consumers.

Using Pulp you can:
- Locally mirror all or part of a repository
- Host your own content in a new repository
- Manage content from multiple sources in one place
- Promote content through different repos in an organized way

## About pulp_npm
The plugin pulp_npm supports mirroring npm packages and hosting your own npm registry with Pulp.
Since the plugin is API compatible with the NPM Registry, you can use standard npm/yarn tooling:

**Install packages from Pulp:**
```bash
npm install --registry https://pulp.example.com/pulp/content/{domain}/my-repo/ react
```

**Publish packages to Pulp with npm or yarn:**
```bash
npm publish --registry https://pulp.example.com/npm/{domain}/my-repo/
yarn publish --registry https://pulp.example.com/npm/{domain}/my-repo/
```

See the [Publish Packages with npm / yarn](docs/user/guides/npm-publish.md) guide for full setup instructions.

## License
- License: GPLv2+
- Documentation: https://pulpproject.org/
- Source: https://github.com/pulp/pulp_npm/
- Bugs: https://github.com/pulp/pulp_npm/issues
