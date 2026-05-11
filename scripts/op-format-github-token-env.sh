#!/usr/bin/env bash
# Print a GITHUB_TOKEN= line for apr70-orchestrator/.env using 1Password secret ref syntax.
# Usage: ./scripts/op-format-github-token-env.sh "Exact item title from 1Password API vault"
# Vault defaults to API (override: API_VAULT=my-vault-name).
set -euo pipefail
title=${1:?"usage: $0 \"Item title as shown in 1Password\""}
vault=${API_VAULT:-API}
enc=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$title")
echo "GITHUB_TOKEN=\"op://${vault}/${enc}/credential\""
echo "# If inject fails, try field password instead of credential (item type dependent)."
