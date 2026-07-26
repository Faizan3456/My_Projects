#!/usr/bin/env bash
# Push the current working tree to the VPS and (re)build the stack.
#
#   deploy/deploy.sh <vps-host-or-ip> [ssh-user]
#
# Secrets are never copied: deploy/.env.prod lives only on the server.

set -euo pipefail

HOST=${1:-}
USER_NAME=${2:-root}
APP_DIR=/opt/collective
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if [[ -z $HOST ]]; then
	echo "usage: deploy/deploy.sh <vps-host-or-ip> [ssh-user]" >&2
	exit 1
fi

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

log "Checking connectivity to $USER_NAME@$HOST"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$USER_NAME@$HOST" 'echo reachable' || {
	echo "Cannot reach the host with key-based SSH. Add your public key to the" >&2
	echo "VPS first (Hostinger hPanel -> VPS -> SSH keys, or ssh-copy-id)." >&2
	exit 1
}

log "Copying the project to $HOST:$APP_DIR"
rsync -az --delete \
	--exclude '.git' \
	--exclude 'backend/.venv' \
	--exclude 'backend/__pycache__' \
	--exclude '**/__pycache__' \
	--exclude '.pytest_cache' \
	--exclude 'frontend/node_modules' \
	--exclude 'frontend/.next' \
	--exclude '.env' \
	--exclude 'deploy/.env.prod' \
	"$HERE/" "$USER_NAME@$HOST:$APP_DIR/"

log "Verifying the server has its secrets file"
ssh "$USER_NAME@$HOST" "test -f $APP_DIR/deploy/.env.prod" || {
	echo "Missing $APP_DIR/deploy/.env.prod on the server." >&2
	echo "Create it there from deploy/.env.prod.example, then re-run." >&2
	exit 1
}

log "Building and starting the stack"
ssh "$USER_NAME@$HOST" "cd $APP_DIR/deploy && \
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build"

log "Waiting for the API to report healthy"
ssh "$USER_NAME@$HOST" "cd $APP_DIR/deploy && \
	for i in \$(seq 1 30); do \
		if docker compose -f docker-compose.prod.yml --env-file .env.prod \
			exec -T backend python -c \
			'import urllib.request;print(urllib.request.urlopen(\"http://localhost:8000/healthz\",timeout=5).read().decode())' \
			2>/dev/null; then exit 0; fi; \
		sleep 4; \
	done; \
	echo 'API did not become healthy in time'; \
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail 40 backend; \
	exit 1"

SITE=$(ssh "$USER_NAME@$HOST" "grep -m1 '^SITE_DOMAIN=' $APP_DIR/deploy/.env.prod | cut -d= -f2")
log "Deployed. Check https://$SITE"
