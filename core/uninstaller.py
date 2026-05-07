"""
Uninstaller - Lists all installed programs from registry, runs their uninstallers,
and cleans up leftover files/registry keys.
"""
import os
import sys
import subprocess
from typing import List, Dict, Optional, Callable
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    import winreg


class InstalledProgram:
    def __init__(self, data: Dict):
        self.name: str = data.get("DisplayName", "Unknown")
        self.version: str = data.get("DisplayVersion", "")
        self.publisher: str = data.get("Publisher", "Unknown")
        self.install_date: str = data.get("InstallDate", "")
        self.install_location: str = data.get("InstallLocation", "")
        self.install_size: int = self._parse_size(data.get("EstimatedSize", 0))
        self.uninstall_string: str = data.get("UninstallString", "")
        self.quiet_uninstall: str = data.get("QuietUninstallString", "")
        self.registry_key: str = data.get("_reg_key", "")
        self.registry_hive: int = data.get("_hive", 0)
        self.system_component: bool = bool(data.get("SystemComponent", False))
        self.no_remove: bool = bool(data.get("NoRemove", False))

    @staticmethod
    def _parse_size(val) -> int:
        try:
            return int(val) * 1024  # EstimatedSize is in KB
        except (ValueError, TypeError):
            return 0

    @property
    def size_str(self) -> str:
        sz = self.install_size
        for unit in ("B", "KB", "MB", "GB"):
            if sz < 1024:
                return f"{sz:.1f} {unit}"
            sz /= 1024
        return f"{sz:.1f} GB"

    @property
    def install_date_formatted(self) -> str:
        if not self.install_date:
            return "Unknown"
        try:
            d = datetime.strptime(self.install_date, "%Y%m%d")
            return d.strftime("%Y-%m-%d")
        except Exception:
            return self.install_date

    def __repr__(self):
        return f"InstalledProgram({self.name!r}, {self.version})"


class Uninstaller:
    UNINSTALL_PATHS = [
        (True,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (True,  r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (False, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    def __init__(self):
        self.programs: List[InstalledProgram] = []

    # ------------------------------------------------------------------ #
    # Enumerate
    # ------------------------------------------------------------------ #
    def get_installed(self, include_system: bool = False) -> List[InstalledProgram]:
        if sys.platform != "win32":
            return []
        self.programs = []
        seen: set = set()

        for is_hklm, kp in self.UNINSTALL_PATHS:
            hive = winreg.HKEY_LOCAL_MACHINE if is_hklm else winreg.HKEY_CURRENT_USER
            try:
                key = winreg.OpenKey(hive, kp)
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        sub_key = winreg.OpenKey(hive, f"{kp}\\{sub_name}")
                        data = self._read_key(sub_key)
                        data["_reg_key"] = f"{kp}\\{sub_name}"
                        data["_hive"] = hive
                        winreg.CloseKey(sub_key)

                        prog = InstalledProgram(data)
                        # Skip entries without display name or uninstall string
                        if not prog.name or prog.name == "Unknown":
                            i += 1
                            continue
                        if not include_system and (prog.system_component or prog.no_remove):
                            i += 1
                            continue
                        uid = f"{prog.name}_{prog.version}"
                        if uid not in seen:
                            seen.add(uid)
                            self.programs.append(prog)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except (OSError, PermissionError):
                pass

        self.programs.sort(key=lambda p: p.name.lower())
        return self.programs

    @staticmethod
    def _read_key(key) -> Dict:
        data = {}
        fields = [
            "DisplayName", "DisplayVersion", "Publisher", "InstallDate",
            "InstallLocation", "EstimatedSize", "UninstallString",
            "QuietUninstallString", "SystemComponent", "NoRemove",
        ]
        for field in fields:
            try:
                val, _ = winreg.QueryValueEx(key, field)
                data[field] = val
            except (FileNotFoundError, OSError):
                pass
        return data

    # ------------------------------------------------------------------ #
    # Uninstall
    # ------------------------------------------------------------------ #
    def uninstall(
        self,
        program: InstalledProgram,
        silent: bool = False,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        cmd = program.quiet_uninstall if (silent and program.quiet_uninstall) else program.uninstall_string
        if not cmd:
            return False
        if progress_cb:
            progress_cb(f"Running uninstaller for {program.name}…")
        try:
            result = subprocess.run(cmd, shell=True, timeout=300)
            success = result.returncode == 0
            if success:
                if progress_cb:
                    progress_cb(f"Cleaning up leftovers for {program.name}…")
                self._cleanup_leftovers(program)
            return success
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False

    def _cleanup_leftovers(self, program: InstalledProgram):
        """Remove lingering install folder and registry key after uninstall."""
        # Remove install folder if still exists
        if program.install_location and os.path.isdir(program.install_location):
            import shutil
            try:
                shutil.rmtree(program.install_location, ignore_errors=True)
            except Exception:
                pass

        # Remove registry key
        if program.registry_key and program.registry_hive:
            try:
                parent, _, child = program.registry_key.rpartition("\\")
                key = winreg.OpenKey(
                    program.registry_hive, parent, 0,
                    winreg.KEY_SET_VALUE | winreg.KEY_WRITE
                )
                winreg.DeleteKey(key, child)
                winreg.CloseKey(key)
            except Exception:
                pass

        # Remove AppData remnants
        for base in [
            os.environ.get("APPDATA", ""),
            os.environ.get("LOCALAPPDATA", ""),
            r"C:\ProgramData",
        ]:
            if not base:
                continue
            for candidate in [program.name, program.publisher]:
                if not candidate or candidate in ("Unknown", ""):
                    continue
                # Only first word of name for safety
                safe = candidate.split()[0]
                path = os.path.join(base, safe)
                if os.path.isdir(path):
                    import shutil
                    try:
                        shutil.rmtree(path, ignore_errors=True)
                    except Exception:
                        pass

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def search(self, query: str) -> List[InstalledProgram]:
        q = query.lower()
        return [p for p in self.programs if q in p.name.lower() or q in p.publisher.lower()]
