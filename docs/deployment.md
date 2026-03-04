# Clawdbot — Deployment Guide

> **Time to deploy:** 15–30 minutes depending on option chosen.

Clawdbot runs as three long-lived services:

| Service | Purpose |
|---------|---------|
| `db` | PostgreSQL 16 — stores all messages, tasks, PVI state |
| `worker` | APScheduler — polls Gmail/Outlook, runs LLM extraction, sends reminders |
| `bot` | python-telegram-bot — handles Telegram commands and inline buttons |

A fourth ephemeral service (`migrate`) runs Alembic migrations on startup and exits.

---

## Prerequisites (all options)

Before deploying you need:

1. **Gmail credentials JSON** — follow steps in [Gmail OAuth setup](#gmail-oauth-setup)
2. **`.env` file** — all variables filled in (run `./setup.sh --wizard` locally)
3. **Docker 24+** — for local/VPS options
4. A **Telegram bot token + chat ID** — see `.env.example`
5. A **Gemini API key** — https://aistudio.google.com/app/apikey (free)

---

## Gmail OAuth Setup

Gmail OAuth tokens **cannot** be generated inside a Docker container because they require a browser. Generate the token locally, then copy it into your deployment.

```bash
# 1. On your local machine:
./setup.sh                   # installs packages
claw connect gmail           # opens browser, saves token to OS keychain

# 2. Export the token to a file:
python3 -c "
import keyring, json, pathlib
token_json = keyring.get_password('clawdbot-gmail', 'token')
path = pathlib.Path.home() / '.config/clawdbot/gmail_token.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(token_json)
print(f'Token written to {path}')
"

# You now have ~/.config/clawdbot/gmail_token.json
# This file is mounted into the worker/bot containers (see each option below).
```

> **Security:** Never commit `gmail_token.json` to git. It is already in `.gitignore`.

---

## Option A: Railway (Easiest — ~$5/mo)

Railway auto-deploys from git push, provides managed Postgres, and handles environment variables via its dashboard.

**Limitations:** Railway does not support Docker Compose natively — each service is deployed as a separate service pointing to its own Dockerfile. The `migrate` service must be run as a release command.

### Step 1: Install Railway CLI

```bash
npm i -g @railway/cli
# or: brew install railway
railway login
```

### Step 2: Create project + database

```bash
cd /path/to/LifeOps
railway init                          # creates a new Railway project
railway add --database postgresql     # provisions Postgres, injects DATABASE_URL
```

### Step 3: Set environment variables

In the Railway dashboard (https://railway.app → your project → Variables), add every key from your `.env`:

```
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_ENABLED=true
BOT_NOTIFY_MIN_PRIORITY=60
USER_TIMEZONE=Asia/Singapore
# DATABASE_URL is injected automatically by Railway
```

### Step 4: Upload Gmail token as a volume-like env var

Railway does not support volumes, so encode the token as base64 and decode it at startup.

```bash
# Local: encode the token
TOKEN_B64=$(base64 -i ~/.config/clawdbot/gmail_token.json)
# Paste $TOKEN_B64 into Railway Variables as: GMAIL_TOKEN_B64=...
```

Add a startup hook in `apps/worker/src/worker/main.py` to decode it:

```python
import os, base64, pathlib
_b64 = os.getenv("GMAIL_TOKEN_B64")
if _b64:
    p = pathlib.Path.home() / ".config/clawdbot/gmail_token.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(base64.b64decode(_b64))
```

### Step 5: Configure services

Railway reads `.railway.json` (see railway.toml in repo root). Each service is a separate Railway service:

- **migrate** — runs once on deploy (release command)
- **worker** — persistent process
- **bot** — persistent process

### Step 6: Deploy

```bash
railway up
```

Railway builds each Dockerfile, runs the release command (migrations), then starts worker + bot.

**Redeploy after code changes:**
```bash
git push origin master    # Railway auto-deploys on push if GitHub is linked
# or:
railway up
```

---

## Option B: Fly.io (~$3–5/mo)

Fly.io runs Docker containers on shared VMs. With `[processes]` in `fly.toml` you can run worker + bot as separate processes in one app, sharing the same image.

### Step 1: Install flyctl

```bash
brew install flyctl
# or: curl -L https://fly.io/install.sh | sh
fly auth login
```

### Step 2: Create app + Postgres

```bash
cd /path/to/LifeOps
fly launch --no-deploy          # creates fly.toml (or use the one in this repo)
fly postgres create \
    --name clawdbot-db \
    --region sin \
    --vm-size shared-cpu-1x \
    --volume-size 3
fly postgres attach clawdbot-db # injects DATABASE_URL as a secret
```

### Step 3: Set secrets

```bash
fly secrets set \
  GEMINI_API_KEY="..." \
  TELEGRAM_BOT_TOKEN="..." \
  TELEGRAM_CHAT_ID="..." \
  TELEGRAM_ENABLED="true" \
  BOT_NOTIFY_MIN_PRIORITY="60" \
  USER_TIMEZONE="Asia/Singapore"

# Upload Gmail token:
fly secrets set GMAIL_TOKEN_B64="$(base64 -i ~/.config/clawdbot/gmail_token.json)"
```

### Step 4: Create a volume for credentials

```bash
fly volumes create clawdbot_config --size 1 --region sin
```

The `fly.toml` mounts this at `/root/.config/clawdbot`.

### Step 5: Run migrations

```bash
fly ssh console -C "cd /app && python3 -m alembic -c infra/alembic.ini upgrade head"
# or use the [deploy] release_command in fly.toml
```

### Step 6: Deploy

```bash
fly deploy
```

**Check logs:**
```bash
fly logs
```

**Redeploy after code changes:**
```bash
fly deploy
```

---

## Option C: Self-Hosted VPS (Most Control)

Recommended for: DigitalOcean Droplet ($4/mo), Hetzner Cloud (EUR 3.79/mo), or any Linux VPS.

### Step 1: Provision VPS

Minimum specs: 1 vCPU, 1 GB RAM, 10 GB SSD. Ubuntu 22.04 LTS recommended.

```bash
# On your VPS:
apt update && apt install -y git docker.io docker-compose-plugin python3.11 python3-pip
systemctl enable docker && systemctl start docker
```

### Step 2: Clone and configure

```bash
git clone https://github.com/AryanG01/LifeOps.git
cd LifeOps
cp .env.example .env
nano .env     # fill in all credentials
```

### Step 3: Upload Gmail credentials

```bash
# From your local machine:
scp ~/.config/clawdbot/gmail_token.json user@your-vps:/root/.config/clawdbot/gmail_token.json
scp ~/.config/clawdbot/gmail_credentials.json user@your-vps:/root/.config/clawdbot/gmail_credentials.json
```

The `docker-compose.yml` mounts `/root/.config/clawdbot` into the worker and bot containers.

### Step 4: Start everything

```bash
cd infra
docker compose up -d
```

This starts: db → migrate (one-shot) → worker + bot (restart: unless-stopped).

### Step 5: Verify

```bash
docker compose ps          # all services should show "running" (except migrate = "exited 0")
docker compose logs worker  # check for "scheduler started" and first poll logs
docker compose logs bot     # check for "bot polling started"
```

### Step 6: Enable auto-restart on reboot

```bash
systemctl enable docker   # already done in Step 1
```

For an additional safety net:

```bash
# crontab -e
@reboot sleep 30 && cd /root/LifeOps/infra && docker compose up -d
```

### Step 7: (Optional) Web dashboard access via Cloudflare Tunnel

```bash
# On VPS:
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
cloudflared tunnel login
cloudflared tunnel create clawdbot
cloudflared tunnel route dns clawdbot clawdbot.yourdomain.com
cloudflared tunnel run clawdbot
```

---

## Option D: Oracle Cloud Free Tier (Best free option — $0 forever)

Oracle Cloud's **Always Free** tier includes ARM Ampere A1 VMs with **4 OCPUs + 24 GB RAM** at no cost, indefinitely. No expiry, no credits — just an account that requires a credit card at signup (never charged for Always Free resources).

### Step 1: Create Oracle Cloud account

1. Go to https://cloud.oracle.com/free and sign up
2. Choose your **home region** closest to you (e.g. `ap-singapore-1`) — this cannot be changed later
3. Verify your credit card (not charged for Always Free)

### Step 2: Provision ARM VM

In the Oracle Cloud console:

1. **Compute → Instances → Create Instance**
2. Name: `clawdbot`
3. Image: **Ubuntu 22.04** (Canonical Ubuntu)
4. Shape: **VM.Standard.A1.Flex** (Ampere — Always Free)
   - OCPUs: `4`, Memory: `24 GB` (use the full free allocation)
5. Networking: Create new VCN (defaults are fine)
6. SSH keys: upload your `~/.ssh/id_rsa.pub` (or generate a new key pair and download it)
7. Click **Create**

Wait ~2 minutes for the instance to reach **RUNNING** state. Note the **Public IP**.

### Step 3: Open ports in the firewall

Oracle Cloud has two firewalls: the VCN Security List and the OS-level iptables.

**VCN Security List** (Oracle console → Networking → Virtual Cloud Networks → your VCN → Security Lists → Default):

Add ingress rules:
| Source | Protocol | Port | Purpose |
|--------|----------|------|---------|
| 0.0.0.0/0 | TCP | 22 | SSH |
| 0.0.0.0/0 | TCP | 8000 | Web dashboard (optional) |

**OS iptables** (on the VM — Oracle Ubuntu blocks ports at the OS level by default):

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

### Step 4: SSH in and install dependencies

```bash
ssh ubuntu@<your-public-ip>

# Update and install Docker
sudo apt update && sudo apt install -y git docker.io docker-compose-plugin python3.11 python3-pip
sudo systemctl enable docker && sudo systemctl start docker
sudo usermod -aG docker ubuntu   # allow docker without sudo
newgrp docker                     # apply group change immediately
```

### Step 5: Clone and configure

```bash
git clone https://github.com/AryanG01/LifeOps.git
cd LifeOps
cp .env.example .env
nano .env    # fill in: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED=true
             # DATABASE_URL default (localhost:5432) works because DB runs in Docker on the same VM
```

### Step 6: Upload Gmail credentials

From your **local machine**:

```bash
# Create the config dir on the VM first
ssh ubuntu@<your-public-ip> "mkdir -p ~/.config/clawdbot"

# Copy your locally-generated Gmail token and credentials
scp ~/.config/clawdbot/gmail_token.json     ubuntu@<your-public-ip>:~/.config/clawdbot/
scp ~/.config/clawdbot/gmail_credentials.json ubuntu@<your-public-ip>:~/.config/clawdbot/
```

> If you haven't generated these yet, run `./setup.sh && claw connect gmail` locally first, then copy them up.

### Step 7: Start everything

```bash
# On the VM:
cd ~/LifeOps/infra
docker compose up -d
```

This starts: `db` → `migrate` (runs Alembic, exits 0) → `worker` + `bot` + `api` (all restart: unless-stopped).

### Step 8: Verify

```bash
docker compose ps          # migrate = Exited(0), all others = running
docker compose logs -f worker  # look for "scheduler started"
docker compose logs -f bot     # look for "bot polling started"
```

Send `/status` to your Telegram bot — it should respond within seconds.

### Step 9: Enable auto-restart on reboot

Docker's `restart: unless-stopped` handles container restarts. To start Docker Compose on VM reboot:

```bash
# crontab -e
@reboot sleep 30 && cd /home/ubuntu/LifeOps/infra && docker compose up -d
```

### Step 10: (Optional) Web dashboard via Cloudflare Tunnel

Rather than exposing port 8000 directly, a Cloudflare Tunnel gives you HTTPS for free with no port forwarding.

```bash
# On the VM:
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
cloudflared tunnel login
cloudflared tunnel create clawdbot
cloudflared tunnel route dns clawdbot clawdbot.yourdomain.com
# Start as a service:
cloudflared service install
sudo systemctl start cloudflared
```

Then set `DASHBOARD_API_KEY` in `.env` to protect the dashboard.

### Updating Clawdbot on Oracle Cloud

```bash
ssh ubuntu@<your-public-ip>
cd ~/LifeOps
git pull origin master
cd infra
docker compose build worker bot api
docker compose up -d --no-deps worker bot api
```

---

## Option E: Google Cloud e2-micro + Neon.tech (Free forever, no Docker needed)

**Why this combo:** Google Cloud's Always Free tier includes one **e2-micro VM** (1 shared vCPU, 614 MB RAM) that never expires. Neon.tech provides **serverless Postgres** on a free plan (500 MB storage). Running the worker + bot as systemd services (no Docker) keeps RAM usage under 400 MB — within the free limit.

**Cost: $0/month, no trial expiry.**

---

### Part 1: Neon.tech — Free Postgres

1. Sign up at https://neon.tech (GitHub login works)
2. **New Project** → Name: `clawdbot`, Region: `AWS us-east-1` (closest to GCP us-central1)
3. On the dashboard, click **Connection string** → copy the full URL:
   ```
   postgresql://clawdbot:<password>@ep-xxx.us-east-1.aws.neon.tech/clawdbot?sslmode=require
   ```
4. Save this — it goes into `DATABASE_URL` in your `.env`

---

### Part 2: Google Cloud — Free e2-micro VM

**Sign up:** https://cloud.google.com/free (credit card required, never charged for Always Free resources)

#### Create the VM

1. Go to **Compute Engine → VM Instances → Create Instance**
2. Configure:
   - **Name:** `clawdbot`
   - **Region:** `us-central1` (or `us-east1`, `us-west1`) — **required for Always Free**
   - **Machine type:** `e2-micro` (select from General Purpose → E2)
   - **Boot disk:** Ubuntu 22.04 LTS, **30 GB Standard disk** (also Always Free)
   - **Firewall:** check "Allow HTTP traffic" and "Allow HTTPS traffic"
3. Under **Security → SSH Keys**, add your public key (`cat ~/.ssh/id_rsa.pub`)
4. Click **Create** — wait ~1 minute, note the **External IP**

#### Open port 8000 (optional, for web dashboard)

In GCP Console → **VPC Network → Firewall → Create Firewall Rule**:
- Name: `allow-clawdbot-api`
- Targets: All instances in the network
- Source IP ranges: `0.0.0.0/0`
- Protocols and ports: TCP `8000`

---

### Part 3: VM Setup

```bash
ssh your-username@<external-ip>

# Install Python and pip
sudo apt update && sudo apt install -y git python3.11 python3.11-venv python3-pip

# Clone the repo
git clone https://github.com/AryanG01/LifeOps.git
cd LifeOps

# Create a virtualenv (keeps packages isolated)
python3.11 -m venv .venv
source .venv/bin/activate

# Install all packages
pip install -e packages/core -e packages/connectors -e packages/cli -e apps/worker -e apps/bot -e apps/api
```

---

### Part 4: Configure .env

```bash
cp .env.example .env
nano .env
```

Key values to set:

```env
# Use Neon connection string (NOT localhost)
DATABASE_URL=postgresql://clawdbot:<password>@ep-xxx.us-east-1.aws.neon.tech/clawdbot?sslmode=require

GEMINI_API_KEY=your-key
TELEGRAM_BOT_TOKEN=your-token
TELEGRAM_CHAT_ID=your-chat-id
TELEGRAM_ENABLED=true
USER_TIMEZONE=Asia/Singapore
USER_DISPLAY_NAME=Aryan
USER_EMAIL=your@email.com
```

---

### Part 5: Upload Gmail credentials

From your **local machine**:

```bash
ssh your-username@<external-ip> "mkdir -p ~/.config/clawdbot"
scp ~/.config/clawdbot/gmail_token.json      your-username@<external-ip>:~/.config/clawdbot/
scp ~/.config/clawdbot/gmail_credentials.json your-username@<external-ip>:~/.config/clawdbot/
```

---

### Part 6: Run migrations + init

```bash
# On the VM (inside LifeOps dir, venv active):
cd infra
python3 -m alembic upgrade head
cd ..
python3 -m cli.main init
```

---

### Part 7: Create systemd services

Running as systemd services means they start on boot and restart on crash automatically.

```bash
# Get the full path to your virtualenv python
which python3   # should show /home/<user>/LifeOps/.venv/bin/python3
```

Create the worker service:

```bash
sudo tee /etc/systemd/system/clawdbot-worker.service > /dev/null <<EOF
[Unit]
Description=Clawdbot Worker
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=/home/$(whoami)/LifeOps
ExecStart=/home/$(whoami)/LifeOps/.venv/bin/python3 -m worker.main
Restart=always
RestartSec=10
EnvironmentFile=/home/$(whoami)/LifeOps/.env

[Install]
WantedBy=multi-user.target
EOF
```

Create the bot service:

```bash
sudo tee /etc/systemd/system/clawdbot-bot.service > /dev/null <<EOF
[Unit]
Description=Clawdbot Telegram Bot
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=/home/$(whoami)/LifeOps
ExecStart=/home/$(whoami)/LifeOps/.venv/bin/python3 -m bot
Restart=always
RestartSec=10
EnvironmentFile=/home/$(whoami)/LifeOps/.env

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start both:

```bash
sudo systemctl daemon-reload
sudo systemctl enable clawdbot-worker clawdbot-bot
sudo systemctl start clawdbot-worker clawdbot-bot
```

---

### Part 8: Verify

```bash
sudo systemctl status clawdbot-worker   # should show "active (running)"
sudo systemctl status clawdbot-bot      # should show "active (running)"

# Live logs:
sudo journalctl -u clawdbot-worker -f
sudo journalctl -u clawdbot-bot -f
```

Send `/status` to your Telegram bot — it should respond within a few seconds.

---

### Updating Clawdbot on GCP

```bash
ssh your-username@<external-ip>
cd ~/LifeOps
git pull origin master
source .venv/bin/activate
pip install -e packages/core -e packages/connectors -e packages/cli -e apps/worker -e apps/bot -e apps/api
# Run migrations if schema changed:
cd infra && python3 -m alembic upgrade head && cd ..
# Restart services:
sudo systemctl restart clawdbot-worker clawdbot-bot
```

---

## Updating Clawdbot

### Self-hosted VPS

```bash
cd /root/LifeOps
git pull origin master
cd infra
docker compose build worker bot
docker compose up -d --no-deps worker bot
```

### New migrations

```bash
cd infra
docker compose run --rm migrate
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `worker` exits immediately | Missing env var | `docker compose logs worker` — look for `ValidationError` or `KeyError` |
| Gmail not polling | Token expired | Re-run `claw connect gmail` locally, re-upload token |
| Telegram not sending | `TELEGRAM_ENABLED=false` | Set `TELEGRAM_ENABLED=true` in `.env` / secrets |
| `migrate` exits non-zero | DB not ready | Check `docker compose logs db` — wait for "ready to accept connections" |
| `AADSTS50059` (Outlook) | Wrong tenant | Set `OUTLOOK_TENANT=organizations` in `.env` |
| LLM extraction failing | API key invalid or quota exceeded | Check `GEMINI_API_KEY`, visit https://aistudio.google.com |

---

## Cost Summary

| Platform | DB | Compute | Est. monthly |
|----------|----|---------|-------------|
| **Oracle Cloud Free Tier** | Docker on VM (free) | 4 OCPU / 24 GB ARM VM (free forever) | **$0** |
| Railway | Managed Postgres $5 | Worker+Bot ~$0–2 | ~$5–7 |
| Fly.io | Postgres shared $0–3 | 2 processes shared VM ~$2 | ~$3–5 |
| DigitalOcean Droplet | Docker on VPS | $4/mo Droplet | ~$4 |
| Hetzner Cloud | Docker on VPS | CX11 EUR 3.79/mo | ~$4 |
| Local Mac | Existing machine | Free | $0 |
