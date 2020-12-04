#!/bin/bash
# Create .env file from GitHub secrets

json_secrets_str=$1
env_filename=".env"

jq -r 'to_entries|map("\(.key)=\(.value|tostring)")|.[]' <<< "$json_secrets_str" > "$env_filename"
cat .env >> $GITHUB_ENV
