"""
Disk Analyzer - Scans drives and directories, reports top large files/folders,
and provides per-extension breakdown.
"""
import os
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Callable, Optional
from collections import defaultdict


class DiskItem:
    def __init__(self, path: str, size: int, is_dir: bool):
        self.path = path
        self.size = size
        self.is_dir = is_dir
        self.name = os.path.basename(path) or path

    def __lt__(self, other):
        return self.size > other.size  # reverse sort by size


class DiskAnalyzer:
    def __init__(self):
        self.items: List[DiskItem] = []
        self.ext_breakdown: Dict[str, int] = {}
        self.total_scanned: int = 0

    # ------------------------------------------------------------------ #
    # Drive info
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_drives() -> List[Dict]:
        drives = []
        if sys.platform == "win32":
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                if bitmask & 1:
                    path = f"{letter}:\\"
                    try:
                        total, used, free = DiskAnalyzer._disk_usage(path)
                        drives.append({
                            "path": path,
                            "letter": letter,
                            "total": total,
                            "used": used,
                            "free": free,
                            "pct": round(used / total * 100, 1) if total else 0,
                        })
                    except Exception:
                        pass
                bitmask >>= 1
        else:
            try:
                total, used, free = DiskAnalyzer._disk_usage("/")
                drives.append({"path": "/", "letter": "/", "total": total, "used": used, "free": free,
                                "pct": round(used / total * 100, 1) if total else 0})
            except Exception:
                pass
        return drives

    @staticmethod
    def _disk_usage(path: str) -> Tuple[int, int, int]:
        import shutil as sh
        u = sh.disk_usage(path)
        return u.total, u.used, u.free

    # ------------------------------------------------------------------ #
    # Scan directory
    # ------------------------------------------------------------------ #
    def scan_directory(
        self,
        root: str,
        max_depth: int = 3,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> List[DiskItem]:
        self.items = []
        self.ext_breakdown = defaultdict(int)
        self.total_scanned = 0
        self._walk(root, 0, max_depth, progress_cb)
        self.items.sort()
        return self.items

    def _walk(self, path: str, depth: int, max_depth: int, cb):
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(path))
        except (PermissionError, OSError):
            return

        dir_size = 0
        for entry in entries:
            if cb and self.total_scanned % 500 == 0:
                cb(entry.path)
            try:
                if entry.is_file(follow_symlinks=False):
                    sz = entry.stat(follow_symlinks=False).st_size
                    dir_size += sz
                    self.total_scanned += 1
                    ext = os.path.splitext(entry.name)[1].lower() or "(no ext)"
                    self.ext_breakdown[ext] += sz
                    if depth <= 2:
                        self.items.append(DiskItem(entry.path, sz, False))
                elif entry.is_dir(follow_symlinks=False):
                    self._walk(entry.path, depth + 1, max_depth, cb)
            except (PermissionError, OSError):
                pass

    def get_top_files(self, n: int = 50) -> List[DiskItem]:
        return sorted([i for i in self.items if not i.is_dir], key=lambda x: x.size, reverse=True)[:n]

    def get_top_extensions(self, n: int = 20) -> List[Tuple[str, int]]:
        return sorted(self.ext_breakdown.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_file_type_summary(self) -> Dict[str, int]:
        """Group extensions into human-readable categories."""
        categories = {
            "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
            "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".svg", ".webp", ".raw"},
            "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
            "Documents": {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".rtf", ".odt"},
            "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
            "Executables": {".exe", ".msi", ".dll", ".sys", ".bat", ".cmd"},
            "Code": {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".h", ".cs", ".php"},
            "Databases": {".db", ".sqlite", ".mdf", ".ldf", ".accdb"},
        }
        result = defaultdict(int)
        for ext, size in self.ext_breakdown.items():
            placed = False
            for cat, exts in categories.items():
                if ext in exts:
                    result[cat] += size
                    placed = True
                    break
            if not placed:
                result["Other"] += size
        return dict(result)

    @staticmethod
    def format_size(nbytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if nbytes < 1024:
                return f"{nbytes:.1f} {unit}"
            nbytes /= 1024
        return f"{nbytes:.1f} PB"
