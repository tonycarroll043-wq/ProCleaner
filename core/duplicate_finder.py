"""
Duplicate Finder - Finds duplicate files using MD5 hashing.
Groups identical files, shows total wasted space, lets user select which copies to delete.
"""
import os
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Callable, Optional
from collections import defaultdict


class DuplicateGroup:
    def __init__(self, file_hash: str, size: int, paths: List[str]):
        self.hash = file_hash
        self.size = size          # size of one file
        self.paths = paths        # all copies
        self.wasted = size * (len(paths) - 1)

    @property
    def count(self):
        return len(self.paths)


class DuplicateFinder:
    def __init__(self):
        self.groups: List[DuplicateGroup] = []
        self.total_wasted: int = 0
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def find(
        self,
        roots: List[str],
        min_size: int = 1024,          # ignore files smaller than 1 KB
        extensions: Optional[List[str]] = None,
        progress_cb: Optional[Callable[[str, int], None]] = None,
    ) -> List[DuplicateGroup]:
        self._cancelled = False
        self.groups = []
        self.total_wasted = 0

        # Step 1 – group by size (fast pre-filter)
        size_map: Dict[int, List[str]] = defaultdict(list)
        total_files = 0

        for root in roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                if self._cancelled:
                    return self.groups
                for fname in files:
                    fp = os.path.join(dirpath, fname)
                    if extensions:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in extensions:
                            continue
                    try:
                        sz = os.path.getsize(fp)
                        if sz >= min_size:
                            size_map[sz].append(fp)
                            total_files += 1
                    except (OSError, PermissionError):
                        pass

        # Step 2 – hash files that share a size
        candidates = {sz: paths for sz, paths in size_map.items() if len(paths) > 1}
        processed = 0

        hash_map: Dict[str, List[str]] = defaultdict(list)
        for sz, paths in candidates.items():
            if self._cancelled:
                break
            for fp in paths:
                if self._cancelled:
                    break
                file_hash = self._hash_file(fp)
                if file_hash:
                    hash_map[file_hash].append(fp)
                processed += 1
                if progress_cb:
                    progress_cb(fp, processed)

        # Step 3 – build groups
        for file_hash, paths in hash_map.items():
            if len(paths) > 1:
                sz = 0
                try:
                    sz = os.path.getsize(paths[0])
                except Exception:
                    pass
                grp = DuplicateGroup(file_hash, sz, paths)
                self.groups.append(grp)
                self.total_wasted += grp.wasted

        self.groups.sort(key=lambda g: g.wasted, reverse=True)
        return self.groups

    @staticmethod
    def _hash_file(path: str, block_size: int = 65536) -> Optional[str]:
        h = hashlib.md5()
        try:
            with open(path, "rb") as f:
                # Read first + last block for speed on large files
                buf = f.read(block_size)
                if not buf:
                    return None
                h.update(buf)
                f.seek(0, 2)
                file_size = f.tell()
                if file_size > block_size * 2:
                    f.seek(-block_size, 2)
                    h.update(f.read(block_size))
            return h.hexdigest()
        except (OSError, PermissionError):
            return None

    def delete_duplicates(
        self,
        paths_to_delete: List[str],
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Tuple[int, int]:
        deleted = 0
        freed = 0
        for fp in paths_to_delete:
            try:
                sz = os.path.getsize(fp)
                os.remove(fp)
                deleted += 1
                freed += sz
                if progress_cb:
                    progress_cb(fp)
            except (OSError, PermissionError):
                pass
        return deleted, freed

    @staticmethod
    def format_size(nbytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if nbytes < 1024:
                return f"{nbytes:.1f} {unit}"
            nbytes /= 1024
        return f"{nbytes:.1f} TB"
