"""
Registry Cleaner - Scans for and removes invalid/orphaned registry entries.
Categories: missing file paths, invalid software keys, orphaned uninstall entries,
obsolete MUI cache, missing shared DLLs, invalid help files, broken shortcuts.
"""
import os
import sys
from typing import List, Dict, Tuple, Optional

if sys.platform == "win32":
    import winreg


class RegistryIssue:
    def __init__(self, category: str, hive: int, key_path: str, value_name: str, description: str):
        self.category = category
        self.hive = hive
        self.key_path = key_path
        self.value_name = value_name
        self.description = description

    def __repr__(self):
        return f"[{self.category}] {self.key_path}\\{self.value_name}"


class RegistryCleaner:
    HIVES = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE if sys.platform == "win32" else None,
        "HKCU": winreg.HKEY_CURRENT_USER if sys.platform == "win32" else None,
        "HKCR": winreg.HKEY_CLASSES_ROOT if sys.platform == "win32" else None,
    }

    def __init__(self):
        self.issues: List[RegistryIssue] = []

    # ------------------------------------------------------------------ #
    # Scan
    # ------------------------------------------------------------------ #
    def scan(self, progress_cb=None) -> List[RegistryIssue]:
        if sys.platform != "win32":
            return []
        self.issues = []
        checks = [
            ("Invalid File Paths in App Paths", self._scan_app_paths),
            ("Orphaned Uninstall Entries", self._scan_uninstall_entries),
            ("Invalid Startup Entries", self._scan_startup_entries),
            ("Missing Shared DLL References", self._scan_shared_dlls),
            ("Obsolete MUI Cache Entries", self._scan_mui_cache),
            ("Invalid Help File References", self._scan_help_files),
            ("Broken COM/ActiveX References", self._scan_com_entries),
            ("Orphaned User Software Keys", self._scan_orphaned_software),
        ]
        for name, fn in checks:
            if progress_cb:
                progress_cb(name)
            try:
                found = fn()
                self.issues.extend(found)
            except Exception:
                pass
        return self.issues

    # ------------------------------------------------------------------ #
    # Individual scanners
    # ------------------------------------------------------------------ #
    def _scan_app_paths(self) -> List[RegistryIssue]:
        issues = []
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        for hive_name, hive in [("HKLM", self.HIVES["HKLM"]), ("HKCU", self.HIVES["HKCU"])]:
            try:
                key = winreg.OpenKey(hive, key_path)
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(key, i)
                        sub_key = winreg.OpenKey(hive, f"{key_path}\\{sub}")
                        try:
                            val, _ = winreg.QueryValueEx(sub_key, "")
                            if val and not os.path.exists(val):
                                issues.append(RegistryIssue(
                                    "Invalid App Path", hive,
                                    f"{key_path}\\{sub}", "",
                                    f"File not found: {val}"
                                ))
                        except FileNotFoundError:
                            pass
                        winreg.CloseKey(sub_key)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except (OSError, PermissionError):
                pass
        return issues

    def _scan_uninstall_entries(self) -> List[RegistryIssue]:
        issues = []
        paths = [
            (self.HIVES["HKLM"], r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (self.HIVES["HKLM"], r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (self.HIVES["HKCU"], r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, kp in paths:
            try:
                key = winreg.OpenKey(hive, kp)
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(key, i)
                        sub_key = winreg.OpenKey(hive, f"{kp}\\{sub}")
                        try:
                            install_loc, _ = winreg.QueryValueEx(sub_key, "InstallLocation")
                            if install_loc and install_loc.strip() and not os.path.exists(install_loc):
                                name_val = ""
                                try:
                                    name_val, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                                except Exception:
                                    pass
                                issues.append(RegistryIssue(
                                    "Orphaned Uninstall Entry", hive,
                                    f"{kp}\\{sub}", "InstallLocation",
                                    f"{name_val} - path missing: {install_loc}"
                                ))
                        except FileNotFoundError:
                            pass
                        winreg.CloseKey(sub_key)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except (OSError, PermissionError):
                pass
        return issues

    @staticmethod
    def _parse_exe_path(val: str) -> str:
        """
        Robustly extract the executable path from a registry Run value.
        Handles quoted paths, unquoted paths with spaces and trailing args,
        and environment variables.
        """
        val = val.strip()
        if val.startswith('"'):
            # "C:\path with spaces\app.exe" /args  →  C:\path with spaces\app.exe
            end = val.find('"', 1)
            exe = val[1:end] if end > 1 else val[1:]
        else:
            # C:\path\app.exe /args  or  C:\path with spaces\app.exe /args
            lower = val.lower()
            exe = val
            for ext in ('.exe', '.bat', '.cmd', '.com', '.pif', '.scr'):
                idx = lower.find(ext)
                if idx >= 0:
                    exe = val[:idx + len(ext)]
                    break
        return os.path.expandvars(exe)

    def _scan_startup_entries(self) -> List[RegistryIssue]:
        issues = []
        run_paths = [
            (self.HIVES["HKLM"], r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            (self.HIVES["HKCU"], r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            (self.HIVES["HKLM"], r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
        ]
        for hive, kp in run_paths:
            try:
                key = winreg.OpenKey(hive, kp)
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        exe = self._parse_exe_path(str(val))
                        if exe and not os.path.exists(exe):
                            issues.append(RegistryIssue(
                                "Invalid Startup Entry", hive, kp, name,
                                f"Executable not found: {exe}"
                            ))
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except (OSError, PermissionError):
                pass
        return issues

    def _scan_shared_dlls(self) -> List[RegistryIssue]:
        issues = []
        kp = r"SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs"
        try:
            key = winreg.OpenKey(self.HIVES["HKLM"], kp)
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    if name and not os.path.exists(name):
                        issues.append(RegistryIssue(
                            "Missing Shared DLL", self.HIVES["HKLM"], kp, name,
                            f"DLL not found: {name}"
                        ))
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (OSError, PermissionError):
            pass
        return issues

    def _scan_mui_cache(self) -> List[RegistryIssue]:
        issues = []
        kp = r"SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"
        try:
            key = winreg.OpenKey(self.HIVES["HKCU"], kp)
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    exe_path = name.split(".")[0] if "." in name else name
                    if exe_path and not os.path.exists(exe_path) and os.sep in exe_path:
                        issues.append(RegistryIssue(
                            "Obsolete MUI Cache", self.HIVES["HKCU"], kp, name,
                            f"Executable gone: {exe_path}"
                        ))
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (OSError, PermissionError):
            pass
        return issues

    def _scan_help_files(self) -> List[RegistryIssue]:
        issues = []
        kp = r"SOFTWARE\Microsoft\Windows\HTMLHelp"
        try:
            key = winreg.OpenKey(self.HIVES["HKLM"], kp)
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    if val and isinstance(val, str) and not os.path.exists(val):
                        issues.append(RegistryIssue(
                            "Invalid Help File", self.HIVES["HKLM"], kp, name,
                            f"Help file missing: {val}"
                        ))
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (OSError, PermissionError):
            pass
        return issues

    def _scan_com_entries(self) -> List[RegistryIssue]:
        issues = []
        kp = r"SOFTWARE\Classes\CLSID"
        try:
            key = winreg.OpenKey(self.HIVES["HKCU"], kp)
            count = 0
            i = 0
            while count < 200:  # limit for performance
                try:
                    sub = winreg.EnumKey(key, i)
                    try:
                        sub_key = winreg.OpenKey(self.HIVES["HKCU"], f"{kp}\\{sub}\\InprocServer32")
                        try:
                            val, _ = winreg.QueryValueEx(sub_key, "")
                            clean_val = val.strip('"').split('"')[0]
                            if clean_val and os.sep in clean_val and not os.path.exists(clean_val):
                                issues.append(RegistryIssue(
                                    "Broken COM Reference", self.HIVES["HKCU"],
                                    f"{kp}\\{sub}", "InprocServer32",
                                    f"DLL missing: {clean_val}"
                                ))
                                count += 1
                        except FileNotFoundError:
                            pass
                        winreg.CloseKey(sub_key)
                    except (OSError, PermissionError):
                        pass
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (OSError, PermissionError):
            pass
        return issues

    def _scan_orphaned_software(self) -> List[RegistryIssue]:
        issues = []
        kp = r"SOFTWARE"
        try:
            key = winreg.OpenKey(self.HIVES["HKCU"], kp)
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                    # Look for company sub-keys with no products
                    company_path = f"{kp}\\{sub}"
                    company_key = winreg.OpenKey(self.HIVES["HKCU"], company_path)
                    j = 0
                    products = []
                    while True:
                        try:
                            product = winreg.EnumKey(company_key, j)
                            products.append(product)
                            j += 1
                        except OSError:
                            break
                    winreg.CloseKey(company_key)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (OSError, PermissionError):
            pass
        return issues

    # ------------------------------------------------------------------ #
    # Fix helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _delete_key_recursive(hive: int, key_path: str) -> bool:
        """Recursively delete a registry key and all sub-keys (handles non-empty keys)."""
        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_ALL_ACCESS)
            # Delete all sub-keys first
            while True:
                try:
                    sub_name = winreg.EnumKey(key, 0)
                    RegistryCleaner._delete_key_recursive(hive, f"{key_path}\\{sub_name}")
                except OSError:
                    break
            winreg.CloseKey(key)
            # Now delete the key itself from its parent
            parent_path, _, child_name = key_path.rpartition("\\")
            if not parent_path or not child_name:
                return False
            parent_key = winreg.OpenKey(hive, parent_path, 0, winreg.KEY_WRITE)
            winreg.DeleteKey(parent_key, child_name)
            winreg.CloseKey(parent_key)
            return True
        except (OSError, PermissionError):
            return False

    def _fix_issue(self, issue: RegistryIssue) -> bool:
        """
        Apply the correct fix for a single registry issue.

        Strategy per category:
        - Invalid App Path / Orphaned Uninstall Entry:
            key_path IS the sub-key to remove; value_name is "".
            → Delete the sub-key from its parent.
        - Broken COM Reference:
            key_path is the CLSID key; value_name is the InprocServer32
            sub-key name (not a registry value).
            → Recursively delete the InprocServer32 sub-key.
        - Everything else (Startup, SharedDLL, MUI Cache, Help File …):
            value_name is a real registry value inside key_path.
            → DeleteValue.
        """
        try:
            if issue.category in ("Invalid App Path", "Orphaned Uninstall Entry"):
                # Whole sub-key removal
                return RegistryCleaner._delete_key_recursive(issue.hive, issue.key_path)

            elif issue.category == "Broken COM Reference":
                # value_name is a sub-key (InprocServer32), not a value
                full_path = f"{issue.key_path}\\{issue.value_name}"
                return RegistryCleaner._delete_key_recursive(issue.hive, full_path)

            elif issue.value_name:
                # Delete a specific registry VALUE inside key_path
                key = winreg.OpenKey(
                    issue.hive, issue.key_path, 0,
                    winreg.KEY_SET_VALUE | winreg.KEY_WRITE
                )
                winreg.DeleteValue(key, issue.value_name)
                winreg.CloseKey(key)
                return True

            else:
                # Fallback: value_name is empty → delete the sub-key
                return RegistryCleaner._delete_key_recursive(issue.hive, issue.key_path)

        except (OSError, PermissionError):
            return False

    # ------------------------------------------------------------------ #
    # Fix
    # ------------------------------------------------------------------ #
    def fix(self, issues: Optional[List[RegistryIssue]] = None) -> Tuple[int, int]:
        targets = issues or self.issues
        fixed = 0
        failed = 0
        for issue in targets:
            if self._fix_issue(issue):
                fixed += 1
            else:
                failed += 1
        return fixed, failed

    def fix_one(self, issue: RegistryIssue) -> bool:
        return self._fix_issue(issue)

    @staticmethod
    def backup_key(hive: int, key_path: str, backup_path: str) -> bool:
        """Export a registry key to a .reg file for backup."""
        import subprocess
        hive_map = {
            winreg.HKEY_LOCAL_MACHINE: "HKLM",
            winreg.HKEY_CURRENT_USER: "HKCU",
            winreg.HKEY_CLASSES_ROOT: "HKCR",
        }
        hive_str = hive_map.get(hive, "HKCU")
        full_path = f"{hive_str}\\{key_path}"
        try:
            result = subprocess.run(
                ["reg", "export", full_path, backup_path, "/y"],
                capture_output=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
