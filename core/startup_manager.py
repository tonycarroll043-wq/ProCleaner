"""
Startup Manager - Read, enable, disable, and delete startup entries
from registry (HKLM/HKCU Run keys) and Startup folders.
"""
import os
import sys
import glob
from pathlib import Path
from typing import List, Dict, Optional

if sys.platform == "win32":
    import winreg


class StartupEntry:
    def __init__(self, name: str, command: str, source: str, enabled: bool, location: str):
        self.name = name
        self.command = command
        self.source = source      # 'Registry' or 'Folder'
        self.enabled = enabled
        self.location = location  # registry path or folder path
        self.exe_exists: bool = self._check_exe()
        self.publisher: str = self._get_publisher()

    def _check_exe(self) -> bool:
        exe = self.command.strip('"').split('"')[0].split(" ")[0].strip()
        if not exe:
            return True
        # expand env vars
        exe = os.path.expandvars(exe)
        return os.path.isfile(exe)

    def _get_publisher(self) -> str:
        exe = self.command.strip('"').split('"')[0].strip()
        exe = os.path.expandvars(exe)
        if sys.platform == "win32" and os.path.isfile(exe):
            try:
                import win32api
                info = win32api.GetFileVersionInfo(exe, r"\StringFileInfo\040904B0\CompanyName")
                return info or "Unknown"
            except Exception:
                pass
        return "Unknown"

    def __repr__(self):
        return f"StartupEntry({self.name!r}, enabled={self.enabled})"


class StartupManager:
    REGISTRY_LOCATIONS = [
        (True,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",      "HKLM Run"),
        (True,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",  "HKLM RunOnce"),
        (False, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",      "HKCU Run"),
        (False, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",  "HKCU RunOnce"),
        (True,  r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "HKLM Run (32-bit)"),
    ]

    DISABLED_KEY = r"SOFTWARE\Microsoft\Shared Tools\MSConfig\startupreg"

    def __init__(self):
        self.entries: List[StartupEntry] = []

    # ------------------------------------------------------------------ #
    # Enumerate
    # ------------------------------------------------------------------ #
    def get_all(self) -> List[StartupEntry]:
        self.entries = []
        self.entries.extend(self._from_registry())
        self.entries.extend(self._from_folders())
        return self.entries

    def _from_registry(self) -> List[StartupEntry]:
        entries = []
        if sys.platform != "win32":
            return entries
        for is_hklm, key_path, label in self.REGISTRY_LOCATIONS:
            hive = winreg.HKEY_LOCAL_MACHINE if is_hklm else winreg.HKEY_CURRENT_USER
            try:
                key = winreg.OpenKey(hive, key_path)
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        entries.append(StartupEntry(
                            name=name,
                            command=str(val),
                            source="Registry",
                            enabled=True,
                            location=f"{'HKLM' if is_hklm else 'HKCU'}\\{key_path}",
                        ))
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except (OSError, PermissionError):
                pass

        # Disabled entries stored by MSConfig
        try:
            hive = winreg.HKEY_LOCAL_MACHINE
            key = winreg.OpenKey(hive, self.DISABLED_KEY)
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(key, i)
                    sub_key = winreg.OpenKey(hive, f"{self.DISABLED_KEY}\\{sub_name}")
                    try:
                        cmd, _ = winreg.QueryValueEx(sub_key, "command")
                        loc, _ = winreg.QueryValueEx(sub_key, "hkey")
                        entries.append(StartupEntry(
                            name=sub_name, command=str(cmd),
                            source="Registry", enabled=False, location=str(loc)
                        ))
                    except Exception:
                        pass
                    winreg.CloseKey(sub_key)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (OSError, PermissionError):
            pass
        return entries

    def _from_folders(self) -> List[StartupEntry]:
        entries = []
        folders = [
            str(Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup",
        ]
        for folder in folders:
            if not os.path.isdir(folder):
                continue
            for fp in glob.glob(os.path.join(folder, "*")):
                name = os.path.splitext(os.path.basename(fp))[0]
                entries.append(StartupEntry(
                    name=name, command=fp,
                    source="Folder", enabled=True, location=folder
                ))
        return entries

    # ------------------------------------------------------------------ #
    # Enable / Disable / Delete
    # ------------------------------------------------------------------ #
    def disable(self, entry: StartupEntry) -> bool:
        if sys.platform != "win32" or not entry.enabled:
            return False
        if entry.source == "Registry":
            # Move value to MSConfig disabled key
            return self._registry_disable(entry)
        else:
            # Rename .lnk/.exe to .disabled
            new_path = entry.location + ".disabled"
            try:
                os.rename(entry.command, new_path)
                entry.enabled = False
                return True
            except OSError:
                return False

    def enable(self, entry: StartupEntry) -> bool:
        if sys.platform != "win32" or entry.enabled:
            return False
        if entry.source == "Registry":
            return self._registry_enable(entry)
        else:
            orig = entry.command.replace(".disabled", "")
            try:
                os.rename(entry.command, orig)
                entry.enabled = True
                return True
            except OSError:
                return False

    def delete(self, entry: StartupEntry) -> bool:
        if sys.platform != "win32":
            return False
        if entry.source == "Registry":
            hive = winreg.HKEY_LOCAL_MACHINE if "HKLM" in entry.location else winreg.HKEY_CURRENT_USER
            key_path = entry.location.split("\\", 1)[1] if "\\" in entry.location else entry.location
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WRITE)
                winreg.DeleteValue(key, entry.name)
                winreg.CloseKey(key)
                self.entries = [e for e in self.entries if e is not entry]
                return True
            except Exception:
                return False
        else:
            try:
                os.remove(entry.command)
                self.entries = [e for e in self.entries if e is not entry]
                return True
            except OSError:
                return False

    def _registry_disable(self, entry: StartupEntry) -> bool:
        try:
            hive = winreg.HKEY_LOCAL_MACHINE if "HKLM" in entry.location else winreg.HKEY_CURRENT_USER
            key_path = entry.location.split("\\", 1)[1] if "\\" in entry.location else entry.location
            src_key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WRITE)
            winreg.DeleteValue(src_key, entry.name)
            winreg.CloseKey(src_key)

            # Write to disabled location
            dis_path = f"{self.DISABLED_KEY}\\{entry.name}"
            dis_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, dis_path)
            winreg.SetValueEx(dis_key, "command", 0, winreg.REG_SZ, entry.command)
            winreg.SetValueEx(dis_key, "hkey", 0, winreg.REG_SZ, entry.location)
            winreg.SetValueEx(dis_key, "key", 0, winreg.REG_SZ, key_path)
            winreg.SetValueEx(dis_key, "item", 0, winreg.REG_SZ, entry.name)
            winreg.CloseKey(dis_key)
            entry.enabled = False
            return True
        except Exception:
            return False

    def _registry_enable(self, entry: StartupEntry) -> bool:
        try:
            hive = winreg.HKEY_LOCAL_MACHINE if "HKLM" in entry.location else winreg.HKEY_CURRENT_USER
            key_path = entry.location.split("\\", 1)[1] if "\\" in entry.location else entry.location
            run_key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WRITE)
            winreg.SetValueEx(run_key, entry.name, 0, winreg.REG_SZ, entry.command)
            winreg.CloseKey(run_key)

            # Remove from disabled
            try:
                dis_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, self.DISABLED_KEY, 0,
                    winreg.KEY_SET_VALUE | winreg.KEY_WRITE
                )
                winreg.DeleteKey(dis_key, entry.name)
                winreg.CloseKey(dis_key)
            except Exception:
                pass
            entry.enabled = True
            return True
        except Exception:
            return False
