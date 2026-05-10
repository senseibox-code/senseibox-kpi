# Contributing

Thanks for helping improve System Dashboard.

## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
system-dashboard --reload
```

The app is intentionally small:

- `src/system_dashboard/metrics.py` reads Linux telemetry.
- `src/system_dashboard/app.py` exposes the API and WebSocket routes.
- `static/` contains the dashboard UI with no frontend build step.

## Local Checks

```bash
python -m compileall src
pytest
node --check static/dashboard.js
```

When changing metrics, test on Linux. macOS can import the project, but `/proc`
values will be placeholders because Linux is the target runtime.

## API Compatibility

Keep these routes stable unless a major version changes them:

- `/api/usage`
- `/api/uptime`
- `/api/info`
- `/ws/metrics`
