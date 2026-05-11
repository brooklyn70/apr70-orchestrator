#!/usr/bin/env sh
# Run on the DSM host (SSH) after orchestrator --once/--loop batches if you SSH into
# /volume1/apps/apr70-pictures as a non-root user who cannot write git objects anymore.
#
# Synology DSM: optionally schedule this hourly for the APR70 site checkout.
#
# Usage:
#   bash scripts/chown-mounted-repos-on-nas.sh
#
# Customize OWNER if your DSM login uid:gid differs (check: id).

set -euo pipefail

OWNER="${ORCHESTRATOR_CHOWN_OWNER:-caruso:users}"

sudo chown -R "$OWNER" /volume1/apps/apr70-pictures
sudo chown -R "$OWNER" /volume1/apps/apr70-orchestrator/state
