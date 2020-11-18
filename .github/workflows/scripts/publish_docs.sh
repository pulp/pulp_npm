#!/bin/bash

set -euv

export WORKSPACE=$GITHUB_WORKSPACE
export BRANCH=$GITHUB_REF_NAME_SLUG

mkdir ~/.ssh
echo "$PULP_DOCS_KEY" > ~/.ssh/pulp-infra
chmod 600 ~/.ssh/pulp-infra

echo "docs.pulpproject.org,8.43.85.236 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBGXG+8vjSQvnAkq33i0XWgpSrbco3rRqNZr0SfVeiqFI7RN/VznwXMioDDhc+hQtgVhd6TYBOrV07IMcKj+FAzg=" >> ~/.ssh/known_hosts
chmod 644 ~/.ssh/known_hosts

pip3 install -r doc_requirements.txt

export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE=pulpcore.app.settings
export PULP_SETTINGS=$WORKSPACE/.github/settings/settings.py

eval "$(ssh-agent -s)" #start the ssh agent
ssh-add ~/.ssh/pulp-infra

if [[ $GITHUB_REF = "refs/heads"* ]]; then
  type="nightly"
else
  type="tag"
fi

python3 $WORKSPACE/.ci/scripts/docs-builder.py --build-type $type --branch $BRANCH
