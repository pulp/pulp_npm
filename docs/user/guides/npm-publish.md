# Publish Packages with npm / yarn

The `pulp_npm` plugin supports the standard npm registry publish protocol, allowing you to
use `npm publish` or `yarn publish` directly against a Pulp NPM repository -- no Pulp-specific
tooling required.

## Prerequisites

### 1. Create a Repository

```bash
pulp npm repository create --name my-npm-repo
```

### 2. Create a Distribution

Create a distribution pointing to the repository. The `base_path` determines the URL
segment clients will use.

```bash
pulp npm distribution create \
  --name my-npm-repo \
  --base-path my-npm-repo \
  --repository my-npm-repo
```

Your registry URL will be:

```
https://pulp.example.com/npm/<domain>/my-npm-repo/
```

If domains are not enabled, omit the `<domain>` segment:

```
https://pulp.example.com/npm/my-npm-repo/
```

## Configure Authentication

Pulp uses standard HTTP basic authentication. Configure your `.npmrc` with credentials
for the registry URL.

### Using npm

```bash
npm set //pulp.example.com/npm/default/my-npm-repo/:_auth=$(echo -n 'admin:password' | base64)
```

### Using yarn (v1 / Classic)

Yarn Classic reads the same `.npmrc` file, so the npm command above works. Alternatively,
add it directly:

```bash
echo '//pulp.example.com/npm/default/my-npm-repo/:_auth='$(echo -n 'admin:password' | base64) >> ~/.npmrc
```

### Using yarn (v2+ / Berry)

```bash
yarn config set npmRegistryServer https://pulp.example.com/npm/default/my-npm-repo/
yarn config set npmAuthToken "$(echo -n 'admin:password' | base64)"
```

## Publish a Package

### Create a test package

```bash
mkdir my-package && cd my-package

cat > package.json <<'EOF'
{
  "name": "my-package",
  "version": "1.0.0",
  "description": "My npm package hosted on Pulp",
  "main": "index.js",
  "license": "MIT"
}
EOF

echo "module.exports = 'hello from pulp';" > index.js
```

### Publish with npm

```bash
npm publish --registry https://pulp.example.com/npm/default/my-npm-repo/
```

### Publish with yarn (v1)

```bash
yarn publish --registry https://pulp.example.com/npm/default/my-npm-repo/
```

### Publish with yarn (v2+)

```bash
yarn npm publish
```

## Publish Scoped Packages

Scoped packages (e.g. `@myorg/my-lib`) work the same way. The scope is URL-encoded
automatically by npm/yarn:

```bash
npm publish --registry https://pulp.example.com/npm/default/my-npm-repo/
```

You can also set the registry per-scope in `.npmrc`:

```ini
@myorg:registry=https://pulp.example.com/npm/default/my-npm-repo/
//pulp.example.com/npm/default/my-npm-repo/:_auth=YWRtaW46cGFzc3dvcmQ=
```

## Verify Published Packages

### Check the repository

```bash
pulp npm repository show --name my-npm-repo
```

### Query the package metadata

The distribution serves standard npm registry JSON. You can query it with curl or
point npm/yarn at it to install packages:

```bash
# View package metadata
curl https://pulp.example.com/pulp/content/default/my-npm-repo/my-package

# Install from your Pulp registry
npm install my-package --registry https://pulp.example.com/pulp/content/default/my-npm-repo/
```

## Registry Utility Endpoints

The registry also exposes standard utility endpoints:

```bash
# Health check
curl https://pulp.example.com/npm/default/my-npm-repo/-/ping
# Returns: {}

# Authenticated user info
curl -u admin:password https://pulp.example.com/npm/default/my-npm-repo/-/whoami
# Returns: {"username": "admin"}
```
