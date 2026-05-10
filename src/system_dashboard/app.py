from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager
from importlib import metadata
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from .metrics import MetricsSampler, ProcessSampler, file_usage, filesystems


ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
VERSION_FILE = ROOT / "VERSION"


def app_version() -> str:
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        try:
            return metadata.version("system-dashboard")
        except metadata.PackageNotFoundError:
            return "0.0.0"
    return version or "0.0.0"


class MetricsHub:
    def __init__(self, interval: int = 3) -> None:
        self.interval = interval
        self.sampler = MetricsSampler()
        self.current = self.sampler.snapshot()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _refresh_loop(self) -> None:
        while True:
            self.current = self.sampler.snapshot()
            await asyncio.sleep(self.interval)


hub = MetricsHub()
process_sampler = ProcessSampler()


@asynccontextmanager
async def lifespan(_app: Starlette):
    await hub.start()
    try:
        yield
    finally:
        await hub.stop()


async def homepage(_request):
    return FileResponse(STATIC / "index.html")


async def api_usage(_request):
    return JSONResponse(hub.current["usage"])


async def api_uptime(_request):
    return JSONResponse(hub.current["uptime"])


async def api_info(_request):
    return JSONResponse(hub.current["info"])


async def api_snapshot(_request):
    return JSONResponse(hub.current)


async def api_version(_request):
    return JSONResponse({"version": app_version()})


async def api_processes(_request):
    return JSONResponse(process_sampler.sample())


async def api_storage_filesystems(_request):
    return JSONResponse(filesystems())


async def api_storage_files(_request):
    return JSONResponse(await asyncio.to_thread(file_usage))


async def websocket_metrics(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(json.dumps(hub.current))
            await asyncio.sleep(hub.interval)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    except Exception:
        try:
            await websocket.close()
        except RuntimeError:
            pass


def create_app() -> Starlette:
    return Starlette(
        debug=False,
        lifespan=lifespan,
        routes=[
            Route("/", homepage),
            Route("/api/usage", api_usage),
            Route("/api/uptime", api_uptime),
            Route("/api/info", api_info),
            Route("/api/snapshot", api_snapshot),
            Route("/api/version", api_version),
            Route("/api/processes", api_processes),
            Route("/api/storage/filesystems", api_storage_filesystems),
            Route("/api/storage/files", api_storage_files),
            WebSocketRoute("/ws/metrics", websocket_metrics),
            Mount("/static", StaticFiles(directory=STATIC), name="static"),
        ],
    )


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Linux system dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "system_dashboard.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        access_log=False,
    )


if __name__ == "__main__":
    main()
