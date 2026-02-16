#!/usr/bin/env python3
#
# Fixlet Debugger for Linux
# Copyright (C) 2026 Mike Consuegra
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
"""
Fixlet Debugger for Linux
A GUI wrapper for the BigFix qna command-line tool.
Provides similar functionality to the Windows Fixlet Debugger.

Version 1.1.0 - Added Single Clause mode, type information, pkexec support,
                multi-tab system.
Version 1.2.0 - Added unsaved changes detection with save prompts.
Version 1.2.1 - Package cleanup, removed leftover files from previous versions.
"""

import sys
import subprocess
import time
import os
import re
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPlainTextEdit, QPushButton, QLabel, QStatusBar,
    QMenuBar, QMenu, QAction, QFileDialog, QMessageBox,
    QToolBar, QTabBar, QFrame, QStackedWidget, QSplitter
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRegExp, QSize, QPointF
from PyQt5.QtGui import (
    QFont, QTextCursor, QColor, QSyntaxHighlighter, QTextCharFormat,
    QKeySequence, QTextDocument, QIcon, QPainter, QPixmap, QPen, QBrush,
    QPolygonF, QLinearGradient
)


class QnAHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for the QnA pane - matches Windows Fixlet Debugger colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        # Keywords - Blue foreground (relevance language keywords)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#0000FF"))  # Blue
        keywords = [
            r'\bif\b', r'\bthen\b', r'\belse\b', r'\bof\b', r'\bwhose\b',
            r'\bwhere\b', r'\bas\b', r'\bexists\b', r'\bnot\b', r'\band\b',
            r'\bor\b', r'\bcontains\b', r'\bstarts\s+with\b', r'\bends\s+with\b',
            r'\bequals\b', r'\bmod\b', r'\ba\b', r'\ban\b', r'\bthe\b',
            r'\bnumber\b', r'\bstring\b', r'\bboolean\b', r'\binteger\b',
            r'\btrue\b', r'\bfalse\b', r'\brelative\b', r'\babsolute\b',
        ]
        for kw in keywords:
            self.highlighting_rules.append((kw, keyword_format))

        # Operators - Blue foreground
        operator_format = QTextCharFormat()
        operator_format.setForeground(QColor("#0000FF"))  # Blue
        operators = [
            r'\+', r'-', r'\*', r'/', r'=', r'!=', r'<', r'>', r'<=', r'>=',
            r'\|', r'&',
        ]
        for op in operators:
            self.highlighting_rules.append((op, operator_format))

        # Strings - Teal foreground (text in quotes)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#008080"))  # Teal
        self.highlighting_rules.append((r'"[^"]*"', string_format))
        self.highlighting_rules.append((r"'[^']*'", string_format))

        # Constants/Numbers - Purple foreground
        constant_format = QTextCharFormat()
        constant_format.setForeground(QColor("#800080"))  # Purple
        self.highlighting_rules.append((r'\b\d+\.?\d*\b', constant_format))

        # Comments - Green foreground (// style comments)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#008000"))  # Green
        self.highlighting_rules.append((r'//.*$', comment_format))

        # Block comments - Green foreground (/* */ style comments)
        self.highlighting_rules.append((r'/\*.*\*/', comment_format))

        # Note: "it" keyword highlighting is handled dynamically by highlight_it_references()
        # to show red when unmatched and green when matched

        # Q: keyword - Red foreground
        q_format = QTextCharFormat()
        q_format.setForeground(QColor("#FF0000"))  # Red
        self.highlighting_rules.append((r'^Q:', q_format))

        # A: keyword - Red foreground
        a_format = QTextCharFormat()
        a_format.setForeground(QColor("#FF0000"))  # Red
        self.highlighting_rules.append((r'^A:', a_format))

        # E: lines - White on Red background (error/illegal)
        e_format = QTextCharFormat()
        e_format.setForeground(QColor("#FFFFFF"))  # White
        e_format.setBackground(QColor("#FF0000"))  # Red
        self.highlighting_rules.append((r'^E:.*$', e_format))

        # T: prefix - Red foreground (matching Q: and A:), value stays black
        t_format = QTextCharFormat()
        t_format.setForeground(QColor("#FF0000"))  # Red
        self.highlighting_rules.append((r'^T:', t_format))

        # I: prefix - Red foreground (matching Q: and A:), value stays black
        i_format = QTextCharFormat()
        i_format.setForeground(QColor("#FF0000"))  # Red
        self.highlighting_rules.append((r'^I:', i_format))

    def highlightBlock(self, text):
        # Apply standard rules first
        for pattern, fmt in self.highlighting_rules:
            expression = QRegExp(pattern)
            expression.setCaseSensitivity(Qt.CaseInsensitive)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, fmt)
                index = expression.indexIn(text, index + length)

        # Handle multi-line block comments /* */
        self.setCurrentBlockState(0)

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#008000"))  # Green

        start_expression = QRegExp(r'/\*')
        end_expression = QRegExp(r'\*/')

        # If previous block was in a comment, start from beginning
        if self.previousBlockState() == 1:
            start_index = 0
            end_index = end_expression.indexIn(text, 0)

            if end_index == -1:
                # Still in comment, whole line is comment
                self.setCurrentBlockState(1)
                self.setFormat(0, len(text), comment_format)
            else:
                # Comment ends on this line
                comment_length = end_index + end_expression.matchedLength()
                self.setFormat(0, comment_length, comment_format)
                # Look for new comment starts after this
                start_index = start_expression.indexIn(text, comment_length)
        else:
            start_index = start_expression.indexIn(text)

        # Process any comment starts on this line
        while start_index >= 0:
            end_index = end_expression.indexIn(text, start_index + 2)

            if end_index == -1:
                # Comment continues to next line
                self.setCurrentBlockState(1)
                comment_length = len(text) - start_index
            else:
                # Comment ends on this line
                comment_length = end_index - start_index + end_expression.matchedLength()

            self.setFormat(start_index, comment_length, comment_format)
            start_index = start_expression.indexIn(text, start_index + comment_length)


class QnAWorker(QThread):
    """Worker thread to run qna evaluations without blocking the UI."""

    finished = pyqtSignal(str, float)
    error = pyqtSignal(str)

    def __init__(self, qna_path, query, worker_id=0, show_types=True):
        super().__init__()
        self.qna_path = qna_path
        self.query = query
        self.worker_id = worker_id
        self._is_cancelled = False
        self.show_types = show_types

    def cancel(self):
        """Signal the thread to cancel."""
        self._is_cancelled = True

    def run(self):
        try:
            start_time = time.perf_counter()

            # Clean the query - remove Q: prefix if present
            query = self.query.strip()
            if query.upper().startswith('Q:'):
                query = query[2:].strip()

            if not query:
                if not self._is_cancelled:
                    self.error.emit("No query to evaluate")
                return

            # Build command with optional -showtypes flag
            cmd = [self.qna_path]
            if self.show_types:
                cmd.append('-showtypes')

            # Run qna
            result = subprocess.run(
                cmd,
                input=query + '\n',
                capture_output=True,
                text=True,
                timeout=30
            )

            # Check if cancelled before emitting
            if self._is_cancelled:
                return

            elapsed_time = (time.perf_counter() - start_time) * 1000

            stdout = result.stdout

            # Parse the output - qna returns "Q: A: answer" or "Q: E: error" format
            lines = stdout.strip().split('\n')
            formatted_lines = []

            for line in lines:
                line = line.rstrip()
                if not line or line == 'Q:' or line == 'Q: ':
                    continue

                # Handle "Q: A: answer" format
                if line.startswith('Q:') and ' A:' in line:
                    answer = line.split('A:', 1)[1].strip()
                    formatted_lines.append(f"A: {answer}")
                # Handle "Q: E: error" format
                elif line.startswith('Q:') and ' E:' in line:
                    error = line.split('E:', 1)[1].strip()
                    formatted_lines.append(f"E: {error}")
                # Handle T: line (convert microseconds to ms)
                elif line.startswith('T:'):
                    try:
                        time_val = line.replace('T:', '').strip()
                        if time_val.isdigit():
                            time_ms = int(time_val) / 1000.0
                            formatted_lines.append(f"T: {time_ms:.3f} ms")
                        else:
                            formatted_lines.append(line)
                    except:
                        formatted_lines.append(line)
                # Pass through other lines (A:, E:, I:)
                elif line.startswith(('A:', 'E:', 'I:')):
                    formatted_lines.append(line)

            # Check again before emitting
            if self._is_cancelled:
                return

            output = '\n'.join(formatted_lines)
            self.finished.emit(output, elapsed_time)

        except subprocess.TimeoutExpired:
            if not self._is_cancelled:
                self.error.emit("Evaluation timed out after 30 seconds")
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(f"Exception: {str(e)}")


class TabInfo:
    """Holds per-tab state for the multi-tab system."""

    def __init__(self, tab_type, page_widget, input_pane, output_pane=None):
        self.tab_type = tab_type        # "qna" or "sc"
        self.page_widget = page_widget  # QWidget in stacked widget
        self.input_pane = input_pane    # QTextEdit (editable)
        self.output_pane = output_pane  # QTextEdit (SC output, read-only); None for QnA
        self.current_file = None        # Per-tab file path
        self.highlighters = []          # List of QnAHighlighter instances
        self.is_dirty = False           # Unsaved changes flag
        self._saved_content = ""        # Snapshot of content at last save/open


class FixletDebugger(QMainWindow):
    """Main window for the Fixlet Debugger application."""

    DEFAULT_QNA_PATH = "/opt/BESClient/bin/qna"

    def __init__(self):
        super().__init__()
        self.qna_path = self.DEFAULT_QNA_PATH
        self.worker = None
        self.pending_queries = []
        self.current_query_index = 0
        self.current_line_num = 0
        self.worker_counter = 0
        self.total_elapsed_time = 0
        self.tab_data = {}          # page_widget -> TabInfo
        self.evaluating_tab = None  # TabInfo locked during evaluation
        self.current_font_size = 10
        self._suppress_dirty = False  # Suppress dirty tracking during programmatic changes

        self.init_ui()
        self.check_qna_binary()

    def _get_active_tab(self):
        """Return TabInfo for the currently visible tab."""
        widget = self.stacked_widget.currentWidget()
        return self.tab_data.get(widget)

    def _get_active_input_pane(self):
        """Return the currently active input pane."""
        tab = self._get_active_tab()
        return tab.input_pane if tab else None

    def _create_play_icon(self, size=24):
        """Create a green play (right-pointing triangle) icon."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#4CAF50")))
        painter.setPen(Qt.NoPen)
        triangle = QPolygonF([
            QPointF(size * 0.18, size * 0.1),
            QPointF(size * 0.18, size * 0.9),
            QPointF(size * 0.88, size * 0.5)
        ])
        painter.drawPolygon(triangle)
        painter.end()
        return QIcon(pixmap)

    def _create_format_icon(self, size=24):
        """Create a format/indent icon (vertical bar with indented horizontal lines)."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#444444"), max(1.5, size / 14))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        # Vertical bar on left
        bx = int(size * 0.15)
        painter.drawLine(bx, int(size * 0.08), bx, int(size * 0.92))
        # Horizontal lines at varying indentation levels
        for xs, y, xe in [(0.28, 0.20, 0.92), (0.42, 0.40, 0.92),
                          (0.42, 0.60, 0.92), (0.28, 0.80, 0.92)]:
            painter.drawLine(int(size * xs), int(size * y),
                             int(size * xe), int(size * y))
        # Right-pointing arrow from bar to indented line
        ay = int(size * 0.40)
        painter.drawLine(bx + 2, ay, int(size * 0.36), ay)
        hs = max(2, int(size * 0.10))
        tip = int(size * 0.36)
        painter.drawLine(tip, ay, tip - hs, ay - hs)
        painter.drawLine(tip, ay, tip - hs, ay + hs)
        painter.end()
        return QIcon(pixmap)

    def _create_plus_icon(self, size=24):
        """Create a bold blue '+' icon for the new-tab button."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#1976D2"), max(3.0, size / 7))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        mid = size // 2
        margin = int(size * 0.18)
        painter.drawLine(mid, margin, mid, size - margin)      # vertical
        painter.drawLine(margin, mid, size - margin, mid)       # horizontal
        painter.end()
        return QIcon(pixmap)

    def _create_app_icon(self):
        """Create the application icon programmatically for window/taskbar."""
        icon = QIcon()
        for size in [16, 24, 32, 48, 64, 128]:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            # Blue gradient rounded rectangle
            gradient = QLinearGradient(0, 0, 0, size)
            gradient.setColorAt(0, QColor("#42A5F5"))
            gradient.setColorAt(1, QColor("#1976D2"))
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            r = size * 0.18
            painter.drawRoundedRect(1, 1, size - 2, size - 2, r, r)
            # "Q:" text — Q in red, colon in white
            font = QFont("Courier New", max(7, int(size * 0.45)), QFont.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            q_width = fm.horizontalAdvance("Q") if hasattr(fm, 'horizontalAdvance') else fm.width("Q")
            total_width = fm.horizontalAdvance("Q:") if hasattr(fm, 'horizontalAdvance') else fm.width("Q:")
            x_start = (size - total_width) // 2
            y_pos = (size + fm.ascent() - fm.descent()) // 2
            painter.setPen(QPen(QColor("#FF0000")))
            painter.drawText(x_start, y_pos, "Q")
            painter.setPen(QPen(Qt.white))
            painter.drawText(x_start + q_width, y_pos, ":")
            painter.end()
            icon.addPixmap(pixmap)
        return icon

    def _create_qna_page(self):
        """Factory: create a QnA tab page with header and text pane."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel(" QnA")
        header.setStyleSheet("""
            background-color: #4a6ea5;
            color: white;
            padding: 3px 5px;
            font-weight: bold;
        """)
        layout.addWidget(header)

        text_pane = QTextEdit()
        text_pane.setFont(QFont("Monospace", self.current_font_size))
        text_pane.setAcceptRichText(False)
        text_pane.setPlaceholderText(
            "Relevance expressions should begin with a 'Q:'"
        )
        layout.addWidget(text_pane)

        highlighter = QnAHighlighter(text_pane.document())

        # Connect signals
        text_pane.cursorPositionChanged.connect(self.update_cursor_position)
        text_pane.cursorPositionChanged.connect(self.highlight_matching_brackets)
        text_pane.textChanged.connect(self.on_text_changed)
        text_pane.installEventFilter(self)

        return page, text_pane, None, [highlighter]

    def _create_sc_page(self):
        """Factory: create a Single Clause tab page with relevance + output panes."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Vertical)

        # Top: Relevance input pane
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        rel_header = QLabel(" Relevance")
        rel_header.setStyleSheet("""
            background-color: #4a6ea5;
            color: white;
            padding: 3px 5px;
            font-weight: bold;
        """)
        top_layout.addWidget(rel_header)

        relevance_pane = QTextEdit()
        relevance_pane.setFont(QFont("Monospace", self.current_font_size))
        relevance_pane.setAcceptRichText(False)
        relevance_pane.setPlaceholderText(
            "Type a single relevance expression here (no Q: prefix needed)."
        )
        top_layout.addWidget(relevance_pane)

        highlighter1 = QnAHighlighter(relevance_pane.document())

        splitter.addWidget(top_container)

        # Bottom: Output pane
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        output_header = QLabel(" Output")
        output_header.setStyleSheet("""
            background-color: #4a6ea5;
            color: white;
            padding: 3px 5px;
            font-weight: bold;
        """)
        bottom_layout.addWidget(output_header)

        output_pane = QTextEdit()
        output_pane.setFont(QFont("Monospace", self.current_font_size))
        output_pane.setReadOnly(True)
        output_pane.setPlaceholderText("Results will appear here after evaluation.")
        bottom_layout.addWidget(output_pane)

        highlighter2 = QnAHighlighter(output_pane.document())

        splitter.addWidget(bottom_container)
        splitter.setSizes([420, 280])

        layout.addWidget(splitter)

        # Connect signals
        relevance_pane.cursorPositionChanged.connect(self.update_cursor_position)
        relevance_pane.cursorPositionChanged.connect(self.highlight_matching_brackets)
        relevance_pane.textChanged.connect(self.on_text_changed)
        relevance_pane.installEventFilter(self)

        return page, relevance_pane, output_pane, [highlighter1, highlighter2]

    def _add_tab(self, tab_type):
        """Create a new tab of the given type and switch to it."""
        if tab_type == "qna":
            page, input_pane, output_pane, highlighters = self._create_qna_page()
            label = "(qna)*"
        else:
            page, input_pane, output_pane, highlighters = self._create_sc_page()
            label = "(single clause)"

        self.tab_bar.blockSignals(True)

        self.stacked_widget.addWidget(page)
        tab_index = self.tab_bar.addTab(label)

        info = TabInfo(tab_type, page, input_pane, output_pane)
        info.highlighters = highlighters
        self.tab_data[page] = info

        self.tab_bar.blockSignals(False)

        # Switch to the new tab (fires _on_tab_changed which syncs stacked_widget)
        self.tab_bar.setCurrentIndex(tab_index)

        self._update_tab_close_buttons()
        self._update_window_title()

        input_pane.setFocus()

    def _on_tab_changed(self, index):
        """Handle tab bar selection change."""
        if 0 <= index < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(index)
        self._update_window_title()
        # Focus the new tab's input pane
        tab = self._get_active_tab()
        if tab:
            tab.input_pane.setFocus()

    def _on_tab_close_requested(self, index):
        """Handle tab close request. Prevent closing the last tab."""
        if self.tab_bar.count() <= 1:
            return

        page = self.stacked_widget.widget(index)
        info = self.tab_data.get(page)

        # Check for unsaved changes before closing
        if info is not None and info.is_dirty:
            if not self._prompt_save_changes(info):
                return

        # If this tab is being evaluated, stop the evaluation
        if info is not None and info is self.evaluating_tab:
            self.stop_evaluation()

        self.tab_bar.blockSignals(True)

        self.tab_bar.removeTab(index)
        self.stacked_widget.removeWidget(page)

        if page in self.tab_data:
            del self.tab_data[page]

        page.deleteLater()

        self.tab_bar.blockSignals(False)

        # Sync to current tab
        new_index = self.tab_bar.currentIndex()
        if 0 <= new_index < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(new_index)

        self._update_tab_close_buttons()
        self._update_window_title()

    def _update_tab_close_buttons(self):
        """Show close buttons only when more than one tab exists."""
        self.tab_bar.setTabsClosable(self.tab_bar.count() > 1)

    def _update_window_title(self):
        """Update window title from the active tab's type, file, and dirty state."""
        tab = self._get_active_tab()
        if tab is None:
            self.setWindowTitle("Fixlet Debugger")
            return

        if tab.tab_type == "qna":
            prefix = "(qna)*"
        else:
            prefix = "(single clause)"

        title = f"{prefix} - Fixlet Debugger"
        if tab.current_file:
            title += f" - {os.path.basename(tab.current_file)}"
        if tab.is_dirty:
            title += " [modified]"
        self.setWindowTitle(title)

    def _update_tab_label(self, info):
        """Update the tab bar label for the given tab, adding indicator if dirty."""
        for i in range(self.stacked_widget.count()):
            if self.stacked_widget.widget(i) is info.page_widget:
                if info.tab_type == "qna":
                    base_label = "(qna)*"
                else:
                    base_label = "(single clause)"
                if info.is_dirty:
                    label = base_label + " [modified]"
                else:
                    label = base_label
                self.tab_bar.setTabText(i, label)
                break

    def _mark_tab_clean(self, tab):
        """Mark a tab as clean (saved) and update visual indicators."""
        tab.is_dirty = False
        tab._saved_content = tab.input_pane.toPlainText()
        self._update_tab_label(tab)
        self._update_window_title()

    def _prompt_save_changes(self, tab):
        """Prompt user to save unsaved changes. Returns True to proceed, False to cancel."""
        if not tab.is_dirty:
            return True

        if tab.tab_type == "qna":
            tab_desc = "QnA tab"
        else:
            tab_desc = "Single Clause tab"

        if tab.current_file:
            msg = f"The {tab_desc} ({os.path.basename(tab.current_file)}) has unsaved changes."
        else:
            msg = f"The {tab_desc} has unsaved changes."

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            f"{msg}\n\nDo you want to save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save
        )

        if reply == QMessageBox.Save:
            self._save_specific_tab(tab)
            return True
        elif reply == QMessageBox.Discard:
            return True
        else:
            return False

    def _save_specific_tab(self, tab):
        """Save a specific tab's content (may not be the active tab)."""
        if tab.current_file:
            try:
                with open(tab.current_file, 'w') as f:
                    f.write(tab.input_pane.toPlainText())
                self._mark_tab_clean(tab)
                self.status_bar.showMessage(f"Saved: {tab.current_file}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
        else:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Relevance File",
                "", "QnA Files (*.qna);;Relevance Files (*.rel);;Text Files (*.txt);;All Files (*)"
            )
            if filename:
                try:
                    with open(filename, 'w') as f:
                        f.write(tab.input_pane.toPlainText())
                    tab.current_file = filename
                    self._mark_tab_clean(tab)
                    self._update_window_title()
                    self.status_bar.showMessage(f"Saved: {filename}", 3000)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")

    def _apply_font_to_all_panes(self):
        """Apply current font size to all panes across all tabs."""
        font = QFont("Monospace", self.current_font_size)
        for info in self.tab_data.values():
            info.input_pane.setFont(font)
            if info.output_pane:
                info.output_pane.setFont(font)

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("(qna)* - Fixlet Debugger")
        self.setGeometry(100, 100, 900, 700)

        # Set window/taskbar icon
        self.setWindowIcon(self._create_app_icon())

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Tab bar and controls row
        mode_layout = QHBoxLayout()

        # Tab bar
        self.tab_bar = QTabBar()
        self.tab_bar.setMovable(False)
        self.tab_bar.setTabsClosable(False)  # Updated by _update_tab_close_buttons

        # Create red X icons for tab close buttons
        self._close_icon_path = os.path.join(
            os.environ.get('TMPDIR', '/tmp'), 'fixlet-debugger-close.png')
        self._close_hover_path = os.path.join(
            os.environ.get('TMPDIR', '/tmp'), 'fixlet-debugger-close-hover.png')
        for path, color, width in [
            (self._close_icon_path, QColor("#CC0000"), 1.8),
            (self._close_hover_path, QColor("#FF0000"), 2.2),
        ]:
            px = QPixmap(16, 16)
            px.fill(Qt.transparent)
            p = QPainter(px)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(4, 4, 12, 12)
            p.drawLine(12, 4, 4, 12)
            p.end()
            px.save(path)
        self.tab_bar.setStyleSheet(f"""
            QTabBar::close-button {{
                image: url({self._close_icon_path});
                subcontrol-position: right;
                padding: 2px;
            }}
            QTabBar::close-button:hover {{
                image: url({self._close_hover_path});
                background: rgba(255, 80, 80, 30);
                border-radius: 3px;
            }}
        """)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        mode_layout.addWidget(self.tab_bar)

        # Separator between tab bar and action buttons
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setFixedHeight(24)
        mode_layout.addWidget(separator)

        # "+" button for new tab (with programmatic icon)
        self.new_tab_btn = QPushButton()
        self.new_tab_btn.setIcon(self._create_plus_icon())
        self.new_tab_btn.setIconSize(QSize(20, 20))
        self.new_tab_btn.setFixedSize(30, 30)
        self.new_tab_btn.setToolTip("New Tab")
        self.new_tab_btn.setFlat(True)
        self.new_tab_btn.setCursor(Qt.PointingHandCursor)
        new_tab_menu = QMenu(self.new_tab_btn)
        new_tab_menu.addAction("New QnA Tab", lambda: self._add_tab("qna"))
        new_tab_menu.addAction("New Single Clause Tab", lambda: self._add_tab("sc"))
        self.new_tab_btn.setMenu(new_tab_menu)
        mode_layout.addWidget(self.new_tab_btn)

        # Evaluate button (green play triangle)
        self.eval_mode_btn = QPushButton()
        self.eval_mode_btn.setIcon(self._create_play_icon())
        self.eval_mode_btn.setIconSize(QSize(20, 20))
        self.eval_mode_btn.setFixedSize(30, 30)
        self.eval_mode_btn.setToolTip("Evaluate (F5)")
        self.eval_mode_btn.setFlat(True)
        self.eval_mode_btn.setCursor(Qt.PointingHandCursor)
        self.eval_mode_btn.clicked.connect(self.evaluate)
        mode_layout.addWidget(self.eval_mode_btn)

        # Format button (indent icon)
        self.format_mode_btn = QPushButton()
        self.format_mode_btn.setIcon(self._create_format_icon())
        self.format_mode_btn.setIconSize(QSize(20, 20))
        self.format_mode_btn.setFixedSize(30, 30)
        self.format_mode_btn.setToolTip("Expand Relevance")
        self.format_mode_btn.setFlat(True)
        self.format_mode_btn.setCursor(Qt.PointingHandCursor)
        self.format_mode_btn.clicked.connect(self.format_expression)
        mode_layout.addWidget(self.format_mode_btn)

        mode_layout.addStretch()
        main_layout.addLayout(mode_layout)

        # Stacked widget for tab pages (dynamically managed)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Button row
        button_layout = QHBoxLayout()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_all)
        button_layout.addWidget(self.clear_btn)

        button_layout.addStretch()

        self.evaluate_btn = QPushButton("Evaluate")
        self.evaluate_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a6ea5;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #5a7eb5;
            }
            QPushButton:pressed {
                background-color: #3a5e95;
            }
        """)
        self.evaluate_btn.clicked.connect(self.evaluate)
        button_layout.addWidget(self.evaluate_btn)

        main_layout.addLayout(button_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.line_label = QLabel("Line: 1")
        self.char_label = QLabel("Char: 0")
        self.zoom_label = QLabel("Zoom: 10pt")
        self.time_label = QLabel("Evaluation time: -")
        self.qna_status_label = QLabel("Local Fixlet Debugger")

        self.status_bar.addWidget(self.line_label)
        self.status_bar.addWidget(self.char_label)
        self.status_bar.addWidget(self.zoom_label)
        self.status_bar.addWidget(self.time_label)
        self.status_bar.addPermanentWidget(self.qna_status_label)

        # Create menu bar and toolbar
        self.create_menu_bar()
        self.create_toolbar()

        # Create the initial QnA tab
        self._add_tab("qna")

    def eventFilter(self, obj, event):
        """Handle keyboard events for shortcuts."""
        from PyQt5.QtCore import QEvent
        is_input_pane = any(obj is info.input_pane for info in self.tab_data.values())
        if is_input_pane and event.type() == QEvent.KeyPress:
            # F5 to evaluate
            if event.key() == Qt.Key_F5:
                self.evaluate()
                return True
            # Ctrl+Enter to evaluate
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self.evaluate()
                return True
            # Ctrl+R to remove results (A:, T:, E:, I: lines) - QnA tabs only
            if event.key() == Qt.Key_R and event.modifiers() == Qt.ControlModifier:
                self.remove_results()
                return True
            # Ctrl++ or Ctrl+= to zoom in
            if event.key() in (Qt.Key_Plus, Qt.Key_Equal) and event.modifiers() == Qt.ControlModifier:
                self.zoom_in()
                return True
            # Ctrl+- to zoom out
            if event.key() == Qt.Key_Minus and event.modifiers() == Qt.ControlModifier:
                self.zoom_out()
                return True
            # Ctrl+0 to reset zoom
            if event.key() == Qt.Key_0 and event.modifiers() == Qt.ControlModifier:
                self.zoom_reset()
                return True
            # Ctrl+Shift+F to expand/compact expression (Single Clause tabs only)
            if event.key() == Qt.Key_F and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
                self.format_expression()
                return True
        # Handle mouse wheel zoom with Ctrl
        if is_input_pane and event.type() == QEvent.Wheel:
            if event.modifiers() == Qt.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.zoom_in()
                else:
                    self.zoom_out()
                return True
        return super().eventFilter(obj, event)

    def create_menu_bar(self):
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(lambda: self._get_active_input_pane().undo())
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(lambda: self._get_active_input_pane().redo())
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(lambda: self._get_active_input_pane().cut())
        edit_menu.addAction(cut_action)

        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(lambda: self._get_active_input_pane().copy())
        edit_menu.addAction(copy_action)

        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(lambda: self._get_active_input_pane().paste())
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()

        select_all_action = QAction("Select &All", self)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(lambda: self._get_active_input_pane().selectAll())
        edit_menu.addAction(select_all_action)

        edit_menu.addSeparator()

        remove_results_action = QAction("&Remove Results", self)
        remove_results_action.setShortcut("Ctrl+R")
        remove_results_action.triggered.connect(self.remove_results)
        edit_menu.addAction(remove_results_action)

        format_action = QAction("&Expand/Compact Relevance", self)
        format_action.setShortcut("Ctrl+Shift+F")
        format_action.triggered.connect(self.format_expression)
        edit_menu.addAction(format_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)

        zoom_reset_action = QAction("&Reset Zoom", self)
        zoom_reset_action.setShortcut("Ctrl+0")
        zoom_reset_action.triggered.connect(self.zoom_reset)
        view_menu.addAction(zoom_reset_action)

        # Evaluate menu
        eval_menu = menubar.addMenu("E&valuate")

        eval_action = QAction("&Evaluate (F5 or Ctrl+Enter)", self)
        eval_action.setShortcut("F5")
        eval_action.triggered.connect(self.evaluate)
        eval_menu.addAction(eval_action)

        eval_menu.addSeparator()

        stop_action = QAction("&Stop", self)
        stop_action.setShortcut("Escape")
        stop_action.triggered.connect(self.stop_evaluation)
        eval_menu.addAction(stop_action)

        # Settings menu
        settings_menu = menubar.addMenu("&Settings")

        qna_path_action = QAction("Set &QnA Path...", self)
        qna_path_action.triggered.connect(self.set_qna_path)
        settings_menu.addAction(qna_path_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        help_action = QAction("&Relevance Reference", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

    def create_toolbar(self):
        """Create the toolbar."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        new_action = QAction("New", self)
        new_action.triggered.connect(self.new_file)
        toolbar.addAction(new_action)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_file)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        stop_action = QAction("Stop", self)
        stop_action.triggered.connect(self.stop_evaluation)
        toolbar.addAction(stop_action)

        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.clear_all)
        toolbar.addAction(clear_action)

    def check_qna_binary(self):
        """Check if the qna binary exists and is accessible."""
        if os.path.exists(self.qna_path):
            if os.access(self.qna_path, os.X_OK):
                self.qna_status_label.setText("Local Fixlet Debugger")
                self.qna_status_label.setStyleSheet("color: black;")
            else:
                self.qna_status_label.setText("QnA: No execute permission")
                self.qna_status_label.setStyleSheet("color: orange;")
        else:
            self.qna_status_label.setText("QnA: Not found - Settings > Set QnA Path")
            self.qna_status_label.setStyleSheet("color: red;")

    def update_cursor_position(self):
        """Update the cursor position in the status bar from the active input pane."""
        pane = self._get_active_input_pane()
        if pane is None:
            return
        cursor = pane.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber()
        self.line_label.setText(f"Line: {line}")
        self.char_label.setText(f"Char: {col}")

    def on_text_changed(self):
        """Handle text changes - update highlighting and dirty tracking."""
        self.highlight_matching_brackets()

        if self._suppress_dirty:
            return

        # Find which tab owns the sender pane and mark it dirty
        sender_pane = self.sender()
        for info in self.tab_data.values():
            if info.input_pane is sender_pane:
                if not info.is_dirty:
                    info.is_dirty = True
                    self._update_tab_label(info)
                    self._update_window_title()
                return

    def zoom_in(self):
        """Zoom in all text panes."""
        self.current_font_size += 2
        self._apply_font_to_all_panes()
        self.update_zoom_label()

    def zoom_out(self):
        """Zoom out all text panes."""
        if self.current_font_size > 4:
            self.current_font_size -= 2
        self._apply_font_to_all_panes()
        self.update_zoom_label()

    def zoom_reset(self):
        """Reset zoom to default."""
        self.current_font_size = 10
        self._apply_font_to_all_panes()
        self.update_zoom_label()

    def update_zoom_label(self):
        """Update the zoom level display in status bar."""
        if hasattr(self, 'zoom_label'):
            self.zoom_label.setText(f"Zoom: {self.current_font_size}pt")

    def remove_results(self):
        """Remove all A:, T:, E:, I: lines from the active QnA tab."""
        tab = self._get_active_tab()
        if tab is None or tab.tab_type != "qna":
            self.status_bar.showMessage("Remove Results is only available in QnA tabs.", 3000)
            return

        input_pane = tab.input_pane
        text = input_pane.toPlainText()
        lines = text.split('\n')

        # Filter out result lines (A:, T:, E:, I:)
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            if not (stripped.startswith('A:') or stripped.startswith('T:') or
                    stripped.startswith('E:') or stripped.startswith('I:')):
                filtered_lines.append(line)

        # Remove consecutive blank lines (keep at most one)
        result_lines = []
        prev_blank = False
        for line in filtered_lines:
            is_blank = line.strip() == ''
            if is_blank and prev_blank:
                continue
            result_lines.append(line)
            prev_blank = is_blank

        # Remove trailing blank lines
        while result_lines and result_lines[-1].strip() == '':
            result_lines.pop()

        new_text = '\n'.join(result_lines)

        # Preserve cursor position as best we can
        cursor = input_pane.textCursor()
        old_pos = cursor.position()

        self._suppress_dirty = True
        input_pane.setPlainText(new_text)
        self._suppress_dirty = False

        # Try to restore cursor position
        cursor = input_pane.textCursor()
        cursor.setPosition(min(old_pos, len(new_text)))
        input_pane.setTextCursor(cursor)

    def highlight_matching_brackets(self):
        """Highlight matching brackets/parentheses, if-then-else, and it-references at cursor position."""
        pane = self._get_active_input_pane()
        if pane is None:
            return
        try:
            # Always clear existing selections first
            pane.setExtraSelections([])

            cursor = pane.textCursor()
            text = pane.toPlainText()
            pos = cursor.position()

            if not text or pos > len(text):
                return

            # Check if cursor is on an "it" keyword
            it_selections = self.highlight_it_references(pane, text, pos)
            if it_selections:
                pane.setExtraSelections(it_selections)
                return

            # Check if cursor is on an if/then/else keyword
            keyword_selections = self.highlight_if_then_else(pane, text, pos)
            if keyword_selections:
                pane.setExtraSelections(keyword_selections)
                return

            # Check for bracket matching at cursor
            bracket_selections = self.get_cursor_bracket_selections(pane, text, pos)
            if bracket_selections:
                pane.setExtraSelections(bracket_selections)
        except Exception:
            # Silently ignore errors to prevent UI flooding
            pass

    def get_cursor_bracket_selections(self, pane, text, pos):
        """Get bracket highlighting for cursor position."""
        selections = []

        # Define bracket pairs
        open_brackets = '([{'
        close_brackets = ')]}'
        bracket_pairs = {'(': ')', '[': ']', '{': '}'}
        reverse_pairs = {')': '(', ']': '[', '}': '{'}

        # Check character at cursor and before cursor
        char_at = text[pos] if pos < len(text) else ''
        char_before = text[pos - 1] if pos > 0 else ''

        # Determine which character to match (prefer character before cursor for just-typed, then at cursor)
        check_pos = None
        check_char = None

        if char_before in open_brackets + close_brackets:
            check_pos = pos - 1
            check_char = char_before
        elif char_at in open_brackets + close_brackets:
            check_pos = pos
            check_char = char_at

        if check_pos is None or not check_char:
            return selections

        # Find matching bracket
        match_pos = self.find_matching_bracket(text, check_pos, check_char,
                                                open_brackets, close_brackets,
                                                bracket_pairs, reverse_pairs)

        # Matched bracket colors (orange background)
        match_format = QTextCharFormat()
        match_format.setBackground(QColor("#FFA500"))  # Orange
        match_format.setForeground(QColor("#000000"))  # Black text

        # Unmatched bracket colors (red background)
        unmatch_format = QTextCharFormat()
        unmatch_format.setBackground(QColor("#FF0000"))  # Red
        unmatch_format.setForeground(QColor("#FFFFFF"))  # White text

        if match_pos is not None:
            # Both brackets found - highlight both in orange
            sel1 = QTextEdit.ExtraSelection()
            cursor1 = pane.textCursor()
            cursor1.setPosition(check_pos)
            cursor1.setPosition(check_pos + 1, QTextCursor.KeepAnchor)
            sel1.cursor = cursor1
            sel1.format = match_format
            selections.append(sel1)

            sel2 = QTextEdit.ExtraSelection()
            cursor2 = pane.textCursor()
            cursor2.setPosition(match_pos)
            cursor2.setPosition(match_pos + 1, QTextCursor.KeepAnchor)
            sel2.cursor = cursor2
            sel2.format = match_format
            selections.append(sel2)
        else:
            # No match found - highlight current bracket in red
            sel = QTextEdit.ExtraSelection()
            cursor_sel = pane.textCursor()
            cursor_sel.setPosition(check_pos)
            cursor_sel.setPosition(check_pos + 1, QTextCursor.KeepAnchor)
            sel.cursor = cursor_sel
            sel.format = unmatch_format
            selections.append(sel)

        return selections

    def highlight_it_references(self, pane, text, pos):
        """Highlight 'it' keyword and what it refers to when cursor is on 'it'."""
        # Find all 'it', 'its', 'them' keywords
        it_keywords = []
        for match in re.finditer(r'\b(it|its|them)\b', text, re.IGNORECASE):
            it_keywords.append({
                'word': match.group().lower(),
                'start': match.start(),
                'end': match.end()
            })

        if not it_keywords:
            return None

        # Check if cursor is on an 'it' keyword (cursor must be within or immediately after)
        current_it = None
        for kw in it_keywords:
            if kw['start'] <= pos <= kw['end']:
                current_it = kw
                break

        if not current_it:
            return None  # Cursor not on 'it', no highlighting

        # Find what 'it' refers to
        referent = self.find_it_referent(text, current_it)

        # Create selections
        selections = []

        # Matched format (GREEN background - for matched it and referent)
        match_format = QTextCharFormat()
        match_format.setBackground(QColor("#90EE90"))  # Light green
        match_format.setForeground(QColor("#000000"))  # Black text

        # Unmatched format (red background)
        unmatch_format = QTextCharFormat()
        unmatch_format.setBackground(QColor("#FF0000"))  # Red
        unmatch_format.setForeground(QColor("#FFFFFF"))  # White text

        if referent:
            # Highlight the 'it' keyword in green (exact bounds)
            sel_it = QTextEdit.ExtraSelection()
            cursor_it = pane.textCursor()
            cursor_it.setPosition(current_it['start'])
            cursor_it.setPosition(current_it['end'], QTextCursor.KeepAnchor)
            sel_it.cursor = cursor_it
            sel_it.format = match_format
            selections.append(sel_it)

            # Highlight the referent in green
            sel_ref = QTextEdit.ExtraSelection()
            cursor_ref = pane.textCursor()
            cursor_ref.setPosition(referent['start'])
            cursor_ref.setPosition(referent['end'], QTextCursor.KeepAnchor)
            sel_ref.cursor = cursor_ref
            sel_ref.format = match_format
            selections.append(sel_ref)

            # Also highlight any other 'it' keywords that refer to the same thing
            for other_it in it_keywords:
                if other_it['start'] != current_it['start']:
                    other_ref = self.find_it_referent(text, other_it)
                    if other_ref and other_ref['start'] == referent['start'] and other_ref['end'] == referent['end']:
                        sel_other = QTextEdit.ExtraSelection()
                        cursor_other = pane.textCursor()
                        cursor_other.setPosition(other_it['start'])
                        cursor_other.setPosition(other_it['end'], QTextCursor.KeepAnchor)
                        sel_other.cursor = cursor_other
                        sel_other.format = match_format
                        selections.append(sel_other)
        else:
            # No referent found - highlight only 'it' in red (exact bounds)
            sel_it = QTextEdit.ExtraSelection()
            cursor_it = pane.textCursor()
            cursor_it.setPosition(current_it['start'])
            cursor_it.setPosition(current_it['end'], QTextCursor.KeepAnchor)
            sel_it.cursor = cursor_it
            sel_it.format = unmatch_format
            selections.append(sel_it)

        return selections

    def find_it_referent(self, text, it_keyword):
        """Find what an 'it' keyword refers to in the relevance expression."""
        it_pos = it_keyword['start']

        # Case 1: Check for "whose (" pattern before 'it'
        whose_match = self.find_whose_context(text, it_pos)
        if whose_match:
            return whose_match

        # Case 2: Check for "of it" pattern - find what comes after final "of"
        of_it_match = self.find_of_it_context(text, it_pos)
        if of_it_match:
            return of_it_match

        return None

    def find_whose_context(self, text, it_pos):
        """Find the expression that 'it' refers to in a 'whose' clause."""
        # Find all 'whose' keywords with opening paren
        whose_matches = list(re.finditer(r'\bwhose\s*\(', text, re.IGNORECASE))

        if not whose_matches:
            return None

        # Find which 'whose' clause contains this 'it'
        containing_whose = None
        for whose_match in whose_matches:
            whose_end = whose_match.end()  # Position after 'whose ('
            paren_start = whose_end - 1  # Position of '('

            # Find the matching closing paren
            paren_depth = 1
            paren_end = None

            for i in range(whose_end, len(text)):
                if text[i] == '(':
                    paren_depth += 1
                elif text[i] == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        paren_end = i
                        break

            # Check if 'it' is within this whose's parentheses
            if paren_end is not None and whose_end <= it_pos <= paren_end:
                containing_whose = whose_match
                break
            # Also check if paren_end is None (unclosed paren) but it is after whose
            elif paren_end is None and it_pos >= whose_end:
                containing_whose = whose_match
                break

        if not containing_whose:
            return None

        whose_start = containing_whose.start()

        # Now find what's immediately before 'whose'
        # Skip whitespace backward
        expr_end = whose_start
        while expr_end > 0 and text[expr_end - 1] in ' \t\n':
            expr_end -= 1

        if expr_end == 0:
            return None

        # Check if it ends with ')' - parenthesized expression
        if text[expr_end - 1] == ')':
            # Find matching opening paren
            paren_depth = 1
            expr_start = expr_end - 2
            while expr_start >= 0 and paren_depth > 0:
                if text[expr_start] == ')':
                    paren_depth += 1
                elif text[expr_start] == '(':
                    paren_depth -= 1
                expr_start -= 1

            # expr_start is now one before the '(', so add 1
            expr_start += 1

            if paren_depth == 0 and expr_start >= 0:
                return {'start': expr_start, 'end': expr_end}
        else:
            # Find the single word immediately before 'whose'
            word_end = expr_end
            word_start = word_end

            while word_start > 0:
                ch = text[word_start - 1]
                if ch in ' \t\n()[]{},:;':
                    break
                word_start -= 1

            if word_start < word_end:
                return {'start': word_start, 'end': word_end}

        return None

    def find_of_it_context(self, text, it_pos):
        """Find the object that 'it' refers to in an 'of it' pattern."""
        # Pattern: (... of it ...) of <object>
        # First check if this 'it' follows 'of'
        before_it = text[:it_pos].rstrip()
        if not before_it.lower().endswith(' of'):
            return None

        # Find the parentheses level containing this 'it'
        paren_depth = 0
        paren_start = None

        for i in range(it_pos - 1, -1, -1):
            if text[i] == ')':
                paren_depth += 1
            elif text[i] == '(':
                if paren_depth == 0:
                    paren_start = i
                    break
                else:
                    paren_depth -= 1

        if paren_start is None:
            return None

        # Find the closing paren for this group
        paren_depth = 1
        paren_end = None
        for i in range(paren_start + 1, len(text)):
            if text[i] == '(':
                paren_depth += 1
            elif text[i] == ')':
                paren_depth -= 1
                if paren_depth == 0:
                    paren_end = i
                    break

        if paren_end is None:
            return None

        # Now look for "of <object>" after the closing paren
        after_paren = text[paren_end + 1:].lstrip()

        if not after_paren.lower().startswith('of '):
            return None

        # Find the start of the object after 'of'
        of_match = re.match(r'of\s+', after_paren, re.IGNORECASE)
        if not of_match:
            return None

        obj_start_relative = of_match.end()
        obj_start_absolute = paren_end + 1 + (len(text[paren_end + 1:]) - len(after_paren)) + obj_start_relative

        # Find the end of the object (until newline, end of text, or closing paren at depth 0)
        obj_end = obj_start_absolute
        paren_depth = 0

        while obj_end < len(text):
            ch = text[obj_end]
            if ch == '(':
                paren_depth += 1
            elif ch == ')':
                if paren_depth == 0:
                    break
                paren_depth -= 1
            elif ch == '\n':
                break
            obj_end += 1

        # Trim trailing whitespace
        while obj_end > obj_start_absolute and text[obj_end - 1] in ' \t':
            obj_end -= 1

        if obj_end > obj_start_absolute:
            return {'start': obj_start_absolute, 'end': obj_end}

        return None

    def highlight_if_then_else(self, pane, text, pos):
        """Check if cursor is on if/then/else and highlight matching keywords."""
        # Find all if/then/else keywords with their positions (case insensitive)
        keywords = []
        for match in re.finditer(r'\b(if|then|else)\b', text, re.IGNORECASE):
            keywords.append({
                'word': match.group().lower(),
                'start': match.start(),
                'end': match.end()
            })

        if not keywords:
            return None

        # Check if cursor is on any keyword
        current_keyword = None
        for kw in keywords:
            if kw['start'] <= pos <= kw['end']:
                current_keyword = kw
                break

        if not current_keyword:
            return None

        # Find the matching if-then-else group for this keyword
        if_pos, then_pos, else_pos = self.find_matching_if_then_else(text, keywords, current_keyword)

        # Create selections
        selections = []

        # Matched format (orange)
        match_format = QTextCharFormat()
        match_format.setBackground(QColor("#FFA500"))  # Orange
        match_format.setForeground(QColor("#000000"))  # Black text

        # Unmatched format (red)
        unmatch_format = QTextCharFormat()
        unmatch_format.setBackground(QColor("#FF0000"))  # Red
        unmatch_format.setForeground(QColor("#FFFFFF"))  # White text

        # Check if we have a complete if-then-else
        all_matched = if_pos is not None and then_pos is not None and else_pos is not None

        # Helper to create selection with exact keyword bounds
        def add_selection(kw_info, is_matched):
            sel = QTextEdit.ExtraSelection()
            cursor = pane.textCursor()
            cursor.setPosition(kw_info['start'])
            cursor.setPosition(kw_info['end'], QTextCursor.KeepAnchor)
            sel.cursor = cursor
            sel.format = match_format if is_matched else unmatch_format
            selections.append(sel)

        # Add selections for found keywords
        if if_pos is not None:
            add_selection(if_pos, all_matched)
        if then_pos is not None:
            add_selection(then_pos, all_matched)
        if else_pos is not None:
            add_selection(else_pos, all_matched)

        return selections if selections else None

    def get_paren_depth(self, text, pos):
        """Calculate parenthesis depth at a given position."""
        depth = 0
        for i in range(pos):
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
        return depth

    def find_matching_if_then_else(self, text, keywords, current_keyword):
        """Find the matching if, then, else for the current keyword, respecting parentheses."""
        current_word = current_keyword['word']

        if current_word == 'if':
            return self.find_then_else_for_if(text, current_keyword, keywords)
        elif current_word == 'then':
            return self.find_if_else_for_then(text, current_keyword, keywords)
        elif current_word == 'else':
            return self.find_if_then_for_else(text, current_keyword, keywords)

        return None, None, None

    def find_then_else_for_if(self, text, if_kw, keywords):
        """Given an 'if', find its matching 'then' and 'else', respecting parentheses."""
        if_start = if_kw['start']
        start_depth = self.get_paren_depth(text, if_start)

        found_then = None
        found_else = None
        if_nesting = 0  # Track nested if statements at same paren level

        # Get keywords after this 'if', sorted by position
        after_keywords = sorted([k for k in keywords if k['start'] > if_start],
                                key=lambda x: x['start'])

        current_depth = start_depth

        for kw in after_keywords:
            # Update paren depth by scanning text between last position and this keyword
            for i in range(if_start if kw == after_keywords[0] else prev_end, kw['start']):
                if text[i] == '(':
                    current_depth += 1
                elif text[i] == ')':
                    current_depth -= 1
                    # If we drop below starting depth, stop searching
                    if current_depth < start_depth:
                        return if_kw, found_then, found_else

            prev_end = kw['end']

            # Only consider keywords at same or deeper depth
            if current_depth >= start_depth:
                if kw['word'] == 'if':
                    if_nesting += 1
                elif kw['word'] == 'then':
                    if if_nesting == 0 and found_then is None:
                        found_then = kw
                    elif if_nesting > 0:
                        pass  # This then belongs to a nested if
                elif kw['word'] == 'else':
                    if if_nesting == 0 and found_then is not None and found_else is None:
                        found_else = kw
                        return if_kw, found_then, found_else
                    elif if_nesting > 0:
                        if_nesting -= 1  # else closes a nested if-then-else

        return if_kw, found_then, found_else

    def find_if_else_for_then(self, text, then_kw, keywords):
        """Given a 'then', find its matching 'if' and 'else', respecting parentheses."""
        then_start = then_kw['start']
        start_depth = self.get_paren_depth(text, then_start)

        # Look backward for 'if'
        found_if = None
        then_nesting = 0

        before_keywords = sorted([k for k in keywords if k['start'] < then_start],
                                 key=lambda x: x['start'], reverse=True)

        current_depth = start_depth
        prev_pos = then_start

        for kw in before_keywords:
            # Update paren depth by scanning text backward
            for i in range(prev_pos - 1, kw['end'] - 1, -1):
                if text[i] == ')':
                    current_depth += 1
                elif text[i] == '(':
                    current_depth -= 1
                    if current_depth < start_depth:
                        break

            if current_depth < start_depth:
                break

            prev_pos = kw['start']

            if current_depth >= start_depth:
                if kw['word'] == 'then':
                    then_nesting += 1
                elif kw['word'] == 'if':
                    if then_nesting == 0:
                        found_if = kw
                        break
                    else:
                        then_nesting -= 1

        # Look forward for 'else'
        found_else = None
        if found_if:
            if_nesting = 0
            current_depth = start_depth

            after_keywords = sorted([k for k in keywords if k['start'] > then_start],
                                    key=lambda x: x['start'])

            prev_end = then_kw['end']

            for kw in after_keywords:
                # Update paren depth
                for i in range(prev_end, kw['start']):
                    if text[i] == '(':
                        current_depth += 1
                    elif text[i] == ')':
                        current_depth -= 1
                        if current_depth < start_depth:
                            return found_if, then_kw, found_else

                prev_end = kw['end']

                if current_depth >= start_depth:
                    if kw['word'] == 'if':
                        if_nesting += 1
                    elif kw['word'] == 'else':
                        if if_nesting == 0:
                            found_else = kw
                            break
                        else:
                            if_nesting -= 1

        return found_if, then_kw, found_else

    def find_if_then_for_else(self, text, else_kw, keywords):
        """Given an 'else', find its matching 'if' and 'then', respecting parentheses."""
        else_start = else_kw['start']
        start_depth = self.get_paren_depth(text, else_start)

        # Look backward for 'then' and 'if'
        found_then = None
        found_if = None
        else_nesting = 0

        before_keywords = sorted([k for k in keywords if k['start'] < else_start],
                                 key=lambda x: x['start'], reverse=True)

        current_depth = start_depth
        prev_pos = else_start

        for kw in before_keywords:
            # Update paren depth by scanning text backward
            for i in range(prev_pos - 1, kw['end'] - 1, -1):
                if text[i] == ')':
                    current_depth += 1
                elif text[i] == '(':
                    current_depth -= 1
                    if current_depth < start_depth:
                        break

            if current_depth < start_depth:
                break

            prev_pos = kw['start']

            if current_depth >= start_depth:
                if kw['word'] == 'else':
                    else_nesting += 1
                elif kw['word'] == 'then':
                    if else_nesting == 0 and found_then is None:
                        found_then = kw
                elif kw['word'] == 'if':
                    if else_nesting == 0 and found_then is not None:
                        found_if = kw
                        break
                    elif else_nesting > 0:
                        else_nesting -= 1

        return found_if, found_then, else_kw

    def find_matching_bracket(self, text, pos, char, open_brackets, close_brackets,
                               bracket_pairs, reverse_pairs):
        """Find the position of the matching bracket."""
        # Guard against empty or invalid characters
        if not char or char not in open_brackets + close_brackets:
            return None

        if char in open_brackets:
            # Search forward for closing bracket
            target = bracket_pairs[char]
            direction = 1
            count = 1
            search_pos = pos + 1

            while search_pos < len(text):
                c = text[search_pos]
                if c == char:
                    count += 1
                elif c == target:
                    count -= 1
                    if count == 0:
                        return search_pos
                search_pos += direction

        elif char in close_brackets:
            # Search backward for opening bracket
            target = reverse_pairs[char]
            direction = -1
            count = 1
            search_pos = pos - 1

            while search_pos >= 0:
                c = text[search_pos]
                if c == char:
                    count += 1
                elif c == target:
                    count -= 1
                    if count == 0:
                        return search_pos
                search_pos += direction

        return None  # No match found

    # --- Pretty-printer for relevance expressions ---

    def pretty_print_relevance(self, expr):
        """Pretty-print a relevance expression with indentation based on
        parenthesis depth and if/then/else keywords."""
        tokens = self._tokenize_for_pretty_print(expr)

        result = []
        indent_level = 0
        indent_str = "    "  # 4 spaces per level
        current_line = ""

        for token in tokens:
            token_stripped = token.strip()
            if not token_stripped:
                # Whitespace-only token, add a space to current line
                if current_line and not current_line.endswith(' '):
                    current_line += ' '
                continue

            token_lower = token_stripped.lower()

            if token_stripped == '(':
                # Flush current line, then open paren on its own line
                if current_line.strip():
                    result.append(indent_str * indent_level + current_line.strip())
                    current_line = ""
                result.append(indent_str * indent_level + '(')
                indent_level += 1
            elif token_stripped == ')':
                # Flush current line, dedent, then close paren
                if current_line.strip():
                    result.append(indent_str * indent_level + current_line.strip())
                    current_line = ""
                indent_level = max(0, indent_level - 1)
                result.append(indent_str * indent_level + ')')
            elif token_lower in ('if', 'then', 'else'):
                # Put keyword on its own line at current indent
                if current_line.strip():
                    result.append(indent_str * indent_level + current_line.strip())
                    current_line = ""
                current_line = token_stripped + " "
            else:
                current_line += token_stripped + " "

        # Flush remaining content
        if current_line.strip():
            result.append(indent_str * indent_level + current_line.strip())

        return '\n'.join(result)

    def _tokenize_for_pretty_print(self, expr):
        """Split expression into tokens for pretty printing.
        Tokens are: '(', ')', 'if', 'then', 'else', and runs of other text."""
        # Split on parentheses and if/then/else keywords, keeping delimiters
        parts = re.split(r'(\(|\)|\bif\b|\bthen\b|\belse\b)', expr, flags=re.IGNORECASE)
        return [p for p in parts if p]  # Remove empty strings

    def format_expression(self):
        """Toggle between expanded (pretty-printed) and compact (single-line) relevance."""
        tab = self._get_active_tab()
        if tab is None or tab.tab_type != "sc":
            self.status_bar.showMessage("Expand/Compact is only available in Single Clause tabs.", 3000)
            return

        expr = tab.input_pane.toPlainText().strip()
        if not expr:
            return

        if '\n' in expr:
            # Currently expanded -> compact to single line
            single_line = ' '.join(expr.split())
            tab.input_pane.setPlainText(single_line)
            self.format_mode_btn.setToolTip("Expand Relevance")
        else:
            # Currently compact -> expand/pretty-print
            formatted = self.pretty_print_relevance(expr)
            tab.input_pane.setPlainText(formatted)
            self.format_mode_btn.setToolTip("Compact Relevance")

    # --- Evaluation methods ---

    def evaluate(self):
        """Evaluate based on current tab type."""
        tab = self._get_active_tab()
        if tab is None:
            return
        self.evaluating_tab = tab  # Lock evaluation to this tab
        if tab.tab_type == "qna":
            self.evaluate_qna_mode()
        else:
            self.evaluate_single_clause_mode()

    def evaluate_qna_mode(self):
        """Find and evaluate all Q: lines in the document (QnA mode)."""
        # Stop any running worker first
        if self.worker is not None:
            try:
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.cancel()
                if not self.worker.wait(1000):
                    self.worker.terminate()
                    self.worker.wait(500)
            self.worker = None

        if not os.path.exists(self.qna_path):
            QMessageBox.warning(
                self, "QnA Not Found",
                f"The qna binary was not found at:\n{self.qna_path}\n\n"
                "Please set the correct path via Settings > Set QnA Path"
            )
            return

        input_pane = self.evaluating_tab.input_pane

        # First, strip all existing results (A:, E:, T:, I: lines) but keep Q: lines and blank lines
        text = input_pane.toPlainText()
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith(('A:', 'E:', 'T:', 'I:')):
                cleaned_lines.append(line)

        # Remove consecutive blank lines (keep max 1)
        final_lines = []
        prev_blank = False
        for line in cleaned_lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue  # Skip consecutive blanks
            final_lines.append(line)
            prev_blank = is_blank

        # Update the text pane with cleaned content
        cleaned_text = '\n'.join(final_lines)
        self._suppress_dirty = True
        input_pane.setPlainText(cleaned_text)
        self._suppress_dirty = False

        # Now find all Q: queries
        lines = cleaned_text.split('\n')

        # Find Q: queries - each Q: line is a separate query
        # Multi-line queries: Q: continues on next non-empty, non-Q: lines
        self.pending_queries = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith('Q:') and len(stripped) > 2:
                query_parts = [stripped[2:].strip()]  # First line without Q:
                query_end_line = i

                # Look ahead for continuation lines (not starting with Q: and not empty)
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    if not next_line or next_line.startswith('Q:'):
                        break
                    query_parts.append(next_line)
                    query_end_line = j
                    j += 1

                # Join multi-line query
                full_query = ' '.join(query_parts)
                if full_query:  # Only add if there's actual content
                    self.pending_queries.append((query_end_line, full_query))
                i = j
            else:
                i += 1

        if not self.pending_queries:
            # No Q: lines found - check if user typed without Q:
            cursor = input_pane.textCursor()
            cursor.movePosition(QTextCursor.StartOfLine)
            cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
            current_line = cursor.selectedText().strip()

            if current_line and not current_line.startswith('Q:'):
                # User typed a query without Q: - add it and evaluate
                cursor = input_pane.textCursor()
                cursor.movePosition(QTextCursor.StartOfLine)
                cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
                self._suppress_dirty = True
                cursor.removeSelectedText()
                cursor.insertText(f"Q: {current_line}")
                self._suppress_dirty = False
                input_pane.setTextCursor(cursor)

                # Add this as a pending query
                block_num = input_pane.textCursor().blockNumber()
                self.pending_queries.append((block_num, current_line))

        if not self.pending_queries:
            self.status_bar.showMessage("No queries to evaluate. Type 'Q: your query' and press F5.", 3000)
            return

        # Process in reverse order so line insertions don't affect earlier line numbers
        self.pending_queries.reverse()

        self.current_query_index = 0
        self.total_elapsed_time = 0
        self.evaluate_next_query()

    def evaluate_single_clause_mode(self):
        """Evaluate the single relevance expression in Single Clause mode."""
        # Stop any running worker first
        if self.worker is not None:
            try:
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.cancel()
                if not self.worker.wait(1000):
                    self.worker.terminate()
                    self.worker.wait(500)
            self.worker = None

        if not os.path.exists(self.qna_path):
            QMessageBox.warning(
                self, "QnA Not Found",
                f"The qna binary was not found at:\n{self.qna_path}\n\n"
                "Please set the correct path via Settings > Set QnA Path"
            )
            return

        input_pane = self.evaluating_tab.input_pane
        output_pane = self.evaluating_tab.output_pane

        # Get expression from the relevance pane (no Q: prefix needed)
        expression = input_pane.toPlainText().strip()
        if not expression:
            self.status_bar.showMessage("No expression to evaluate.", 3000)
            return

        # Collapse multi-line expression to single line for qna
        expression = ' '.join(expression.split())

        # Check for Q: prefix — not allowed in Single Clause mode
        if expression.upper().startswith('Q:'):
            if output_pane:
                output_pane.setPlainText(
                    "E: Single Clause mode does not use the 'Q:' prefix.\n"
                    "Please remove the 'Q:' from your expression and try again."
                )
            self.status_bar.showMessage(
                "Remove the 'Q:' prefix — Single Clause mode evaluates expressions directly.", 5000)
            return

        # Clear previous output
        if output_pane:
            output_pane.clear()

        self.evaluate_btn.setEnabled(False)
        self.evaluate_btn.setText("Evaluating...")
        self.eval_mode_btn.setEnabled(False)
        self.status_bar.showMessage("Evaluating expression...")
        self.total_elapsed_time = 0

        # Create worker
        self.worker_counter += 1
        self.worker = QnAWorker(self.qna_path, expression, self.worker_counter, show_types=True)
        self.worker.finished.connect(self._on_sc_worker_finished, Qt.QueuedConnection)
        self.worker.error.connect(self._on_sc_worker_error, Qt.QueuedConnection)
        self.worker.start()

    def _on_sc_worker_finished(self, result, time_val):
        """Handle worker result for Single Clause mode."""
        if self.worker is None or self.evaluating_tab is None:
            return

        output_pane = self.evaluating_tab.output_pane
        if output_pane is None:
            return

        self.total_elapsed_time = time_val
        self.time_label.setText(f"Evaluation time: {time_val:.3f} ms")

        # Format output with evaluation time summary at the bottom
        output_text = result
        if output_text:
            output_text += f"\n\nEvaluation time: {time_val:.3f} ms"

        output_pane.setPlainText(output_text)

        self.evaluate_btn.setEnabled(True)
        self.evaluate_btn.setText("Evaluate")
        self.eval_mode_btn.setEnabled(True)
        self.status_bar.showMessage("Evaluation complete", 3000)

        self._cleanup_worker()

    def _on_sc_worker_error(self, err):
        """Handle worker error for Single Clause mode."""
        if self.worker is None or self.evaluating_tab is None:
            return

        output_pane = self.evaluating_tab.output_pane
        if output_pane:
            output_pane.setPlainText(f"E: {err}")

        self.evaluate_btn.setEnabled(True)
        self.evaluate_btn.setText("Evaluate")
        self.eval_mode_btn.setEnabled(True)
        self.status_bar.showMessage("Evaluation error", 3000)

        self._cleanup_worker()

    def _cleanup_worker(self):
        """Safely clean up the current worker thread."""
        if self.worker is not None:
            try:
                self.worker.finished.disconnect()
            except Exception:
                pass
            try:
                self.worker.error.disconnect()
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.wait(1000)
            self.worker = None

    def evaluate_next_query(self):
        """Evaluate the next pending query (QnA mode)."""
        if self.current_query_index >= len(self.pending_queries):
            self.status_bar.showMessage("Evaluation complete", 3000)
            self.evaluate_btn.setEnabled(True)
            self.evaluate_btn.setText("Evaluate")
            self.eval_mode_btn.setEnabled(True)
            # Clean up the last worker
            self._cleanup_worker()
            return

        line_num, query = self.pending_queries[self.current_query_index]
        self.current_line_num = line_num  # Store for use in callbacks

        self.evaluate_btn.setEnabled(False)
        self.evaluate_btn.setText("Evaluating...")
        self.eval_mode_btn.setEnabled(False)
        self.status_bar.showMessage(f"Evaluating query {self.current_query_index + 1} of {len(self.pending_queries)}...")

        # Clean up previous worker if exists
        if self.worker is not None:
            try:
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.cancel()
                if not self.worker.wait(1000):
                    self.worker.terminate()
                    self.worker.wait(500)
            self.worker = None

        # Run evaluation in worker thread
        self.worker_counter += 1
        self.worker = QnAWorker(self.qna_path, query, self.worker_counter, show_types=True)
        self.worker.finished.connect(self._on_worker_finished, Qt.QueuedConnection)
        self.worker.error.connect(self._on_worker_error, Qt.QueuedConnection)
        self.worker.start()

    def _on_worker_finished(self, result, time_val):
        """Internal slot for worker finished signal (QnA mode)."""
        if self.worker is None:
            return
        self.on_query_finished(self.current_line_num, result, time_val)

    def _on_worker_error(self, err):
        """Internal slot for worker error signal (QnA mode)."""
        if self.worker is None:
            return
        self.on_query_error(self.current_line_num, err)

    def on_query_finished(self, line_num, result, elapsed_time):
        """Handle successful query evaluation (QnA mode)."""
        # Add blank line after result for spacing (except for last query visually, which is first processed)
        is_last_query = (self.current_query_index == len(self.pending_queries) - 1)
        self.insert_result_after_line(line_num, result, add_spacing=not is_last_query)

        self.total_elapsed_time += elapsed_time
        self.time_label.setText(f"Evaluation time: {self.total_elapsed_time:.3f} ms")

        self.current_query_index += 1
        self.evaluate_next_query()

    def on_query_error(self, line_num, error_msg):
        """Handle query evaluation error (QnA mode)."""
        is_last_query = (self.current_query_index == len(self.pending_queries) - 1)
        self.insert_result_after_line(line_num, f"E: {error_msg}", add_spacing=not is_last_query)

        self.current_query_index += 1
        self.evaluate_next_query()

    def insert_result_after_line(self, line_num, result, add_spacing=True):
        """Insert the result text after the specified line number (QnA mode)."""
        if self.evaluating_tab is None:
            return
        input_pane = self.evaluating_tab.input_pane

        cursor = input_pane.textCursor()

        # Move to end of the specified line
        cursor.movePosition(QTextCursor.Start)
        for _ in range(line_num):
            cursor.movePosition(QTextCursor.NextBlock)
        cursor.movePosition(QTextCursor.EndOfBlock)

        # Insert result on new line, with optional blank line for spacing
        if result:
            text_to_insert = '\n' + result
            if add_spacing:
                text_to_insert += '\n'  # Add blank line after results
            self._suppress_dirty = True
            cursor.insertText(text_to_insert)
            self._suppress_dirty = False

        input_pane.setTextCursor(cursor)

        # Scroll to show the result
        input_pane.ensureCursorVisible()

    def stop_evaluation(self):
        """Stop the current evaluation."""
        if self.worker is not None:
            try:
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.cancel()
                self.worker.terminate()
                if not self.worker.wait(2000):  # Wait up to 2 seconds
                    pass
            self.worker = None

        self.pending_queries = []
        self.evaluating_tab = None
        self.evaluate_btn.setEnabled(True)
        self.evaluate_btn.setText("Evaluate")
        self.eval_mode_btn.setEnabled(True)
        self.status_bar.showMessage("Evaluation stopped", 3000)

    def clear_all(self):
        """Clear the active tab's pane(s)."""
        tab = self._get_active_tab()
        if tab is None:
            return

        if tab.is_dirty:
            if not self._prompt_save_changes(tab):
                return

        self._suppress_dirty = True
        tab.input_pane.clear()
        if tab.output_pane:
            tab.output_pane.clear()
        self._suppress_dirty = False

        tab.is_dirty = False
        tab._saved_content = ""
        self._update_tab_label(tab)
        self._update_window_title()
        self.time_label.setText("Evaluation time: -")

    def new_file(self):
        """Create a new file in the active tab."""
        tab = self._get_active_tab()
        if tab is None:
            return

        if tab.input_pane.toPlainText():
            if not self._prompt_save_changes(tab):
                return

        self._suppress_dirty = True
        tab.input_pane.clear()
        if tab.output_pane:
            tab.output_pane.clear()
        self._suppress_dirty = False

        tab.current_file = None
        self._mark_tab_clean(tab)
        self._update_window_title()

    def open_file(self):
        """Open a relevance file into the active tab."""
        tab = self._get_active_tab()
        if tab is None:
            return

        if tab.is_dirty:
            if not self._prompt_save_changes(tab):
                return

        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Relevance File",
            "", "Relevance Files (*.bes *.rel *.txt *.qna);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    content = f.read()
                self._suppress_dirty = True
                tab.input_pane.setPlainText(content)
                self._suppress_dirty = False
                tab.current_file = filename
                self._mark_tab_clean(tab)
                self._update_window_title()
            except Exception as e:
                self._suppress_dirty = False
                QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")

    def save_file(self):
        """Save the active tab's file."""
        tab = self._get_active_tab()
        if tab is None:
            return

        if tab.current_file:
            try:
                with open(tab.current_file, 'w') as f:
                    f.write(tab.input_pane.toPlainText())
                self._mark_tab_clean(tab)
                self.status_bar.showMessage(f"Saved: {tab.current_file}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
        else:
            self.save_file_as()

    def save_file_as(self):
        """Save the active tab's file with a new name."""
        tab = self._get_active_tab()
        if tab is None:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Relevance File",
            "", "QnA Files (*.qna);;Relevance Files (*.rel);;Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(tab.input_pane.toPlainText())
                tab.current_file = filename
                self._mark_tab_clean(tab)
                self._update_window_title()
                self.status_bar.showMessage(f"Saved: {filename}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")

    def set_qna_path(self):
        """Set the path to the qna binary."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select QnA Binary",
            "/opt/BESClient/bin", "All Files (*)"
        )
        if filename:
            self.qna_path = filename
            self.check_qna_binary()

    def show_about(self):
        """Show the about dialog."""
        QMessageBox.about(
            self, "About Fixlet Debugger",
            "<h3>Fixlet Debugger for Linux v1.2.1</h3>"
            "<p>A GUI wrapper for the BigFix qna command-line tool.</p>"
            "<p>Provides similar functionality to the Windows Fixlet Debugger.</p>"
            "<hr>"
            "<p><b>Modes:</b></p>"
            "<ul>"
            "<li><b>(qna)*</b>: Multiple Q: queries with inline results</li>"
            "<li><b>(single clause)</b>: Single expression with formatted output</li>"
            "</ul>"
            "<hr>"
            "<p><b>Shortcuts:</b></p>"
            "<ul>"
            "<li>F5 or Ctrl+Enter: Evaluate</li>"
            "<li>Escape: Stop evaluation</li>"
            "<li>Ctrl+R: Remove results (QnA tabs)</li>"
            "<li>Ctrl+Shift+F: Expand/Compact relevance (Single Clause tabs)</li>"
            "<li>Ctrl+O: Open file</li>"
            "<li>Ctrl+S: Save file</li>"
            "</ul>"
            "<hr>"
            "<p>Created by Mike Consuegra for use with HCL BigFix</p>"
        )

    def show_help(self):
        """Show relevance reference help."""
        help_text = """
<h3>BigFix Relevance Quick Reference</h3>

<h4>Usage:</h4>
<p>Type queries starting with <code>Q:</code> and press F5:</p>
<pre>
Q: name of operating system
Q: computer name
Q: version of client
</pre>

<h4>Common Inspectors:</h4>
<ul>
<li><code>name of operating system</code> - OS name</li>
<li><code>computer name</code> - Hostname</li>
<li><code>now</code> - Current date/time</li>
<li><code>names of running processes</code> - Running processes</li>
<li><code>addresses of adapters of network</code> - IP addresses</li>
</ul>

<h4>Operators:</h4>
<ul>
<li><code>exists</code> - Check if something exists</li>
<li><code>whose</code> - Filter results</li>
<li><code>it</code> - Reference current object</li>
<li><code>contains</code> - String contains</li>
<li><code>as string</code> - Convert to string</li>
</ul>

<h4>Examples:</h4>
<pre>
Q: exists file "/etc/passwd"

Q: (name of it, version of it) of operating system

Q: names of running processes whose (it contains "bes")
</pre>

<p>For full documentation, visit the BigFix Developer site.</p>
"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Relevance Reference")
        msg.setTextFormat(Qt.RichText)
        msg.setText(help_text)
        msg.exec_()

    def closeEvent(self, event):
        """Handle window close event."""
        # Check all tabs for unsaved changes
        for info in list(self.tab_data.values()):
            if info.is_dirty:
                if not self._prompt_save_changes(info):
                    event.ignore()
                    return

        # Stop any running worker
        if self.worker is not None:
            try:
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except Exception:
                pass
            if self.worker.isRunning():
                self.worker.cancel()
                self.worker.terminate()
                if not self.worker.wait(2000):  # Wait up to 2 seconds
                    pass
            self.worker = None

        self.evaluating_tab = None
        event.accept()


def main():
    # Suppress dconf warnings when running as root (no D-Bus session bus)
    if os.environ.get('EUID', '') == '0' or os.geteuid() == 0:
        os.environ.setdefault('GSETTINGS_BACKEND', 'memory')

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Set application-wide font
    font = QFont("Sans Serif", 10)
    app.setFont(font)

    window = FixletDebugger()

    # Set app-level icon (ensures taskbar icon on all Linux DEs)
    app.setWindowIcon(window._create_app_icon())

    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
