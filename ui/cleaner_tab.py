"""
Custom Cleaner Tab - System junk + browser cache cleaner with checkboxes,
real-time scan results, and animated progress.
"""
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QFrame,
    QSplitter, QScrollArea, QCheckBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor

from core.file_cleaner import FileCleaner
from core.browser_cleaner import BrowserCleaner, BROWSERS


class ScanWorker(QObject):
    progress = pyqtSignal(str, int)      # category, size
    finished = pyqtSignal(dict, dict)    # file_results, browser_results
    error    = pyqtSignal(str)

    def __init__(self, file_cleaner, browser_cleaner, checked_cats, checked_browsers):
        super().__init__()
        self.file_cleaner    = file_cleaner
        self.browser_cleaner = browser_cleaner
        self.checked_cats    = checked_cats
        self.checked_browsers = checked_browsers

    def run(self):
        try:
            file_results = self.file_cleaner.scan(
                categories=self.checked_cats if self.checked_cats else None,
                progress_cb=lambda cat, sz: self.progress.emit(cat, sz),
            )
            browser_results = {}
            if self.checked_browsers:
                browser_results = self.browser_cleaner.scan()
            self.finished.emit(file_results, browser_results)
        except Exception as e:
            self.error.emit(str(e))


class CleanWorker(QObject):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(int, int)
    error    = pyqtSignal(str)

    def __init__(self, file_cleaner, browser_cleaner, checked_cats, checked_browsers, browser_types):
        super().__init__()
        self.file_cleaner     = file_cleaner
        self.browser_cleaner  = browser_cleaner
        self.checked_cats     = checked_cats
        self.checked_browsers = checked_browsers
        self.browser_types    = browser_types

    def run(self):
        try:
            count, freed = self.file_cleaner.clean(
                categories=self.checked_cats if self.checked_cats else None,
                progress_cb=lambda cat, sz: self.progress.emit(cat, sz),
            )
            for browser in self.checked_browsers:
                bc, bf = self.browser_cleaner.clean(browser, self.browser_types)
                count += bc
                freed += bf
            self.finished.emit(count, freed)
        except Exception as e:
            self.error.emit(str(e))


class CustomCleanerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_cleaner    = FileCleaner()
        self.browser_cleaner = BrowserCleaner()
        self._scan_thread    = None
        self._clean_thread   = None
        self._cat_checks     = {}
        self._browser_checks = {}
        self._browser_type_checks = {}
        self._scan_done      = False
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Header
        header = self._make_header()
        main.addWidget(header)

        # Body: left checklist | right results
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #2a2d35; }")

        splitter.addWidget(self._make_left_panel())
        splitter.addWidget(self._make_right_panel())
        splitter.setSizes([320, 700])
        main.addWidget(splitter, 1)

        # Progress bar + status
        bottom = QWidget()
        bottom.setStyleSheet("background:#13151a; border-top:1px solid #2a2d35;")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(20, 8, 20, 8)
        bl.setSpacing(4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        bl.addWidget(self.progress_bar)

        self.status_label = QLabel("Select categories and click Scan to begin.")
        self.status_label.setStyleSheet("color:#6c7280; font-size:12px;")
        bl.addWidget(self.status_label)
        main.addWidget(bottom)

    def _make_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#1a1d23; border-bottom:1px solid #2a2d35;")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(24, 16, 24, 16)

        title_col = QVBoxLayout()
        title = QLabel("Custom Cleaner")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color:white;")
        subtitle = QLabel("Remove junk files, browser cache, temp data and free up disk space")
        subtitle.setStyleSheet("color:#6c7280; font-size:12px;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        hl.addLayout(title_col, 1)

        btn_row = QHBoxLayout()
        self.btn_analyze = QPushButton("  🔍  Analyze")
        self.btn_analyze.setObjectName("PrimaryButton")
        self.btn_analyze.setFixedHeight(38)
        self.btn_analyze.clicked.connect(self._start_scan)

        self.btn_clean = QPushButton("  🧹  Clean")
        self.btn_clean.setObjectName("SuccessButton")
        self.btn_clean.setFixedHeight(38)
        self.btn_clean.setEnabled(False)
        self.btn_clean.clicked.connect(self._start_clean)

        btn_row.addWidget(self.btn_analyze)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.btn_clean)
        hl.addLayout(btn_row)
        return w

    def _make_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:#1a1d23; }")

        container = QWidget()
        container.setStyleSheet("background:#1a1d23;")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(16)

        # ── Windows section ──
        win_label = QLabel("WINDOWS")
        win_label.setStyleSheet("color:#4fc3f7; font-size:11px; font-weight:bold; letter-spacing:2px;")
        vl.addWidget(win_label)

        for cat in FileCleaner.LOCATIONS:
            cb = QCheckBox(cat)
            cb.setChecked(True)
            cb.setStyleSheet("QCheckBox { padding: 3px 0; }")
            self._cat_checks[cat] = cb
            vl.addWidget(cb)

        vl.addSpacing(8)

        # Select all / none
        row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.setFixedHeight(28)
        btn_all.clicked.connect(lambda: self._set_all_cats(True))
        btn_none = QPushButton("Select None")
        btn_none.setFixedHeight(28)
        btn_none.clicked.connect(lambda: self._set_all_cats(False))
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        vl.addLayout(row)

        vl.addSpacing(16)
        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine); div.setStyleSheet("color:#2a2d35;")
        vl.addWidget(div)
        vl.addSpacing(8)

        # ── Browser section ──
        br_label = QLabel("BROWSERS")
        br_label.setStyleSheet("color:#4fc3f7; font-size:11px; font-weight:bold; letter-spacing:2px;")
        vl.addWidget(br_label)

        installed = BrowserCleaner.get_installed_browsers()
        for browser in BROWSERS:
            cb = QCheckBox(f"{'✓ ' if browser in installed else '✗ '}{browser}")
            cb.setChecked(browser in installed)
            cb.setEnabled(browser in installed)
            self._browser_checks[browser] = cb
            vl.addWidget(cb)

        vl.addSpacing(8)
        br2_label = QLabel("Browser data to clean:")
        br2_label.setStyleSheet("color:#888; font-size:12px;")
        vl.addWidget(br2_label)

        for btype, label in [("cache", "Cache"), ("history", "History"),
                              ("cookies", "Cookies"), ("other", "Other Data")]:
            cb = QCheckBox(label)
            cb.setChecked(btype in ("cache", "history"))
            cb.setStyleSheet("QCheckBox { padding-left:12px; }")
            self._browser_type_checks[btype] = cb
            vl.addWidget(cb)

        vl.addStretch()
        scroll.setWidget(container)
        return scroll

    def _make_right_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#1a1d23;")
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        # Summary row
        summary_row = QHBoxLayout()
        self.lbl_files   = self._stat_card("Files Found", "—")
        self.lbl_size    = self._stat_card("Total Size",  "—")
        self.lbl_freed   = self._stat_card("Last Freed",  "—")
        summary_row.addWidget(self.lbl_files[0])
        summary_row.addWidget(self.lbl_size[0])
        summary_row.addWidget(self.lbl_freed[0])
        vl.addLayout(summary_row)

        # Results tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Category", "Files", "Size"])
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 120)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setSortingEnabled(False)
        vl.addWidget(self.tree, 1)
        return w

    def _stat_card(self, title: str, value: str):
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet("""
            QFrame#Card { background:#21242c; border:1px solid #2a2d35;
                          border-radius:8px; padding:12px; }
        """)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet("color:#6c7280; font-size:11px; text-transform:uppercase; letter-spacing:1px;")
        v = QLabel(value)
        v.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        v.setStyleSheet("color:white;")
        cl.addWidget(t)
        cl.addWidget(v)
        return card, v  # return card widget + value label

    # ------------------------------------------------------------------ #
    # Scan
    # ------------------------------------------------------------------ #
    def _start_scan(self):
        self.tree.clear()
        self.btn_analyze.setEnabled(False)
        self.btn_clean.setEnabled(False)
        self._scan_done = False
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Scanning…")

        checked_cats    = [c for c, cb in self._cat_checks.items() if cb.isChecked()]
        checked_browsers = [b for b, cb in self._browser_checks.items() if cb.isChecked()]

        self._scan_thread = QThread()
        self._worker = ScanWorker(self.file_cleaner, self.browser_cleaner, checked_cats, checked_browsers)
        self._worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._scan_thread.quit)
        self._scan_thread.start()

    def _on_scan_progress(self, category: str, size: int):
        self.status_label.setText(f"Scanning: {category}…")

    def _on_scan_done(self, file_results: dict, browser_results: dict):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.btn_analyze.setEnabled(True)
        self._scan_done = True

        total_files = 0
        total_size  = 0

        # ── Windows junk ──
        win_root = QTreeWidgetItem(self.tree, ["🖥  Windows Junk", "", ""])
        win_root.setFont(0, QFont("Segoe UI", 12, QFont.Weight.Bold))
        for cat, data in file_results.items():
            n = len(data["files"])
            sz = data["size"]
            if n == 0:
                continue
            item = QTreeWidgetItem(win_root, [cat, str(n), FileCleaner.format_size(sz)])
            item.setForeground(2, QColor("#4fc3f7"))
            total_files += n
            total_size  += sz
        win_root.setExpanded(True)

        # ── Browser ──
        if browser_results:
            br_root = QTreeWidgetItem(self.tree, ["🌐  Browser Data", "", ""])
            br_root.setFont(0, QFont("Segoe UI", 12, QFont.Weight.Bold))
            for browser, data in browser_results.items():
                for dtype, ddata in data.items():
                    n  = len(ddata["files"])
                    sz = ddata["size"]
                    if n == 0:
                        continue
                    item = QTreeWidgetItem(br_root, [f"{browser} – {dtype.title()}", str(n),
                                                     FileCleaner.format_size(sz)])
                    item.setForeground(2, QColor("#4fc3f7"))
                    total_files += n
                    total_size  += sz
            br_root.setExpanded(True)

        self.lbl_files[1].setText(f"{total_files:,}")
        self.lbl_size[1].setText(FileCleaner.format_size(total_size))
        self.status_label.setText(
            f"Analysis complete — found {total_files:,} files totalling {FileCleaner.format_size(total_size)}"
        )
        if total_files > 0:
            self.btn_clean.setEnabled(True)

    # ------------------------------------------------------------------ #
    # Clean
    # ------------------------------------------------------------------ #
    def _start_clean(self):
        self.btn_clean.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Cleaning…")

        checked_cats     = [c for c, cb in self._cat_checks.items() if cb.isChecked()]
        checked_browsers = [b for b, cb in self._browser_checks.items() if cb.isChecked()]
        browser_types    = [t for t, cb in self._browser_type_checks.items() if cb.isChecked()]

        self._clean_thread = QThread()
        self._clean_worker = CleanWorker(
            self.file_cleaner, self.browser_cleaner,
            checked_cats, checked_browsers, browser_types
        )
        self._clean_worker.moveToThread(self._clean_thread)
        self._clean_thread.started.connect(self._clean_worker.run)
        self._clean_worker.progress.connect(lambda c, s: self.status_label.setText(f"Cleaning {c}…"))
        self._clean_worker.finished.connect(self._on_clean_done)
        self._clean_worker.error.connect(self._on_error)
        self._clean_worker.finished.connect(self._clean_thread.quit)
        self._clean_thread.start()

    def _on_clean_done(self, count: int, freed: int):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.btn_analyze.setEnabled(True)
        self.lbl_freed[1].setText(FileCleaner.format_size(freed))
        self.status_label.setText(
            f"✓  Clean complete — removed {count:,} files, freed {FileCleaner.format_size(freed)}"
        )
        self.tree.clear()
        self._scan_done = False

    def _on_error(self, msg: str):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"Error: {msg}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _set_all_cats(self, state: bool):
        for cb in self._cat_checks.values():
            cb.setChecked(state)
