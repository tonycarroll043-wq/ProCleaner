"""
Performance Optimizer - Lists running processes and background services,
identifies high-impact startup apps, and lets the user freeze/terminate
resource-hungry processes.
"""
import os
import sys
from typing import List, Dict, Optional, Callable

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False


class ProcessInfo:
    def __init__(self, proc):
        self.pid: int = proc.pid
        self.name: str = ""
        self.exe: str = ""
        self.cpu_percent: float = 0.0
        self.memory_mb: float = 0.0
        self.status: str = ""
        self.username: str = ""
        self.num_threads: int = 0
        try:
            with proc.oneshot():
                self.name = proc.name()
                self.exe = proc.exe() if hasattr(proc, "exe") else ""
                self.cpu_percent = proc.cpu_percent(interval=None)
                self.memory_mb = proc.memory_info().rss / 1024 / 1024
                self.status = proc.status()
                self.username = proc.username() or ""
                self.num_threads = proc.num_threads()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.name = "(access denied)"

    @property
    def impact(self) -> str:
        """Rough performance impact rating."""
        score = self.cpu_percent + (self.memory_mb / 50)
        if score > 50:
            return "High"
        if score > 10:
            return "Medium"
        return "Low"

    def __repr__(self):
        return f"ProcessInfo({self.name}, CPU={self.cpu_percent:.1f}%, RAM={self.memory_mb:.1f}MB)"


class ServiceInfo:
    def __init__(self, data: Dict):
        self.name: str = data.get("name", "")
        self.display: str = data.get("display", "")
        self.status: str = data.get("status", "")
        self.start_type: str = data.get("start_type", "")
        self.pid: Optional[int] = data.get("pid")

    @property
    def is_running(self) -> bool:
        return self.status.lower() == "running"


class PerformanceOptimizer:
    def __init__(self):
        self.processes: List[ProcessInfo] = []
        self.services: List[ServiceInfo] = []
        self._cpu_sampled = False

    # ------------------------------------------------------------------ #
    # Processes
    # ------------------------------------------------------------------ #
    def get_processes(
        self,
        sort_by: str = "memory",
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> List[ProcessInfo]:
        if not PSUTIL_OK:
            return []
        if progress_cb:
            progress_cb("Sampling CPU usage (1s)…")

        # First pass – trigger CPU measurement
        procs = []
        for p in psutil.process_iter():
            try:
                p.cpu_percent(interval=None)
                procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Brief wait for CPU sample to stabilise
        import time
        time.sleep(0.5)

        # Second pass – collect
        self.processes = []
        for p in procs:
            try:
                info = ProcessInfo(p)
                self.processes.append(info)
            except Exception:
                pass

        if sort_by == "cpu":
            self.processes.sort(key=lambda x: x.cpu_percent, reverse=True)
        elif sort_by == "memory":
            self.processes.sort(key=lambda x: x.memory_mb, reverse=True)
        elif sort_by == "name":
            self.processes.sort(key=lambda x: x.name.lower())

        return self.processes

    def kill_process(self, pid: int) -> bool:
        if not PSUTIL_OK:
            return False
        try:
            p = psutil.Process(pid)
            p.terminate()
            p.wait(timeout=5)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
            try:
                psutil.Process(pid).kill()
                return True
            except Exception:
                return False

    def get_system_metrics(self) -> Dict:
        if not PSUTIL_OK:
            return {}
        metrics = {}
        # CPU
        metrics["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        metrics["cpu_count"] = psutil.cpu_count(logical=True)
        metrics["cpu_freq"] = getattr(psutil.cpu_freq(), "current", 0) if psutil.cpu_freq() else 0
        # Memory
        vm = psutil.virtual_memory()
        metrics["ram_total_gb"] = round(vm.total / 1024**3, 1)
        metrics["ram_used_gb"] = round(vm.used / 1024**3, 1)
        metrics["ram_percent"] = vm.percent
        # Disk I/O
        try:
            dio = psutil.disk_io_counters()
            metrics["disk_read_mb"] = round(dio.read_bytes / 1024**2, 1)
            metrics["disk_write_mb"] = round(dio.write_bytes / 1024**2, 1)
        except Exception:
            pass
        # Network
        try:
            net = psutil.net_io_counters()
            metrics["net_sent_mb"] = round(net.bytes_sent / 1024**2, 1)
            metrics["net_recv_mb"] = round(net.bytes_recv / 1024**2, 1)
        except Exception:
            pass
        # Uptime
        try:
            import time
            metrics["uptime_hours"] = round((time.time() - psutil.boot_time()) / 3600, 1)
        except Exception:
            pass
        return metrics

    # ------------------------------------------------------------------ #
    # Services
    # ------------------------------------------------------------------ #
    def get_services(self) -> List[ServiceInfo]:
        if not PSUTIL_OK or sys.platform != "win32":
            return []
        self.services = []
        try:
            for svc in psutil.win_service_iter():
                try:
                    info = svc.as_dict()
                    self.services.append(ServiceInfo({
                        "name": info.get("name", ""),
                        "display": info.get("display_name", ""),
                        "status": info.get("status", ""),
                        "start_type": info.get("start_type", ""),
                        "pid": info.get("pid"),
                    }))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return self.services

    def stop_service(self, name: str) -> bool:
        import subprocess
        try:
            r = subprocess.run(["sc", "stop", name], capture_output=True, timeout=15)
            return r.returncode == 0
        except Exception:
            return False

    def start_service(self, name: str) -> bool:
        import subprocess
        try:
            r = subprocess.run(["sc", "start", name], capture_output=True, timeout=15)
            return r.returncode == 0
        except Exception:
            return False

    def set_service_startup(self, name: str, start_type: str) -> bool:
        """start_type: 'auto', 'demand', 'disabled'"""
        import subprocess
        sc_map = {"auto": "auto", "demand": "demand", "disabled": "disabled"}
        sc_type = sc_map.get(start_type, "demand")
        try:
            r = subprocess.run(["sc", "config", name, f"start={sc_type}"], capture_output=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # High-impact identifier
    # ------------------------------------------------------------------ #
    def get_high_impact_processes(self, threshold_mb: float = 200) -> List[ProcessInfo]:
        return [p for p in self.processes if p.memory_mb >= threshold_mb or p.cpu_percent >= 10]
