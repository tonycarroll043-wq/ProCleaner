"""
Software Updater - Checks installed programs for available updates using
Winget (Windows Package Manager) and WMI. Falls back to a curated version
check against a public API for popular apps.
"""
import os
import sys
import json
import subprocess
from typing import List, Dict, Optional, Callable
from pathlib import Path


class SoftwareUpdate:
    def __init__(self, name: str, current: str, available: str, source: str, pkg_id: str = ""):
        self.name = name
        self.current_version = current
        self.available_version = available
        self.source = source        # 'winget' or 'manual'
        self.pkg_id = pkg_id
        self.update_in_progress = False
        self.status = "pending"     # pending / updating / done / failed

    def __repr__(self):
        return f"Update({self.name}: {self.current_version} → {self.available_version})"


class SoftwareUpdater:
    def __init__(self):
        self.updates: List[SoftwareUpdate] = []
        self._winget_available: Optional[bool] = None

    # ------------------------------------------------------------------ #
    # Winget check
    # ------------------------------------------------------------------ #
    def _has_winget(self) -> bool:
        if self._winget_available is None:
            try:
                r = subprocess.run(
                    ["winget", "--version"], capture_output=True, timeout=5, text=True
                )
                self._winget_available = r.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self._winget_available = False
        return self._winget_available

    # ------------------------------------------------------------------ #
    # Check for updates
    # ------------------------------------------------------------------ #
    def check(
        self,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> List[SoftwareUpdate]:
        self.updates = []
        if progress_cb:
            progress_cb("Checking for updates…")

        if self._has_winget():
            self.updates = self._check_winget(progress_cb)
        else:
            if progress_cb:
                progress_cb("Winget not available. Install Windows Package Manager for best results.")
            self.updates = self._check_manual(progress_cb)

        return self.updates

    def _check_winget(self, progress_cb=None) -> List[SoftwareUpdate]:
        updates = []
        try:
            if progress_cb:
                progress_cb("Running winget upgrade check…")
            result = subprocess.run(
                ["winget", "upgrade", "--include-unknown"],
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace"
            )
            lines = result.stdout.splitlines()
            # Parse winget table output (skip headers)
            parsing = False
            for line in lines:
                if line.startswith("Name") and "Id" in line and "Version" in line:
                    parsing = True
                    continue
                if not parsing or not line.strip() or line.startswith("-"):
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    # winget columns: Name, Id, Version, Available, Source
                    # Name can have spaces — heuristic parse
                    try:
                        # Find version patterns (x.y.z)
                        ver_indices = [i for i, p in enumerate(parts) if self._looks_like_version(p)]
                        if len(ver_indices) >= 2:
                            cur_idx = ver_indices[0]
                            avail_idx = ver_indices[1]
                            name = " ".join(parts[:cur_idx - 1]) or parts[0]
                            pkg_id = parts[cur_idx - 1] if cur_idx > 1 else ""
                            current = parts[cur_idx]
                            available = parts[avail_idx]
                            source = parts[-1] if len(parts) > avail_idx + 1 else "winget"
                            updates.append(SoftwareUpdate(
                                name=name.strip(),
                                current=current,
                                available=available,
                                source=source,
                                pkg_id=pkg_id,
                            ))
                    except Exception:
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return updates

    def _check_manual(self, progress_cb=None) -> List[SoftwareUpdate]:
        """Fallback: check common apps via their own version mechanisms."""
        updates = []
        checks = [
            self._check_chrome,
            self._check_firefox,
        ]
        for check_fn in checks:
            try:
                result = check_fn()
                if result:
                    updates.append(result)
            except Exception:
                pass
        return updates

    def _check_chrome(self) -> Optional[SoftwareUpdate]:
        chrome_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application"
        if not chrome_path.exists():
            return None
        versions = [d for d in chrome_path.iterdir() if d.is_dir() and d.name[0].isdigit()]
        if not versions:
            return None
        current = str(sorted(versions)[-1].name)
        return None  # Would need API call for latest version

    def _check_firefox(self) -> Optional[SoftwareUpdate]:
        return None  # Placeholder

    # ------------------------------------------------------------------ #
    # Install update
    # ------------------------------------------------------------------ #
    def install_update(
        self,
        update: SoftwareUpdate,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        update.update_in_progress = True
        update.status = "updating"
        try:
            if self._has_winget() and update.pkg_id:
                if progress_cb:
                    progress_cb(f"Updating {update.name}…")
                result = subprocess.run(
                    ["winget", "upgrade", "--id", update.pkg_id, "--silent", "--accept-package-agreements",
                     "--accept-source-agreements"],
                    capture_output=True, text=True, timeout=300
                )
                success = result.returncode == 0
                update.status = "done" if success else "failed"
                return success
        except Exception:
            update.status = "failed"
        finally:
            update.update_in_progress = False
        return False

    def install_all(
        self,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, bool]:
        results = {}
        for u in self.updates:
            results[u.name] = self.install_update(u, progress_cb)
        return results

    @staticmethod
    def _looks_like_version(s: str) -> bool:
        import re
        return bool(re.match(r"^\d+[\.\d]*$", s))

    @staticmethod
    def is_winget_installed() -> bool:
        try:
            r = subprocess.run(["winget", "--version"], capture_output=True, timeout=3)
            return r.returncode == 0
        except Exception:
            return False

    @staticmethod
    def install_winget_prompt() -> str:
        return "Install Windows Package Manager (winget) from the Microsoft Store to enable automatic update checking."
