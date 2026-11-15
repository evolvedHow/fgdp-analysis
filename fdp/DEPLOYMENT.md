# FDP Deployment Guide

Target architecture: **Modal (compute + volume) + Cloudflare (edge proxy)**.

The local homelab setup (systemd service + local data files) remains the default
for daily development. Modal + Cloudflare are for remote access or production
use. There is **no PostgreSQL/Supabase dependency** in any environment.

---

## 1. Local homelab (today)

Already running:

```bash
# MCP server on 127.0.0.1:8001
systemctl --user status fdp-mcp

# Data files live in the fdp repo
cd ~/codebox/fgdp/fdp
ls data/repos/main/
```

The service reads directly from `data/repos/main/` (and any active workspace).
No database is required.

---

## 2. Cloudflare Tunnel (test remote access from the homelab)

Use this to expose the local `fdp-mcp` systemd service on a public subdomain
before moving to Modal.

```bash
# 1. Install cloudflared
curl -L --output /tmp/cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i /tmp/cloudflared.deb

# 2. Authenticate and create tunnel
cloudflared tunnel login
cloudflared tunnel create fdp
cloudflared tunnel route dns fdp fdp.yourdomain.com

# 3. Copy the generated config
sudo mkdir -p /etc/cloudflared
sudo cp cloudflare-tunnel/config.yml /etc/cloudflared/config.yml
# Edit /etc/cloudflared/config.yml and replace <TUNNEL_ID> with the UUID shown
# by `cloudflared tunnel list`.

# 4. Install service
sudo cp cloudflare-tunnel/cloudflared-fdp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared-fdp
```

Test from outside:

```bash
curl https://fdp.yourdomain.com/mcp \
  -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

> Note: Cloudflare Tunnel points to a **local origin**. When you move the app to
> Modal, switch to a Cloudflare Worker reverse proxy or Cloudflare Access on a
> CNAME to the Modal origin instead.

---

## 3. Secrets management (worker-env vault)

Store real values in `~/docker/stack/secrets/fdp.secrets.csv`, then copy it to
`~/codebox/worker-env/worker/secrets/fdp.secrets.csv` before deploying the vault.

```bash
cp ~/docker/stack/secrets/fdp.secrets.csv \
   ~/codebox/worker-env/worker/secrets/fdp.secrets.csv
cd ~/codebox/worker-env
npm run deploy
```

Retrieve in scripts or CI:

```bash
vault get fdp/MODAL_TOKEN_ID
vault get fdp/FDPAPI_SECRET
```

---

## 4. Modal (cloud target)

### 4.1 Secrets

Add these GitHub repository secrets (`Settings > Secrets and variables > Actions`):

| Secret | Description |
|---|---|
| `MODAL_TOKEN_ID` | Modal token ID |
| `MODAL_TOKEN_SECRET` | Modal token secret |
| `FDPAPI_SECRET` | Token protecting `POST /api/v1/query` |

Also create a Modal secret named `fdp-api` with the same env vars:

```bash
modal secret create fdp-api \
  FDPAPI_SECRET="..."
```

### 4.2 Upload data to Modal Volume

```bash
cd ~/codebox/fgdp/fdp
uv run --extra modal modal volume put fdp-data data /fdp-data --force
```

### 4.3 Deploy

```bash
uv run --extra modal modal deploy modal_app.py
```

Or push to `main` and let the GitHub Action `.github/workflows/deploy-modal.yml`
handle it.

---

## 5. Cloudflare in front of Modal

Once Modal is deployed you get an origin like
`https://vgana--fdp-api-fastapi-app.modal.run`. Do **not** give that URL to
clients. Put Cloudflare in front:

### Option A: Cloudflare Worker reverse proxy (recommended)

Deploy the worker in `cloudflare-proxy/`:

```bash
cd cloudflare-proxy
npm install
npx wrangler secret put PROXY_TOKEN
npx wrangler deploy
```

Set the `MODAL_URL` variable in `wrangler.toml` after the first Modal deploy.

Clients then call `https://fdp.yourdomain.com/mcp` with:

```
Authorization: Bearer <PROXY_TOKEN>
```

### Option B: Cloudflare Access + CNAME

1. Add a CNAME record `fdp.yourdomain.com` → `vgana--fdp-api-fastapi-app.modal.run`
2. Enable the orange cloud (proxy)
3. Create a Cloudflare Access application for `fdp.yourdomain.com`
4. Issue service tokens for API clients

---

## Files added for this architecture

| File | Purpose |
|---|---|
| `modal_app.py` | Modal ASGI deployment |
| `.github/workflows/deploy-modal.yml` | Deploy to Modal on push |
| `cloudflare-proxy/` | Worker reverse proxy for Modal |
| `cloudflare-tunnel/` | Tunnel config for local homelab testing |
| `DEPLOYMENT.md` | This guide |
