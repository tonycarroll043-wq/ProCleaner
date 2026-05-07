"""
Real-time Monitor - Watches temp directories using watchdog and notifies
when junk accumulates beyond a threshold.  Also tracks browser close events.
"""
import os
import sys
import time
import threading
from pathlib import Path
from typing import Callable, Optional, List, Dict

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    WATCHDOG_OK = True
except ImportError:
    WATCHDOG_OK = False


WATCH_PATHS = [
    os.environ.get("TEMP", ""),
    os.environ.get("TMP", ""),
    # C:\Windows\Temp requires admin — skip by default, added only if elevated
]


class JunkAccumulationHandler(FileSystemEventHandler if WATCHDOG_OK else object):
    def __init__(self, threshold_mb: float, alert_cb: Callable[[float], None]):
        if WATCHDOG_OK:
            super().__init__()
        self.threshold_bytes = threshold_mb * 1024 * 1024
        self.alert_cb = alert_cb
        self._accumulated = 0
        self._last_alert = 0
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        try:
            sz = os.path.getsize(event.src_path)
            with self._lock:
                self._accumulated += sz
                now = time.time()
                if self._accumulated >= self.threshold_bytes and (now - self._last_alert) > 60:
                    self._last_alert = now
                    mb = self._accumulated / 1024**2
                    self._accumulated = 0
                    self.alert_cb(mb)
        except (OSError, PermissionError):
            pass


class RealTimeMonitor:
    def __init__(
        self,
        threshold_mb: float = 100,
        alert_cb: Optional[Callable[[str, float], None]] = None,
    ):
        self.threshold_mb = threshold_mb
        self.alert_cb = alert_cb or self._default_alert
        self._observer: Optional[object] = None
        self._running = False
        self._stats: Dict[str, int] = {"files_created": 0, "bytes_added": 0}

    # ------------------------------------------------------------------ #
    # Start / Stop
    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        if not WATCHDOG_OK:
            return False
        if self._running:
            return True
        handler = JunkAccumulationHandler(self.threshold_mb, self._on_threshold)
        self._observer = Observer()
        watched = 0
        for path in WATCH_PATHS:
            if path and os.path.isdir(path):
                try:
                    self._observer.schedule(handler, path, recursive=False)
                    watched += 1
                except (PermissionError, OSError, Exception):
                    pass
        # Also try Windows\Temp if we have access
        win_temp = r"C:\Windows\Temp"
        if os.path.isdir(win_temp):
            try:
                self._observer.schedule(handler, win_temp, recursive=False)
                watched += 1
            except (PermissionError, OSError, Exception):
                pass
        if watched == 0:
            return False
        try:
            self._observer.start()
        except Exception:
            return False
        self._running = True
        return True

    def stop(self):
        if self._observer and self._running:
            try:
                self._observer.stop()
                self._observer.join(timeout=3)
            except Exception:
                pass
        self._running = False
        self._observer = None

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------ #
    # Alert handling
    # ------------------------------------------------------------------ #
    def _on_threshold(self, mb: float):
        self.alert_cb("Temp Folders", mb)

    @staticmethod
    def _default_alert(source: str, mb: float):
        print(f"[Monitor] {source}: {mb:.1f} MB of junk accumulated")

    # ------------------------------------------------------------------ #
    # Snapshot current junk size
    # ------------------------------------------------------------------ #
    def snapshot_junk_size(self) -> Dict[str, float]:
        result = {}
        for path in WATCH_PATHS:
            if not path or not os.path.isdir(path):
                continue
            size = 0
            for root, _, files in os.walk(path):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass
            result[path] = size / 1024**2
        return result

    # ------------------------------------------------------------------ #
    # Browser close watcher (polling)
    # ------------------------------------------------------------------ #
    def start_browser_watcher(
        self,
        browser_names: List[str],
        on_close_cb: Callable[[str], None],
        poll_interval: float = 5.0,
    ):
        """Polls for browser process disappearance and fires callback."""
        try:
            import psutil
        except ImportError:
            return

        browser_exe_map = {
            "Google Chrome": "chrome.exe",
            "Microsoft Edge": "msedge.exe",
            "Mozilla Firefox": "firefox.exe",
            "Opera GX": "opera.exe",
        }

        def _poll():
            was_running = {b: False for b in browser_names}
            while self._running:
                for browser in browser_names:
                    exe = browser_exe_map.get(browser, "")
                    if not exe:
                        continue
                    running = any(
                        p.name().lower() == exe.lower()
                        for p in psutil.process_iter(["name"])
                    )
                    if was_running[browser] and not running:
                        on_close_cb(browser)
                    was_running[browser] = running
                time.sleep(poll_interval)

        t = threading.Thread(target=_poll, daemon=True)
        t.start()
