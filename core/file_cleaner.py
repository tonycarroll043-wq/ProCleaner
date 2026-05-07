"""
File Cleaner - Scans and removes temporary, junk, and system cache files.
"""
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional


class FileCleaner:
    LOCATIONS: Dict[str, List[str]] = {
        "Windows Temp Files": [
            os.environ.get("TEMP", ""),
            os.environ.get("TMP", ""),
        ],
        "System Temp": [r"C:\Windows\Temp"],
        "Prefetch Files": [r"C:\Windows\Prefetch"],
        "Recent Documents": [
            str(Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent")
        ],
        "Windows Error Reports": [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "WER" / "ReportArchive"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "WER" / "ReportQueue"),
        ],
        "Thumbnail Cache": [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Explorer")
        ],
        "Windows Update Cache": [r"C:\Windows\SoftwareDistribution\Download"],
        "Memory Dump Files": [r"C:\Windows\Minidump"],
        "Old Chkdsk Files": [r"C:\$Recycle.Bin"],
        "Windows Log Files": [r"C:\Windows\Logs"],
        "IE / Edge Cache": [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "INetCache"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "WebCache"),
        ],
        "DirectX Shader Cache": [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "D3DSCache")
        ],
        "Delivery Optimization Files": [r"C:\Windows\ServiceProfiles\NetworkService\AppData\Local\Microsoft\Windows\DeliveryOptimization\Cache"],
        "Windows Defender Logs": [r"C:\ProgramData\Microsoft\Windows Defender\Scans\History"],
        "User Temporary Internet": [
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Temp")
        ],
    }

    def __init__(self):
        self.scan_results: Dict[str, Dict] = {}
        self.total_size: int = 0

    def scan(
        self,
        categories: Optional[List[str]] = None,
        progress_cb: Optional[Callable[[str, int], None]] = None,
    ) -> Dict[str, Dict]:
        self.scan_results = {}
        self.total_size = 0
        locations = (
            {k: v for k, v in self.LOCATIONS.items() if k in categories}
            if categories
            else self.LOCATIONS
        )
        for category, paths in locations.items():
            files: List[Tuple[str, int]] = []
            cat_size = 0
            for base in paths:
                if not base or not os.path.exists(base):
                    continue
                try:
                    if os.path.isfile(base):
                        sz = self._safe_size(base)
                        files.append((base, sz))
                        cat_size += sz
                    else:
                        for root, _dirs, filenames in os.walk(base):
                            for fname in filenames:
                                fp = os.path.join(root, fname)
                                sz = self._safe_size(fp)
                                if sz >= 0:
                                    files.append((fp, sz))
                                    cat_size += sz
                except (OSError, PermissionError):
                    pass
            self.scan_results[category] = {"files": files, "size": cat_size}
            self.total_size += cat_size
            if progress_cb:
                progress_cb(category, cat_size)
        return self.scan_results

    def clean(
        self,
        categories: Optional[List[str]] = None,
        progress_cb: Optional[Callable[[str, int], None]] = None,
    ) -> Tuple[int, int]:
        cleaned_count = 0
        cleaned_size = 0
        targets = (
            {k: v for k, v in self.scan_results.items() if k in categories}
            if categories
            else self.scan_results
        )
        for category, data in targets.items():
            for fp, sz in data["files"]:
                try:
                    if os.path.isfile(fp):
                        os.remove(fp)
                        cleaned_count += 1
                        cleaned_size += sz
                except (OSError, PermissionError):
                    pass
            if progress_cb:
                progress_cb(category, cleaned_size)
        return cleaned_count, cleaned_size

    @staticmethod
    def _safe_size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except (OSError, PermissionError):
            return -1

    @staticmethod
    def format_size(nbytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if nbytes < 1024:
                return f"{nbytes:.1f} {unit}"
            nbytes /= 1024
        return f"{nbytes:.1f} PB"

    @staticmethod
    def get_custom_locations() -> List[str]:
        """Returns extra per-user junk paths to scan."""
        appdata = os.environ.get("APPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        return [
            str(Path(appdata) / "Temp"),
            str(Path(local) / "Temp"),
            str(Path(local) / "Microsoft" / "Windows" / "Explorer" / "thumbcache_*.db"),
        ]
