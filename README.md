# Senseibox KPI

A small Linux-only system telemetry dashboard designed for lightweight server boards.
It exposes simple JSON APIs and streams live updates to a clean HTML/CSS/JS dashboard.

## Features

- CPU, memory, storage, process, swap, and uptime telemetry
- REST APIs for easy scripts and tests
- WebSocket stream for live dashboard updates every 3 seconds
- Static frontend with no build step
- systemd service template for boot startup
- Linux `/proc`, `/sys`, and core utilities only; no heavyweight metrics agent

## API

```text
GET /api/usage
GET /api/uptime
GET /api/info
GET /api/snapshot
GET /api/processes
GET /api/storage/filesystems
GET /api/storage/files
WS  /ws/metrics
```

Example `/api/usage`:

```json
{"processor":0,"ram":13,"storage":69}
```

Example `/api/uptime`:

```json
{"days":"00","hours":"00","minutes":"31","seconds":"23"}
```

## Run Locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
system-dashboard --host 0.0.0.0 --port 8080
```

Then open `http://localhost:8080`.

## Install As A Service

The repo includes a systemd service file at `systemd/senseibox-kpi.service`.
It expects the app to live at `/opt/senseibox/senseibox-kpi`, run as the
`senseibox` service user, and listen on port `8001`.

On a fresh Linux system, create the service user and install the app under the
Senseibox namespace:

```bash
sudo useradd --system --home /opt/senseibox --shell /usr/sbin/nologin senseibox
sudo mkdir -p /opt/senseibox/senseibox-kpi
sudo chown -R senseibox:senseibox /opt/senseibox

cd /opt/senseibox/senseibox-kpi
sudo -u senseibox python3 -m venv .venv
sudo -u senseibox .venv/bin/python -m pip install --upgrade pip
sudo -u senseibox .venv/bin/python -m pip install -e .
```

Then install and start the service:

```bash
sudo cp systemd/senseibox-kpi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now senseibox-kpi
```

Check it:

```bash
systemctl status senseibox-kpi --no-pager
journalctl -u senseibox-kpi -f
curl http://127.0.0.1:8001/api/snapshot
```

Open `http://<server-ip>:8001/`.

If you install to a different path, user, or port, update
`systemd/senseibox-kpi.service` before copying it into `/etc/systemd/system/`.

## Notes

This project targets Linux servers. macOS and Windows are intentionally out of scope.
