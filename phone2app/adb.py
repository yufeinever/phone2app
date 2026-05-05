from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, IO, Iterable, List, Optional, Sequence, Tuple


class AdbError(RuntimeError):
    """Raised when an adb command fails."""


@dataclass
class CommandResult:
    args: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: float


@dataclass
class Device:
    serial: str
    state: str
    model: Optional[str] = None
    product: Optional[str] = None
    transport_id: Optional[str] = None


@dataclass
class ManagedProcess:
    process: subprocess.Popen
    handle: Optional[IO[str]] = None


def find_adb(explicit_path: Optional[str] = None) -> str:
    candidates = [
        explicit_path,
        os.environ.get("ADB"),
        shutil.which("adb"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
        if candidate and shutil.which(candidate):
            return str(candidate)
    raise AdbError("adb not found. Install Android SDK Platform Tools and add adb to PATH.")


class Adb:
    def __init__(self, serial: Optional[str] = None, adb_path: Optional[str] = None, timeout: int = 60):
        self.adb_path = find_adb(adb_path)
        self.serial = serial
        self.timeout = timeout

    def base_args(self) -> List[str]:
        args = [self.adb_path]
        if self.serial:
            args += ["-s", self.serial]
        return args

    def run(
        self,
        args: Iterable[str],
        timeout: Optional[int] = None,
        check: bool = True,
        encoding: str = "utf-8",
    ) -> CommandResult:
        full_args = self.base_args() + list(args)
        started = time.perf_counter()
        completed = subprocess.run(
            full_args,
            capture_output=True,
            text=True,
            encoding=encoding,
            errors="replace",
            timeout=timeout or self.timeout,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        result = CommandResult(full_args, completed.returncode, completed.stdout, completed.stderr, elapsed_ms)
        if check and completed.returncode != 0:
            raise AdbError(f"adb failed ({completed.returncode}): {' '.join(full_args)}\n{completed.stderr.strip()}")
        return result

    def shell(self, command: str, timeout: Optional[int] = None, check: bool = True) -> CommandResult:
        return self.run(["shell", command], timeout=timeout, check=check)

    def devices(self) -> List[Device]:
        result = self.run(["devices", "-l"], check=True)
        devices: List[Device] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            attrs: Dict[str, str] = {}
            for item in parts[2:]:
                if ":" in item:
                    key, value = item.split(":", 1)
                    attrs[key] = value
            devices.append(
                Device(
                    serial=parts[0],
                    state=parts[1],
                    model=attrs.get("model"),
                    product=attrs.get("product"),
                    transport_id=attrs.get("transport_id"),
                )
            )
        return devices

    def choose_device(self, requested_serial: Optional[str] = None) -> Device:
        devices = self.devices()
        authorized = [device for device in devices if device.state == "device"]
        if requested_serial:
            for device in authorized:
                if device.serial == requested_serial:
                    self.serial = requested_serial
                    return device
            raise AdbError(f"Requested device {requested_serial!r} is not connected or not authorized.")
        if not authorized:
            raise AdbError("No authorized adb device found. Check USB debugging authorization.")
        if len(authorized) > 1:
            serials = ", ".join(device.serial for device in authorized)
            raise AdbError(f"Multiple devices found ({serials}). Pass --serial to choose one.")
        self.serial = authorized[0].serial
        return authorized[0]

    def getprop(self, key: str) -> str:
        return self.shell(f"getprop {key}").stdout.strip()

    def device_info(self) -> Dict[str, str]:
        keys = {
            "manufacturer": "ro.product.manufacturer",
            "brand": "ro.product.brand",
            "model": "ro.product.model",
            "device": "ro.product.device",
            "android_version": "ro.build.version.release",
            "sdk": "ro.build.version.sdk",
            "build_fingerprint": "ro.build.fingerprint",
        }
        return {name: self.getprop(prop) for name, prop in keys.items()}

    def install_apk(self, apk_path: str) -> CommandResult:
        return self.run(["install", "-r", apk_path], timeout=300, check=True)

    def force_stop(self, package: str) -> None:
        self.shell(f"am force-stop {package}", check=False)

    def clear_logcat(self) -> None:
        self.run(["logcat", "-c"], check=False)

    def start_activity(self, package: str, activity: Optional[str] = None) -> Tuple[CommandResult, Dict[str, int]]:
        target = package if not activity else f"{package}/{activity}"
        result = self.shell(f"am start -W -n {target}", timeout=30, check=False)
        return result, parse_am_start_w(result.stdout + "\n" + result.stderr)

    def dump_gfxinfo(self, package: str) -> str:
        return self.shell(f"dumpsys gfxinfo {package}", timeout=30, check=False).stdout

    def dump_meminfo(self, package: str) -> str:
        return self.shell(f"dumpsys meminfo {package}", timeout=30, check=False).stdout

    def dump_batterystats(self, package: str) -> str:
        return self.shell(f"dumpsys batterystats --charged {package}", timeout=45, check=False).stdout

    def cpu_snapshot(self, package: str) -> str:
        return self.shell(f"top -b -n 1 | grep {package}", timeout=15, check=False).stdout

    def package_uid(self, package: str) -> Optional[int]:
        output = self.shell(f"cmd package list packages -U {package}", timeout=15, check=False).stdout
        match = re.search(r"uid:(\d+)", output)
        return int(match.group(1)) if match else None

    def uid_net_bytes(self, uid: Optional[int]) -> Optional[Dict[str, int]]:
        if uid is None:
            return None
        stat_path = f"/proc/uid_stat/{uid}"
        rx = self.shell(f"cat {stat_path}/tcp_rcv", timeout=10, check=False).stdout.strip()
        tx = self.shell(f"cat {stat_path}/tcp_snd", timeout=10, check=False).stdout.strip()
        if not rx.isdigit() or not tx.isdigit():
            return None
        return {"rx_bytes": int(rx), "tx_bytes": int(tx)}

    def logcat_process(self, output_path: Path) -> ManagedProcess:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        handle = output_path.open("w", encoding="utf-8", errors="replace")
        args = self.base_args() + ["logcat", "-v", "threadtime"]
        process = subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, text=True)
        return ManagedProcess(process=process, handle=handle)

    def pull(self, remote: str, local: Path, timeout: int = 120) -> CommandResult:
        local.parent.mkdir(parents=True, exist_ok=True)
        return self.run(["pull", remote, str(local)], timeout=timeout, check=True)

    def remove_remote(self, remote: str) -> None:
        self.shell(f"rm -f {remote}", timeout=15, check=False)


def parse_am_start_w(output: str) -> Dict[str, int]:
    metrics: Dict[str, int] = {}
    for key in ("ThisTime", "TotalTime", "WaitTime"):
        match = re.search(rf"{key}:\s*(-?\d+)", output)
        if match:
            metrics[key] = int(match.group(1))
    return metrics


def parse_meminfo_pss_kb(output: str) -> Optional[int]:
    for line in output.splitlines():
        if line.strip().startswith("TOTAL"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    match = re.search(r"TOTAL\s+(\d+)", output)
    return int(match.group(1)) if match else None


def parse_gfxinfo(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    total_match = re.search(r"Total frames rendered:\s*(\d+)", output)
    janky_match = re.search(r"Janky frames:\s*(\d+)\s*\(([\d.]+)%\)", output)
    p90_match = re.search(r"90th percentile:\s*([\d.]+)ms", output)
    p95_match = re.search(r"95th percentile:\s*([\d.]+)ms", output)
    p99_match = re.search(r"99th percentile:\s*([\d.]+)ms", output)
    if total_match:
        metrics["total_frames"] = float(total_match.group(1))
    if janky_match:
        metrics["janky_frames"] = float(janky_match.group(1))
        metrics["janky_percent"] = float(janky_match.group(2))
    if p90_match:
        metrics["frame_p90_ms"] = float(p90_match.group(1))
    if p95_match:
        metrics["frame_p95_ms"] = float(p95_match.group(1))
    if p99_match:
        metrics["frame_p99_ms"] = float(p99_match.group(1))
    return metrics
