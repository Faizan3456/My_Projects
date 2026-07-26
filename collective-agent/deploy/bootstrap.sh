#!/usr/bin/env bash
# Prepare a fresh Ubuntu/Debian VPS to run the stack. Run once, as root:
#
#   ssh root@<vps-ip> 'bash -s' < deploy/bootstrap.sh
#
# Installs Docker, opens only the ports the stack needs, and creates /opt/collective.
# Idempotent: safe to re-run.

set -euo pipefail

APP_DIR=/opt/collective

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
	echo "Run as root (or with sudo)." >&2
	exit 1
fi

log "Updating package lists"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

log "Installing prerequisites"
apt-get install -y -qq ca-certificates curl gnupg rsync ufw

if ! command -v docker >/dev/null 2>&1; then
	log "Installing Docker from the official repository"
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
		gpg --dearmor -o /etc/apt/keyrings/docker.gpg
	chmod a+r /etc/apt/keyrings/docker.gpg
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
		>/etc/apt/sources.list.d/docker.list
	apt-get update -qq
	apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
		docker-buildx-plugin docker-compose-plugin
else
	log "Docker already installed: $(docker --version)"
fi

systemctl enable --now docker

log "Configuring the firewall"
# Order matters: allow SSH before enabling, or you lock yourself out.
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

log "Creating $APP_DIR"
mkdir -p "$APP_DIR"

log "Enabling automatic security updates"
apt-get install -y -qq unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

cat <<'NEXT'

Bootstrap complete.

Next, from your Mac:
  1. deploy/deploy.sh <vps-ip>          # copies the project and builds
  2. ssh root@<vps-ip>
     cd /opt/collective/deploy
     cp .env.prod.example .env.prod && chmod 600 .env.prod
     # fill in POSTGRES_PASSWORD, SERVICE_TOKEN and any provider keys
  3. docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

Caddy will request a TLS certificate on first start, which needs the DNS A record
for the site to already point at this server.
NEXT
