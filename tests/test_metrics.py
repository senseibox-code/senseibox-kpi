from __future__ import annotations

from types import SimpleNamespace

from system_dashboard import metrics


def set_proc(monkeypatch, tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    monkeypatch.setattr(metrics, "PROC", proc)
    return proc


def test_uptime_formats_proc_uptime(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    (proc / "uptime").write_text("93784.10 120000.00\n")

    assert metrics.uptime() == {
        "days": "01",
        "hours": "02",
        "minutes": "03",
        "seconds": "04",
    }


def test_usage_percentages_reads_memory_and_disk(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    (proc / "meminfo").write_text(
        "\n".join(
            [
                "MemTotal:       1000 kB",
                "MemAvailable:    250 kB",
            ]
        )
    )
    monkeypatch.setattr(metrics.shutil, "disk_usage", lambda _path: SimpleNamespace(total=200, used=50))

    assert metrics.usage_percentages(37) == {
        "processor": 37,
        "ram": 75,
        "storage": 25,
    }


def test_usage_percentages_clamps_cpu(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    (proc / "meminfo").write_text("")
    monkeypatch.setattr(metrics.shutil, "disk_usage", lambda _path: SimpleNamespace(total=0, used=0))

    assert metrics.usage_percentages(140)["processor"] == 100
    assert metrics.usage_percentages(-12)["processor"] == 0


def test_system_info_uses_linux_sources(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    sys_block = tmp_path / "sys" / "block"
    sys_block.mkdir(parents=True)
    (sys_block / "mmcblk0").mkdir()
    (sys_block / "loop0").mkdir()
    monkeypatch.setattr(metrics, "SYS_BLOCK", sys_block)

    (proc / "meminfo").write_text(
        "\n".join(
            [
                "MemTotal:       2097152 kB",
                "MemAvailable:  1048576 kB",
                "SwapTotal:       890880 kB",
            ]
        )
    )
    (proc / "cpuinfo").write_text(
        "\n".join(
            [
                "Hardware\t: Kryo-V2",
                "cpu MHz\t\t: 600.000",
            ]
        )
    )
    (proc / "1").mkdir()
    (proc / "44").mkdir()
    (proc / "self").mkdir()

    monkeypatch.setattr(metrics, "_read_key_value_file", lambda _path: {"PRETTY_NAME": "Debian GNU/Linux 13"})
    monkeypatch.setattr(metrics, "_root_device", lambda: "/dev/mmcblk0p68")
    monkeypatch.setattr(metrics.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(metrics.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(metrics.shutil, "disk_usage", lambda _path: SimpleNamespace(total=14 * 1024**3, used=4))

    assert metrics.system_info() == {
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
            "procCount": "2 Procs",
        },
        "storage": {
            "mainStorage": "/dev/mmcblk0p68",
            "total": "14 GiB Total",
            "diskCount": "1 Disks",
            "swapAmount": "870 MiB Swap",
        },
    }


def test_read_cpu_sample_parses_proc_stat(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    (proc / "stat").write_text("cpu 100 0 50 850 10 0 0 0 0 0\n")

    assert metrics.read_cpu_sample() == metrics.CpuSample(idle=860, total=1010)


def test_metrics_sampler_computes_cpu_delta(monkeypatch):
    samples = [
        metrics.CpuSample(idle=900, total=1000),
        metrics.CpuSample(idle=950, total=1100),
    ]
    monkeypatch.setattr(metrics, "read_cpu_sample", lambda: samples.pop(0))

    sampler = metrics.MetricsSampler()

    assert sampler.cpu_percent() == 50


def write_process(proc, pid, name, user_ticks, system_ticks, threads, uid=1000):
    pid_dir = proc / str(pid)
    pid_dir.mkdir()
    fields = [
        "S",
        "1",
        "1",
        "1",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        str(user_ticks),
        str(system_ticks),
        "0",
        "0",
        "20",
        "0",
        str(threads),
        "0",
        "0",
    ]
    (pid_dir / "stat").write_text(f"{pid} ({name}) {' '.join(fields)}\n")
    (pid_dir / "comm").write_text(f"{name}\n")
    (pid_dir / "status").write_text(f"Name:\t{name}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    return pid_dir


def test_process_sampler_reads_proc_without_shelling_out(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    (proc / "stat").write_text("cpu 100 0 0 900 0 0 0 0 0 0\n")
    write_process(proc, 722, "Spotlight", 100, 20, 19)
    write_process(proc, 0, "kernel_task", 80, 10, 495, uid=0)
    monkeypatch.setattr(metrics.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(metrics, "_clock_ticks", lambda: 100)
    monkeypatch.setattr(metrics.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name={0: "root", 1000: "appuser"}[uid]))

    sampler = metrics.ProcessSampler()

    (proc / "stat").write_text("cpu 200 0 0 1000 0 0 0 0 0 0\n")
    (proc / "722" / "stat").write_text(
        "722 (Spotlight) S 1 1 1 0 0 0 0 0 0 0 110 30 0 0 20 0 19 0 0\n"
    )
    (proc / "0" / "stat").write_text(
        "0 (kernel_task) S 1 1 1 0 0 0 0 0 0 0 81 10 0 0 20 0 495 0 0\n"
    )

    assert sampler.sample(limit=10) == {
        "processes": [
            {
                "name": "Spotlight",
                "cpu": 40.0,
                "cpuTime": "0:00:01",
                "threads": 19,
                "pid": 722,
                "user": "appuser",
            },
            {
                "name": "kernel_task",
                "cpu": 2.0,
                "cpuTime": "0:00:00",
                "threads": 495,
                "pid": 0,
                "user": "root",
            },
        ]
    }


def test_filesystems_reads_mountinfo(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    (proc / "self").mkdir()
    (proc / "self" / "mountinfo").write_text(
        "\n".join(
            [
                "22 1 179:68 / / rw,relatime - ext4 /dev/mmcblk0p68 rw",
                "23 22 0:22 / /run rw,nosuid,nodev - tmpfs tmpfs rw",
                "24 22 0:23 / /run/credentials rw,nosuid,nodev - tmpfs tmpfs rw",
            ]
        )
    )

    def fake_disk_usage(path):
        values = {
            "/": SimpleNamespace(total=10 * 1024**3, used=5 * 1024**3, free=5 * 1024**3),
            "/run": SimpleNamespace(total=100 * 1024**2, used=2 * 1024**2, free=98 * 1024**2),
            "/run/credentials": SimpleNamespace(total=1024**2, used=0, free=1024**2),
        }
        return values[path]

    monkeypatch.setattr(metrics.shutil, "disk_usage", fake_disk_usage)

    assert metrics.filesystems() == {
        "filesystems": [
            {
                "filesystem": "/dev/mmcblk0p68",
                "size": "10G",
                "used": "5G",
                "available": "5G",
                "percent": 50,
                "mountedOn": "/",
            },
            {
                "filesystem": "tmpfs",
                "size": "100M",
                "used": "2M",
                "available": "98M",
                "percent": 2,
                "mountedOn": "/run",
            },
        ]
    }


def test_filesystems_collapses_duplicate_backing_filesystems(monkeypatch, tmp_path):
    proc = set_proc(monkeypatch, tmp_path)
    (proc / "self").mkdir()
    (proc / "self" / "mountinfo").write_text(
        "\n".join(
            [
                "22 1 254:3 / / rw,relatime - ext4 /dev/vda3 rw",
                "23 22 254:3 /boot /boot rw,relatime - ext4 /dev/vda3 rw",
                "24 22 254:3 /etc /etc rw,relatime - ext4 /dev/vda3 rw",
                "25 22 0:22 / /run rw,nosuid,nodev - tmpfs tmpfs rw",
                "26 22 0:22 /credentials /run/credentials rw,nosuid,nodev - tmpfs tmpfs rw",
            ]
        )
    )

    def fake_disk_usage(path):
        values = {
            "/": SimpleNamespace(total=18 * 1024**3, used=7 * 1024**3, free=11 * 1024**3),
            "/boot": SimpleNamespace(total=18 * 1024**3, used=7 * 1024**3 + 64, free=11 * 1024**3 - 64),
            "/etc": SimpleNamespace(total=18 * 1024**3, used=7 * 1024**3 + 128, free=11 * 1024**3 - 128),
            "/run": SimpleNamespace(total=197 * 1024**2, used=800 * 1024, free=196 * 1024**2),
            "/run/credentials": SimpleNamespace(total=197 * 1024**2, used=800 * 1024 + 64, free=196 * 1024**2 - 64),
        }
        return values[path]

    monkeypatch.setattr(metrics.shutil, "disk_usage", fake_disk_usage)

    assert metrics.filesystems() == {
        "filesystems": [
            {
                "filesystem": "/dev/vda3",
                "size": "18G",
                "used": "7G",
                "available": "11G",
                "percent": 39,
                "mountedOn": "/",
            },
            {
                "filesystem": "tmpfs",
                "size": "197M",
                "used": "800K",
                "available": "196M",
                "percent": 0,
                "mountedOn": "/run",
            },
        ]
    }


def test_file_usage_stays_on_root_filesystem(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    usr = root / "usr"
    usr.mkdir()
    lib = usr / "lib"
    lib.mkdir()
    (root / "tiny.log").write_bytes(b"x" * 10)
    (usr / "tool").write_bytes(b"x" * 20)
    (lib / "library").write_bytes(b"x" * 30)

    assert metrics.file_usage(str(root), limit=3) == {
        "files": [
            {"size": "60B", "bytes": 60, "path": str(root)},
            {"size": "50B", "bytes": 50, "path": str(usr)},
            {"size": "30B", "bytes": 30, "path": str(lib)},
        ],
        "skipped": 0,
    }
