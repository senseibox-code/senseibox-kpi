from __future__ import annotations

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from system_dashboard import app as app_module


SNAPSHOT = {
    "usage": {"processor": 12, "ram": 34, "storage": 56},
    "uptime": {"days": "01", "hours": "02", "minutes": "03", "seconds": "04"},
    "info": {
        "processor": {
            "name": "Kryo-V2",
            "coreCount": "4 Cores",
            "clockSpeed": "0.6 GHz",
            "bitDepth": "64-bit",
        },
        "machine": {
            "operatingSystem": "Debian GNU/Linux 13",
            "totalRam": "2 GiB RAM",
            "ramTypeOrOSBitDepth": "64-bit",
            "procCount": "170 Procs",
        },
        "storage": {
            "mainStorage": "/dev/mmcblk0p68",
            "total": "14 GiB Total",
            "diskCount": "3 Disks",
            "swapAmount": "870 MiB Swap",
        },
    },
}


class FakeHub:
    interval = 60
    current = SNAPSHOT

    async def start(self):
        return None

    async def stop(self):
        return None


class FakeProcessSampler:
    def sample(self):
        return {
            "processes": [
                {
                    "name": "system-dashboard",
                    "cpu": 1.2,
                    "cpuTime": "00:00:01",
                    "threads": 4,
                    "pid": 123,
                    "user": "arduino",
                }
            ]
        }


def test_api_routes_return_current_hub_snapshot(monkeypatch):
    monkeypatch.setattr(app_module, "hub", FakeHub())
    monkeypatch.setattr(app_module, "process_sampler", FakeProcessSampler())
    monkeypatch.setattr(app_module, "filesystems", lambda: {"filesystems": [{"filesystem": "rootfs"}]})
    monkeypatch.setattr(app_module, "file_usage", lambda: {"files": [{"path": "/", "size": "1G"}], "skipped": 0})

    with TestClient(app_module.create_app()) as client:
        assert client.get("/api/usage").json() == SNAPSHOT["usage"]
        assert client.get("/api/uptime").json() == SNAPSHOT["uptime"]
        assert client.get("/api/info").json() == SNAPSHOT["info"]
        assert client.get("/api/snapshot").json() == SNAPSHOT
        assert client.get("/api/processes").json() == {
            "processes": [
                {
                    "name": "system-dashboard",
                    "cpu": 1.2,
                    "cpuTime": "00:00:01",
                    "threads": 4,
                    "pid": 123,
                    "user": "arduino",
                }
            ]
        }
        assert client.get("/api/storage/filesystems").json() == {"filesystems": [{"filesystem": "rootfs"}]}
        assert client.get("/api/storage/files").json() == {"files": [{"path": "/", "size": "1G"}], "skipped": 0}


def test_websocket_sends_current_snapshot(monkeypatch):
    monkeypatch.setattr(app_module, "hub", FakeHub())

    with TestClient(app_module.create_app()) as client:
        with client.websocket_connect("/ws/metrics") as websocket:
            assert websocket.receive_json() == SNAPSHOT


def test_websocket_disconnect_does_not_attempt_second_close(monkeypatch):
    class DisconnectingWebSocket:
        close_called = False

        async def accept(self):
            return None

        async def send_text(self, _text):
            raise WebSocketDisconnect(code=1001)

        async def close(self):
            self.close_called = True

    websocket = DisconnectingWebSocket()

    monkeypatch.setattr(app_module, "hub", FakeHub())
    import anyio

    anyio.run(app_module.websocket_metrics, websocket)

    assert websocket.close_called is False
