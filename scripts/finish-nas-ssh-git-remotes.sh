#!/usr/bin/env bash
# Run AFTER you add BOTH deploy-key public halves to GitHub (see README Git auth section).
# Usage on NAS over SSH:
#   bash scripts/finish-nas-ssh-git-remotes.sh
set -euo pipefail

export PATH="/usr/local/bin:$PATH"

PicturesRemote="git@github-apr70-pictures:brooklyn70/apr70-pictures.git"
OrchRemote="git@github-apr70-orchestrator:brooklyn70/apr70-orchestrator.git"

cd /volume1/apps/apr70-pictures
GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes" git remote set-url origin "$PicturesRemote"
GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes" git ls-remote origin HEAD

cd /volume1/apps/apr70-orchestrator
GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes" git remote set-url origin "$OrchRemote"
GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes" git ls-remote origin HEAD

echo "Done: both remotes are SSH-alias + ls-remote HEAD succeeded."
