#!/bin/bash
# Create .env file from GitHub secrets
set -mveuo pipefail

python3 .ci/scripts/secrets.py $1
echo $1 >> secrets.json
# cat secrets.json
# env_filename=".env"

# jq -r 'to_entries|map("\(.key)=\(.value|tostring)")|.[]' <<< `cat secrets.json` > "$env_filename"
cat .env >> $GITHUB_ENV
