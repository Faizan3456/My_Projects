# Deploying to agents.openedgetechnologies.com

Target: a Hostinger VPS running Docker, with Caddy terminating TLS. The apex
domain and `www` are untouched — the Horizons site keeps serving those.

```
internet ──▶ Caddy (:80/:443, automatic TLS)
                ├── /api/*  ──▶ backend  (FastAPI, internal only)
                └── /*      ──▶ frontend (Next.js, internal only)
                                    │
                                 db (Postgres, internal only, named volume)
```

Nothing but Caddy publishes a port. Postgres is never reachable from the internet.

---

## What is already done

| Step | Status |
|---|---|
| Entra app registration in the OPENEDGETECHNOLOGIES tenant | **done** — see below |
| API JWT verification, service tokens, production guardrail | **done**, 18 tests |
| Dashboard sign-in gate (MSAL redirect flow) | **done** |
| Production images (backend + standalone Next.js) | **done**, both build and run |
| Caddy config, compose stack, bootstrap and deploy scripts | **done**, exercised locally on `:8080` |
| DNS record for `agents.` | **you** — needs Namecheap access |
| SSH access to the VPS | **you** — needs the host and a key |

### The app registration

Created in tenant `e9ba7eeb-8895-4350-8157-d17f5f523df3` (OPENEDGETECHNOLOGIES LTD):

| Field | Value |
|---|---|
| Name | Collective AI Agent System |
| Application (client) id | `403dfa3f-e031-4bbc-aa98-4884ae230c23` |
| Object id | `927f18c3-e209-4c05-8bfe-f2e14291a186` |
| Sign-in audience | `AzureADMyOrg` (this directory only) |
| Platform | SPA — `https://agents.openedgetechnologies.com`, `http://localhost:3000` |
| Exposed scope | `api://403dfa3f-…/access_as_user` |
| Access token version | 2 (the API validates v2.0 issuers) |
| Pre-authorised client | itself, so users see no consent prompt |

None of those values are secrets. There is **no client secret** — a SPA uses PKCE,
so there is nothing to leak or rotate here.

To remove it: `az ad app delete --id 403dfa3f-e031-4bbc-aa98-4884ae230c23`.

---

## 1. DNS (do this first)

TLS issuance fails until the name resolves, so add the record before deploying.
DNS is at Namecheap (`dns1/dns2.registrar-servers.com`):

> Namecheap → Domain List → openedgetechnologies.com → **Advanced DNS** →
> Add New Record

| Type | Host | Value | TTL |
|---|---|---|---|
| A | `agents` | *your VPS IPv4* | Automatic |

Add the AAAA equivalent too if the VPS has IPv6. Confirm with:

```bash
dig +short agents.openedgetechnologies.com
```

Do **not** point this at `147.79.79.157` or `145.223.124.131` — those are the
Hostinger CDN addresses serving the existing site.

## 2. Prepare the VPS

```bash
ssh root@<vps-ip> 'bash -s' < deploy/bootstrap.sh
```

Installs Docker, opens 22/80/443 only, enables unattended security upgrades,
creates `/opt/collective`. Idempotent.

If SSH refuses your key, add it in hPanel → VPS → SSH keys, or `ssh-copy-id`.

## 3. Secrets, on the server

```bash
ssh root@<vps-ip>
cd /opt/collective/deploy   # after the first deploy.sh run has copied the tree
cp .env.prod.example .env.prod && chmod 600 .env.prod
```

Fill in:

- `POSTGRES_PASSWORD` — `openssl rand -base64 32`
- `SERVICE_TOKEN` — `openssl rand -hex 32`, for scripts and cron
- provider keys for whichever agents you want live

`.env.prod` never leaves the server: it is excluded from `rsync` and from git.

## 4. Deploy

```bash
deploy/deploy.sh <vps-ip>
```

Copies the tree, builds both images, starts the stack, and waits for the API to
report healthy. Re-run it for every subsequent deploy.

Note that `NEXT_PUBLIC_*` values are compiled into the dashboard bundle, so
changing the domain, tenant or client id needs a rebuild — which `deploy.sh`
does anyway.

## 5. Verify

```bash
curl -s https://agents.openedgetechnologies.com/api/healthz
# {"status":"ok","environment":"production","auth_mode":"entra",...}

curl -s -o /dev/null -w '%{http_code}\n' https://agents.openedgetechnologies.com/api/projects
# 401 — unauthenticated, as it must be

curl -s -H "X-Service-Token: $SERVICE_TOKEN" \
  https://agents.openedgetechnologies.com/api/whoami
# {"subject":"service-token","name":"service token","kind":"service"}
```

Then open the site, sign in with a directory account, and run one `echo` turn
before enabling any paid provider.

## Operating it

```bash
cd /opt/collective/deploy
C="docker compose -f docker-compose.prod.yml --env-file .env.prod"

$C ps                      # what is running
$C logs -f backend         # follow the API
$C logs caddy | grep -i tls  # certificate issues
$C restart backend         # after an .env.prod change
$C down                    # stop everything (data survives in volumes)
```

**Backups** — everything durable is in the `pgdata` volume:

```bash
docker exec collective-db-1 pg_dump -U collective collective \
  | gzip > ~/collective-$(date +%F).sql.gz
```

Worth a cron entry once real work lives in it.

**Rollback** — the images are built from the tree on the server, so
`git checkout <good-commit>` (or re-run `deploy.sh` from a known-good local tree)
and rebuild.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Caddy loops on certificate errors | DNS not resolving to this host yet, or 80/443 blocked upstream. Check `dig` and the Hostinger firewall as well as `ufw`. |
| Dashboard shows sign-in but the button does nothing | `NEXT_PUBLIC_ENTRA_*` were empty at build time. Rebuild with `deploy.sh`. |
| `AADSTS50011` after sign-in | The redirect URI in the app registration does not match the site origin exactly. |
| API returns 401 to a freshly signed-in user | Token audience mismatch — the SPA must request `api://<client-id>/access_as_user`, not `openid` alone. |
| Backend exits at boot with "Refusing to start" | `AUTH_MODE=disabled` with `ENVIRONMENT=production`. Deliberate: it will not serve spendable endpoints unauthenticated. |
| `env file .env.prod not found` | The stack needs the real file next to the compose file; `--env-file` alone is not enough. |

## Known gaps

- **No migration tool.** `schema.sql` is applied once, on first boot of an empty
  volume. Schema changes need Alembic (or hand-applied SQL) before the second
  release.
- **Single host, no redundancy.** Fine for one operator; a restart is downtime.
- **Backups are manual** until the cron entry above exists.
- **Rate limiting is absent.** A signed-in account can spend your provider
  budget as fast as the agents will answer.
