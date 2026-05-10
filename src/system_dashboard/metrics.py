from __future__ import annotations

import os
import platform
import pwd
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROC = Path("/proc")
SYS_BLOCK = Path("/sys/block")


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return default


def _read_key_value_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in _read_text(path).splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in _read_text(PROC / "meminfo").splitlines():
        match = re.match(r"^(\w+):\s+(\d+)", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    return values


def _format_bytes(value: int, suffix: str = "") -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(max(value, 0))
    unit_index = 0
    while amount >= 1024 and unit_index < len(units) - 1:
        amount /= 1024
        unit_index += 1
    rendered = f"{amount:.0f}" if amount >= 10 or amount.is_integer() else f"{amount:.1f}"
    return f"{rendered} {units[unit_index]}{suffix}"


def _format_df_bytes(value: int) -> str:
    units = ["B", "K", "M", "G", "T"]
    amount = float(max(value, 0))
    unit_index = 0
    while amount >= 1024 and unit_index < len(units) - 1:
        amount /= 1024
        unit_index += 1
    rendered = f"{amount:.0f}" if amount >= 10 or amount.is_integer() else f"{amount:.1f}"
    return f"{rendered}{units[unit_index]}"


def _decode_mount_field(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def _run(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _root_device() -> str:
    source = _run(["findmnt", "-n", "-o", "SOURCE", "/"])
    if source:
        return source
    return "rootfs"


def _disk_count() -> int:
    if not SYS_BLOCK.exists():
        return 0
    ignored_prefixes = ("loop", "ram", "zram")
    count = 0
    for device in SYS_BLOCK.iterdir():
        name = device.name
        if name.startswith(ignored_prefixes):
            continue
        if (device / "device").exists() or name.startswith(("mmcblk", "nvme", "sd", "vd", "xvd")):
            count += 1
    return count


def _process_count() -> int:
    try:
        return sum(1 for child in PROC.iterdir() if child.name.isdigit())
    except OSError:
        return 0


def _cpu_name() -> str:
    cpuinfo = _read_text(PROC / "cpuinfo")
    preferred_keys = ("Hardware", "model name", "Processor", "cpu model", "cpu")
    for key in preferred_keys:
        match = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return platform.processor() or "Linux CPU"


def _cpu_clock() -> str:
    cpuinfo = _read_text(PROC / "cpuinfo")
    match = re.search(r"^cpu MHz\s*:\s*([\d.]+)$", cpuinfo, re.MULTILINE)
    if match:
        ghz = float(match.group(1)) / 1000
        return f"{ghz:.1f} GHz"

    for path in (
        Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"),
        Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq"),
    ):
        raw = _read_text(path).strip()
        if raw.isdigit():
            return f"{int(raw) / 1_000_000:.1f} GHz"

    return "n/a"


def _bit_depth() -> str:
    machine = platform.machine().lower()
    if "64" in machine or machine in {"aarch64", "arm64"}:
        return "64-bit"
    if "86" in machine or machine.startswith("armv7"):
        return "32-bit"
    return platform.architecture()[0] or "n/a"


def usage_percentages(cpu_percent: int) -> dict[str, int]:
    mem = _meminfo()
    mem_total = mem.get("MemTotal", 0)
    mem_available = mem.get("MemAvailable", 0)
    ram_percent = round(((mem_total - mem_available) / mem_total) * 100) if mem_total else 0

    disk = shutil.disk_usage("/")
    storage_percent = round((disk.used / disk.total) * 100) if disk.total else 0

    return {
        "processor": max(0, min(100, cpu_percent)),
        "ram": max(0, min(100, ram_percent)),
        "storage": max(0, min(100, storage_percent)),
    }


def uptime() -> dict[str, str]:
    raw = _read_text(PROC / "uptime", "0").split()[0]
    total_seconds = int(float(raw))
    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return {
        "days": f"{days:02d}",
        "hours": f"{hours:02d}",
        "minutes": f"{minutes:02d}",
        "seconds": f"{seconds:02d}",
    }


def system_info() -> dict[str, dict[str, str]]:
    mem = _meminfo()
    os_release = _read_key_value_file(Path("/etc/os-release"))
    disk = shutil.disk_usage("/")
    swap_total = mem.get("SwapTotal", 0)

    return {
        "processor": {
            "name": _cpu_name(),
            "coreCount": f"{os.cpu_count() or 0} Cores",
            "clockSpeed": _cpu_clock(),
            "bitDepth": _bit_depth(),
        },
        "machine": {
            "operatingSystem": os_release.get("PRETTY_NAME", platform.platform()),
            "totalRam": _format_bytes(mem.get("MemTotal", 0), " RAM"),
            "ramTypeOrOSBitDepth": _bit_depth(),
            "procCount": f"{_process_count()} Procs",
        },
        "storage": {
            "mainStorage": _root_device(),
            "total": _format_bytes(disk.total, " Total"),
            "diskCount": f"{_disk_count()} Disks",
            "swapAmount": _format_bytes(swap_total, " Swap"),
        },
    }


def filesystems() -> dict[str, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    seen_mounts: set[str] = set()
    minimum_size = 1024**2
    for line in _read_text(PROC / "self" / "mountinfo").splitlines():
        parts = line.split()
        if len(parts) < 10 or "-" not in parts:
            continue
        separator = parts.index("-")
        mount_point = _decode_mount_field(parts[4])
        if mount_point in seen_mounts:
            continue
        seen_mounts.add(mount_point)
        filesystem = _decode_mount_field(parts[separator + 2])
        try:
            usage = shutil.disk_usage(mount_point)
        except OSError:
            continue
        if usage.total <= minimum_size:
            continue
        percent = round((usage.used / usage.total) * 100) if usage.total else 0
        rows.append(
            {
                "filesystem": filesystem,
                "size": _format_df_bytes(usage.total),
                "used": _format_df_bytes(usage.used),
                "available": _format_df_bytes(usage.free),
                "percent": max(0, min(100, percent)),
                "mountedOn": mount_point,
            }
        )
    rows.sort(key=lambda row: (row["mountedOn"] != "/", str(row["mountedOn"])))
    return {"filesystems": rows}


def file_usage(root: str = "/", limit: int = 40) -> dict[str, object]:
    root_path = Path(root)
    try:
        root_device = root_path.stat().st_dev
    except OSError:
        return {"files": [], "skipped": 1}

    direct_sizes: dict[str, int] = {}
    parents: dict[str, str | None] = {str(root_path): None}
    skipped = 0

    def on_error(_error: OSError) -> None:
        nonlocal skipped
        skipped += 1

    for current, dirs, files in os.walk(root_path, topdown=True, onerror=on_error, followlinks=False):
        current_path = Path(current)
        current_key = str(current_path)
        direct_sizes.setdefault(current_key, 0)

        kept_dirs: list[str] = []
        for dirname in dirs:
            child = current_path / dirname
            try:
                stat = child.lstat()
            except OSError:
                skipped += 1
                continue
            if child.is_symlink() or stat.st_dev != root_device:
                continue
            kept_dirs.append(dirname)
            parents[str(child)] = current_key
        dirs[:] = kept_dirs

        for filename in files:
            child = current_path / filename
            try:
                stat = child.lstat()
            except OSError:
                skipped += 1
                continue
            if not child.is_symlink():
                direct_sizes[current_key] += stat.st_size

    total_sizes = dict(direct_sizes)
    for path in sorted(total_sizes, key=lambda value: value.count(os.sep), reverse=True):
        parent = parents.get(path)
        if parent is not None:
            total_sizes[parent] = total_sizes.get(parent, 0) + total_sizes[path]

    rows = [
        {"size": _format_df_bytes(size), "bytes": size, "path": path}
        for path, size in total_sizes.items()
    ]
    rows.sort(key=lambda row: int(row["bytes"]), reverse=True)
    return {"files": rows[:limit], "skipped": skipped}


@dataclass
class ProcessSample:
    name: str
    total_ticks: int
    threads: int
    pid: int
    user: str


def _clock_ticks() -> int:
    try:
        return int(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
    except (KeyError, OSError, ValueError):
        return 100


def _format_cpu_time(total_ticks: int, ticks_per_second: int) -> str:
    total_seconds = total_ticks // ticks_per_second
    hours, remainder = divmod(total_seconds, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _user_for_pid(pid_dir: Path) -> str:
    status = _read_text(pid_dir / "status")
    match = re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE)
    if not match:
        return "unknown"
    uid = int(match.group(1))
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _read_process_sample(pid_dir: Path) -> ProcessSample | None:
    try:
        pid = int(pid_dir.name)
    except ValueError:
        return None

    stat = _read_text(pid_dir / "stat")
    if not stat:
        return None

    match = re.match(r"^(\d+)\s+\((.*)\)\s+(.+)$", stat)
    if not match:
        return None

    fields = match.group(3).split()
    if len(fields) <= 17:
        return None

    try:
        user_ticks = int(fields[11])
        system_ticks = int(fields[12])
        threads = int(fields[17])
    except ValueError:
        return None

    name = _read_text(pid_dir / "comm").strip() or match.group(2)
    return ProcessSample(
        name=name,
        total_ticks=user_ticks + system_ticks,
        threads=threads,
        pid=pid,
        user=_user_for_pid(pid_dir),
    )


class ProcessSampler:
    def __init__(self) -> None:
        self._ticks_per_second = _clock_ticks()
        self._previous_cpu_total = read_cpu_sample().total
        self._previous_process_ticks = self._read_process_ticks()

    def _read_process_ticks(self) -> dict[int, int]:
        samples = self._read_samples()
        return {sample.pid: sample.total_ticks for sample in samples}

    def _read_samples(self) -> list[ProcessSample]:
        try:
            pid_dirs = [child for child in PROC.iterdir() if child.name.isdigit()]
        except OSError:
            return []
        samples: list[ProcessSample] = []
        for pid_dir in pid_dirs:
            sample = _read_process_sample(pid_dir)
            if sample is not None:
                samples.append(sample)
        return samples

    def sample(self, limit: int = 30) -> dict[str, list[dict[str, object]]]:
        current_cpu_total = read_cpu_sample().total
        current_samples = self._read_samples()
        current_process_ticks = {sample.pid: sample.total_ticks for sample in current_samples}
        cpu_delta = current_cpu_total - self._previous_cpu_total
        cpu_count = os.cpu_count() or 1

        rows: list[dict[str, object]] = []
        for sample in current_samples:
            previous_ticks = self._previous_process_ticks.get(sample.pid, sample.total_ticks)
            process_delta = max(0, sample.total_ticks - previous_ticks)
            cpu_percent = 0.0
            if cpu_delta > 0:
                cpu_percent = (process_delta / cpu_delta) * cpu_count * 100
            rows.append(
                {
                    "name": sample.name,
                    "cpu": round(cpu_percent, 1),
                    "cpuTime": _format_cpu_time(sample.total_ticks, self._ticks_per_second),
                    "threads": sample.threads,
                    "pid": sample.pid,
                    "user": sample.user,
                }
            )

        self._previous_cpu_total = current_cpu_total
        self._previous_process_ticks = current_process_ticks
        rows.sort(key=lambda row: float(row["cpu"]), reverse=True)
        return {"processes": rows[:limit]}


@dataclass
class CpuSample:
    idle: int
    total: int


def read_cpu_sample() -> CpuSample:
    lines = _read_text(PROC / "stat").splitlines()
    if not lines:
        return CpuSample(idle=0, total=0)
    parts = [int(value) for value in lines[0].split()[1:]]
    if len(parts) < 4:
        return CpuSample(idle=0, total=0)
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    total = sum(parts)
    return CpuSample(idle=idle, total=total)


class MetricsSampler:
    def __init__(self) -> None:
        self._previous_cpu = read_cpu_sample()

    def cpu_percent(self) -> int:
        current = read_cpu_sample()
        idle_delta = current.idle - self._previous_cpu.idle
        total_delta = current.total - self._previous_cpu.total
        self._previous_cpu = current
        if total_delta <= 0:
            return 0
        return round((1 - idle_delta / total_delta) * 100)

    def usage(self) -> dict[str, int]:
        return usage_percentages(self.cpu_percent())

    def snapshot(self) -> dict[str, object]:
        return {
            "usage": self.usage(),
            "uptime": uptime(),
            "info": system_info(),
        }
