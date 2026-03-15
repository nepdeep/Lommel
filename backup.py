import glob
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BACKUP_DIR = "backup"
BASE_EXCLUDED_NAMES = {
    "backup.py",
    "bkup_html.py",
    "bkup_python.py",
    "bkup_combined.py",
}
BACKUP_PATTERN = r"^(.+)R(\d+)\.backup\.(.+)$"


class BackupManager:
    def __init__(self, root_dir=None, backup_dir=BACKUP_DIR, exclude_gitpushui=True):
        self.root_dir = Path(root_dir or Path(__file__).resolve().parent).resolve()
        self.backup_dir = self.root_dir / backup_dir
        self.exclude_gitpushui = exclude_gitpushui

    def get_excluded_names(self):
        excluded = {name.lower() for name in BASE_EXCLUDED_NAMES}
        if self.exclude_gitpushui:
            excluded.add("gitpushui.py")
        try:
            excluded.add(Path(__file__).name.lower())
        except Exception:
            pass
        return excluded

    def ensure_backup_directory(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize_filename(text):
        invalid_chars = '<>:"/\\|?*'
        cleaned = text.strip()
        for char in invalid_chars:
            cleaned = cleaned.replace(char, "_")
        cleaned = " ".join(cleaned.split())
        cleaned = cleaned.strip(" ._")
        return cleaned[:60] or "backup"

    def detect_available_files(self):
        html_files = sorted(
            [p.name for p in self.root_dir.glob("*.html") if p.is_file()],
            key=str.lower,
        )

        excluded = self.get_excluded_names()
        py_files = sorted(
            [
                p.name
                for p in self.root_dir.glob("*.py")
                if p.is_file() and p.name.lower() not in excluded
            ],
            key=str.lower,
        )
        return html_files, py_files

    def get_files_by_type(self, selected_type):
        html_files, py_files = self.detect_available_files()
        if selected_type == "html":
            return html_files
        if selected_type == "py":
            return py_files
        return sorted(html_files + py_files, key=str.lower)

    def get_counts(self):
        html_files, py_files = self.detect_available_files()
        return len(html_files), len(py_files)

    def get_next_backup_number(self, base_filename):
        revision = 1
        while True:
            pattern = str(self.backup_dir / f"{base_filename}R{revision:02d}.*")
            if not glob.glob(pattern):
                return revision
            revision += 1

    def detect_original_extension(self, base_name, current_html_bases=None, current_py_bases=None):
        if current_html_bases is None or current_py_bases is None:
            html_files, py_files = self.detect_available_files()
            current_html_bases = {Path(f).stem for f in html_files}
            current_py_bases = {Path(f).stem for f in py_files}

        if base_name in current_html_bases:
            return ".html"
        if base_name in current_py_bases:
            return ".py"
        return None

    def get_backup_files(self, selected_type="both"):
        data = {}
        if not self.backup_dir.exists():
            return data

        html_files, py_files = self.detect_available_files()
        current_html_bases = {Path(f).stem for f in html_files}
        current_py_bases = {Path(f).stem for f in py_files}

        for item in self.backup_dir.iterdir():
            if not item.is_file():
                continue

            match = re.match(BACKUP_PATTERN, item.name)
            if not match:
                continue

            base_name = match.group(1)
            revision = int(match.group(2))
            description = match.group(3)
            ext = self.detect_original_extension(base_name, current_html_bases, current_py_bases)
            ext = ext or "unknown"

            if selected_type == "html" and ext not in (".html", "unknown"):
                continue
            if selected_type == "py" and ext not in (".py", "unknown"):
                continue

            group = data.setdefault(base_name, {"extension": ext, "revisions": []})
            group["revisions"].append(
                {
                    "revision": revision,
                    "description": description,
                    "filename": item.name,
                    "path": str(item),
                    "modified": datetime.fromtimestamp(item.stat().st_mtime),
                    "size": item.stat().st_size,
                }
            )

        for base_name in data:
            data[base_name]["revisions"].sort(key=lambda x: x["revision"], reverse=True)
        return data

    def create_backup(self, filename, description):
        source_path = self.root_dir / filename
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {filename}")

        self.ensure_backup_directory()
        base_name = source_path.stem
        revision_num = self.get_next_backup_number(base_name)
        clean_description = self.sanitize_filename(description)
        backup_filename = f"{base_name}R{revision_num:02d}.backup.{clean_description}"
        backup_path = self.backup_dir / backup_filename
        shutil.copy2(source_path, backup_path)
        return {
            "source": str(source_path),
            "backup": str(backup_path),
            "revision": revision_num,
            "filename": backup_filename,
        }

    def restore_backup(self, backup_filename, target_ext=None):
        backup_path = self.backup_dir / backup_filename
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_filename}")

        match = re.match(BACKUP_PATTERN, backup_filename)
        if not match:
            raise ValueError("Invalid backup filename format.")

        base_name = match.group(1)
        ext = target_ext or self.detect_original_extension(base_name)
        if not ext:
            raise ValueError("Target extension is required for unknown file type.")

        target_path = self.root_dir / f"{base_name}{ext}"
        safety_backup_path = None
        if target_path.exists():
            safety_backup_path = self.root_dir / f"{target_path.name}.before_restore"
            shutil.copy2(target_path, safety_backup_path)

        shutil.copy2(backup_path, target_path)
        return {
            "backup": str(backup_path),
            "target": str(target_path),
            "safety": str(safety_backup_path) if safety_backup_path else None,
        }

    @staticmethod
    def human_size(size_bytes):
        units = ["B", "KB", "MB", "GB"]
        value = float(size_bytes)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024


class BackupGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Backup Manager")
        self.geometry("980x760")
        self.minsize(860, 680)
        self.configure(bg="#f4f6f8")

        self.manager = BackupManager()
        self.selected_type = tk.StringVar(value="both")
        self.description_var = tk.StringVar(value=self.default_description())
        self.root_dir_var = tk.StringVar(value=str(self.manager.root_dir))
        self.status_var = tk.StringVar(value="Ready")
        self.restore_ext_var = tk.StringVar(value=".py")
        self.exclude_gitpushui_var = tk.BooleanVar(value=True)

        self.backup_file_map = {}
        self.restore_file_map = {}

        self._setup_style()
        self._build_ui()
        self.refresh_all()
        self.bind_all("<Control-b>", lambda event: self.backup_selected_and_close())
        self.bind_all("<Control-h>", lambda event: self._set_type_filter("html"))
        self.bind_all("<Control-p>", lambda event: self._set_type_filter("py"))
        self.bind_all("<Control-x>", lambda event: self.destroy())
        def _focus_and_select():
            self.description_entry.focus_set()
            self.description_entry.select_range(0, "end")
        self.after(100, _focus_and_select)

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = "#f4f6f8"
        card = "#ffffff"
        soft = "#eef2f6"
        border = "#d7dde5"
        text = "#1e293b"
        muted = "#64748b"
        accent = "#1f5f8b"
        accent_hover = "#2d78aa"

        self.colors = {
            "bg": bg,
            "card": card,
            "soft": soft,
            "border": border,
            "text": text,
            "muted": muted,
            "accent": accent,
        }

        style.configure("App.TFrame", background=bg)
        style.configure("Card.TFrame", background=card)
        style.configure("Soft.TFrame", background=soft)
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("Header.TLabel", background=bg, foreground=text, font=("Segoe UI Semibold", 20))
        style.configure("Title.TLabel", background=card, foreground=text, font=("Segoe UI Semibold", 13))
        style.configure("CardSub.TLabel", background=card, foreground=muted, font=("Segoe UI", 9))
        style.configure("Chip.TLabel", background=soft, foreground=text, font=("Segoe UI Semibold", 9), padding=(10, 5))

        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8), background=card)
        style.map("TButton", background=[("active", soft)])
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), foreground="white", background=accent, borderwidth=0, padding=(12, 9))
        style.map("Accent.TButton", background=[("active", accent_hover)])
        style.configure("Secondary.TButton", font=("Segoe UI", 10), background=soft, padding=(12, 8))
        style.map("Secondary.TButton", background=[("active", "#e3e9ef")])
        style.configure("Danger.TButton", font=("Segoe UI Semibold", 10), foreground="white", background="#c0392b", borderwidth=0, padding=(12, 9))
        style.map("Danger.TButton", background=[("active", "#e74c3c")])

        style.configure("TLabelframe", background=card, bordercolor=border, relief="solid")
        style.configure("TLabelframe.Label", background=card, foreground=text, font=("Segoe UI Semibold", 10))
        style.configure("TRadiobutton", background=card, foreground=text, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=card, foreground=text, font=("Segoe UI", 10))
        style.configure("TEntry", padding=7)
        style.configure("TCombobox", padding=6)

        style.configure(
            "Treeview",
            background=card,
            fieldbackground=card,
            foreground=text,
            rowheight=30,
            bordercolor=border,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=soft,
            foreground=text,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padding=(8, 8),
        )
        style.map("Treeview", background=[("selected", "#dceefe")], foreground=[("selected", text)])

        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(18, 10))
        style.map("TNotebook.Tab", background=[("selected", card), ("active", soft)])

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, style="App.TFrame", padding=(18, 16, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Backup Manager", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Clear backup and restore for HTML and Python files in the selected folder", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(header, text="Refresh", style="Secondary.TButton", command=self.refresh_all).grid(row=0, column=1, rowspan=2, sticky="e")

        top = ttk.Frame(self, style="Card.TFrame", padding=16)
        top.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(4, weight=1)

        ttk.Label(top, text="Folder", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.root_dir_var).grid(row=0, column=1, sticky="ew", padx=(10, 10))
        ttk.Button(top, text="Apply", style="Secondary.TButton", command=self.apply_folder_from_entry).grid(row=0, column=2, sticky="ew")
        ttk.Button(top, text="Browse", style="Secondary.TButton", command=self.choose_folder).grid(row=0, column=3, sticky="ew", padx=(10, 0))
        ttk.Button(top, text="Open Folder", style="Secondary.TButton", command=self.open_working_folder).grid(row=0, column=4, sticky="ew", padx=(10, 0))

        type_row = ttk.Frame(top, style="Card.TFrame")
        type_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        type_row.columnconfigure(7, weight=1)

        ttk.Label(type_row, text="Show", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(type_row, text="All files", value="both", variable=self.selected_type, command=self.refresh_all).grid(row=0, column=1, padx=(12, 4), sticky="w")
        ttk.Radiobutton(type_row, text="HTML only", value="html", variable=self.selected_type, command=self.refresh_all).grid(row=0, column=2, padx=4, sticky="w")
        ttk.Radiobutton(type_row, text="Python only", value="py", variable=self.selected_type, command=self.refresh_all).grid(row=0, column=3, padx=4, sticky="w")

        self.html_count_label = ttk.Label(type_row, text="HTML: 0", style="Chip.TLabel")
        self.html_count_label.grid(row=0, column=4, padx=(18, 6), sticky="w")
        self.py_count_label = ttk.Label(type_row, text="Python: 0", style="Chip.TLabel")
        self.py_count_label.grid(row=0, column=5, padx=6, sticky="w")
        self.backup_count_label = ttk.Label(type_row, text="Backups: 0", style="Chip.TLabel")
        self.backup_count_label.grid(row=0, column=6, padx=6, sticky="w")
        ttk.Checkbutton(
            type_row,
            text="Exclude GITpushUI.py",
            variable=self.exclude_gitpushui_var,
            command=self.on_toggle_exclude_gitpushui,
        ).grid(row=0, column=7, padx=(14, 0), sticky="e")

        content = ttk.Frame(self, style="App.TFrame")
        content.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 10))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(content)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.backup_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=16)
        self.restore_tab = ttk.Frame(self.notebook, style="Card.TFrame", padding=16)
        self.notebook.add(self.backup_tab, text="Backup")
        self.notebook.add(self.restore_tab, text="Restore")

        self._build_backup_tab()
        self._build_restore_tab()

        status = ttk.Frame(self, style="App.TFrame", padding=(18, 0, 18, 14))
        status.grid(row=3, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")

    def _build_backup_tab(self):
        self.backup_tab.columnconfigure(0, weight=1)

        ttk.Label(self.backup_tab, text="Backup files in this folder", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.backup_tab, text="Pick a file and save a new revision", style="CardSub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 12))

        desc = ttk.Frame(self.backup_tab, style="Card.TFrame")
        desc.grid(row=2, column=0, sticky="new", pady=(0, 12))
        desc.columnconfigure(1, weight=1)
        ttk.Label(desc, text="Backup label", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w")
        self.description_entry = ttk.Entry(desc, textvariable=self.description_var)
        self.description_entry.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        ttk.Button(desc, text="Use Time", style="Secondary.TButton", command=self.set_timestamp_description).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(desc, text="Clear", style="Secondary.TButton", command=lambda: self.description_var.set("")).grid(row=0, column=3)

        file_box = ttk.LabelFrame(self.backup_tab, text="Files available to back up", padding=12)
        file_box.grid(row=3, column=0, sticky="ew")
        file_box.columnconfigure(0, weight=1)

        self.backup_tree = ttk.Treeview(
            file_box,
            columns=("filetype", "filename", "nextrev"),
            show="headings",
            selectmode="browse",
            height=4,
        )
        self.backup_tree.heading("filetype", text="Type")
        self.backup_tree.heading("filename", text="File")
        self.backup_tree.heading("nextrev", text="Next backup")
        self.backup_tree.column("filetype", width=90, anchor="center")
        self.backup_tree.column("filename", width=520, anchor="w")
        self.backup_tree.column("nextrev", width=120, anchor="center")
        self.backup_tree.grid(row=0, column=0, sticky="ew")
        self.backup_tree.bind("<Double-1>", lambda event: self.backup_selected_file())

        backup_scroll = ttk.Scrollbar(file_box, orient="vertical", command=self.backup_tree.yview)
        backup_scroll.grid(row=0, column=1, sticky="ns")
        self.backup_tree.configure(yscrollcommand=backup_scroll.set)

        backup_actions = ttk.Frame(self.backup_tab, style="Card.TFrame")
        backup_actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))

        ttk.Button(backup_actions, text="Backup Selected", style="Accent.TButton", command=self.backup_selected_file).grid(row=0, column=0, sticky="ew")
        ttk.Label(backup_actions, text="Double-click", style="Muted.TLabel", anchor="center").grid(row=1, column=0, sticky="ew")

        ttk.Button(backup_actions, text="Backup All Listed", style="Secondary.TButton", command=self.backup_all_visible).grid(row=0, column=1, sticky="ew", padx=(10, 0))
        ttk.Label(backup_actions, text="", style="Muted.TLabel", anchor="center").grid(row=1, column=1, sticky="ew", padx=(10, 0))

        ttk.Button(backup_actions, text="Backup Selected & Close", style="Danger.TButton", command=self.backup_selected_and_close).grid(row=0, column=2, sticky="ew", padx=(10, 0))
        ttk.Label(backup_actions, text="Ctrl+B", style="Muted.TLabel", anchor="center").grid(row=1, column=2, sticky="ew", padx=(10, 0))

        ttk.Button(backup_actions, text="Close", style="Danger.TButton", command=self.destroy).grid(row=0, column=3, sticky="ew", padx=(10, 0))
        ttk.Label(backup_actions, text="Ctrl+X", style="Muted.TLabel", anchor="center").grid(row=1, column=3, sticky="ew", padx=(10, 0))

    def _build_restore_tab(self):
        self.restore_tab.columnconfigure(0, weight=1)
        self.restore_tab.rowconfigure(2, weight=1)

        ttk.Label(self.restore_tab, text="Restore saved backups", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.restore_tab, text="Choose a revision and restore it back into the folder", style="CardSub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 12))

        restore_box = ttk.LabelFrame(self.restore_tab, text="Available backup revisions", padding=12)
        restore_box.grid(row=2, column=0, sticky="nsew")
        restore_box.columnconfigure(0, weight=1)
        restore_box.rowconfigure(0, weight=1)

        self.restore_tree = ttk.Treeview(
            restore_box,
            columns=("file", "type", "rev", "saved", "note"),
            show="headings",
            selectmode="browse",
        )
        self.restore_tree.heading("file", text="File")
        self.restore_tree.heading("type", text="Type")
        self.restore_tree.heading("rev", text="Revision")
        self.restore_tree.heading("saved", text="Saved")
        self.restore_tree.heading("note", text="Backup label")
        self.restore_tree.column("file", width=240, anchor="w")
        self.restore_tree.column("type", width=90, anchor="center")
        self.restore_tree.column("rev", width=90, anchor="center")
        self.restore_tree.column("saved", width=160, anchor="center")
        self.restore_tree.column("note", width=360, anchor="w")
        self.restore_tree.grid(row=0, column=0, sticky="nsew")
        self.restore_tree.bind("<Double-1>", lambda event: self.restore_selected_backup())
        self.restore_tree.bind("<<TreeviewSelect>>", lambda event: self.populate_restore_extension())

        restore_scroll = ttk.Scrollbar(restore_box, orient="vertical", command=self.restore_tree.yview)
        restore_scroll.grid(row=0, column=1, sticky="ns")
        self.restore_tree.configure(yscrollcommand=restore_scroll.set)

        restore_actions = ttk.Frame(self.restore_tab, style="Card.TFrame")
        restore_actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(restore_actions, text="Restore Selected", style="Accent.TButton", command=self.restore_selected_backup).grid(row=0, column=0, sticky="w")
        ttk.Button(restore_actions, text="Open Backup Folder", style="Secondary.TButton", command=self.open_backup_folder).grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(restore_actions, text="If file type is unknown, restore as", background=self.colors["card"], foreground=self.colors["muted"], font=("Segoe UI", 10)).grid(row=0, column=2, padx=(18, 8), sticky="w")
        ttk.Combobox(restore_actions, textvariable=self.restore_ext_var, values=(".py", ".html"), state="readonly", width=8).grid(row=0, column=3, sticky="w")

    def default_description(self):
        return datetime.now().strftime("backup %Y-%m-%d %H-%M")

    def set_status(self, text):
        self.status_var.set(text)
        self.update_idletasks()

    def _set_type_filter(self, file_type):
        self.selected_type.set(file_type)
        self.refresh_all()


    def apply_folder_from_entry(self):
        selected = self.root_dir_var.get().strip()
        if not selected:
            messagebox.showinfo("Folder", "Enter a folder path first.")
            return
        path = Path(selected).expanduser()
        if not path.exists() or not path.is_dir():
            messagebox.showerror("Invalid folder", f"Folder not found:\n{path}")
            return
        self.manager = BackupManager(root_dir=path, exclude_gitpushui=self.exclude_gitpushui_var.get())
        self.root_dir_var.set(str(self.manager.root_dir))
        self.refresh_all()

    def choose_folder(self):
        selected = filedialog.askdirectory(initialdir=str(self.manager.root_dir), title="Choose working folder")
        if not selected:
            return
        self.manager = BackupManager(root_dir=selected, exclude_gitpushui=self.exclude_gitpushui_var.get())
        self.root_dir_var.set(str(self.manager.root_dir))
        self.refresh_all()

    def on_toggle_exclude_gitpushui(self):
        self.manager.exclude_gitpushui = self.exclude_gitpushui_var.get()
        self.refresh_all()

    def open_path(self, path):
        path = str(path)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def open_working_folder(self):
        self.open_path(self.manager.root_dir)

    def open_backup_folder(self):
        self.manager.ensure_backup_directory()
        self.open_path(self.manager.backup_dir)

    def refresh_all(self):
        html_count, py_count = self.manager.get_counts()
        self.html_count_label.config(text=f"HTML: {html_count}")
        self.py_count_label.config(text=f"Python: {py_count}")

        self.refresh_backup_files_list()
        total_backups = self.refresh_restore_list()
        self.backup_count_label.config(text=f"Backups: {total_backups}")

        if not self.description_var.get().strip():
            self.description_var.set(self.default_description())

        listed_backup_files = len(self.backup_tree.get_children())
        gitpushui_state = "excluded" if self.exclude_gitpushui_var.get() else "included"
        self.set_status(
            f"Folder: {self.manager.root_dir} | Showing {listed_backup_files} file(s) to back up and {total_backups} backup revision(s) | GITpushUI.py {gitpushui_state}"
        )

    def refresh_backup_files_list(self):
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)
        self.backup_file_map.clear()

        files = self.manager.get_files_by_type(self.selected_type.get())
        backup_data = self.manager.get_backup_files(self.selected_type.get())

        for filename in files:
            ext = Path(filename).suffix.lower()
            filetype = "HTML" if ext == ".html" else "Python"
            base = Path(filename).stem
            latest = backup_data.get(base, {}).get("revisions", [])
            next_rev = f"R{(latest[0]['revision'] + 1) if latest else 1:02d}"
            row = self.backup_tree.insert("", "end", values=(filetype, filename, next_rev))
            self.backup_file_map[row] = filename

        if len(files) == 1:
            only_row = self.backup_tree.get_children()[0]
            self.backup_tree.selection_set(only_row)
            self.backup_tree.focus(only_row)

    def refresh_restore_list(self):
        for item in self.restore_tree.get_children():
            self.restore_tree.delete(item)
        self.restore_file_map.clear()

        backup_data = self.manager.get_backup_files(self.selected_type.get())
        count = 0
        for base_name in sorted(backup_data.keys(), key=str.lower):
            ext = backup_data[base_name]["extension"]
            filetype = "HTML" if ext == ".html" else "Python" if ext == ".py" else "Unknown"
            for rev in backup_data[base_name]["revisions"]:
                row = self.restore_tree.insert(
                    "",
                    "end",
                    values=(
                        base_name,
                        filetype,
                        f"R{rev['revision']:02d}",
                        rev["modified"].strftime("%Y-%m-%d %H:%M"),
                        rev["description"],
                    ),
                )
                self.restore_file_map[row] = {
                    "base_name": base_name,
                    "extension": ext,
                    "backup": rev,
                }
                count += 1
        return count

    def get_selected_backup_source(self):
        selection = self.backup_tree.selection()
        if not selection:
            return None
        return self.backup_file_map.get(selection[0])

    def get_selected_restore_backup(self):
        selection = self.restore_tree.selection()
        if not selection:
            return None
        return self.restore_file_map.get(selection[0])

    def set_timestamp_description(self):
        self.description_var.set(self.default_description())

    def backup_selected_file(self):
        filename = self.get_selected_backup_source()
        if not filename:
            messagebox.showinfo("Select file", "Select a file from the Backup tab first.")
            return

        description = self.description_var.get().strip() or self.default_description()
        try:
            result = self.manager.create_backup(filename, description)
            self.refresh_all()
            self.select_restore_by_filename(result["filename"])
            self.notebook.select(self.restore_tab)
            self.set_status(f"Created {result['filename']}")
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc))

    def backup_selected_and_close(self):
        filename = self.get_selected_backup_source()
        if not filename:
            messagebox.showinfo("Select file", "Select a file from the Backup tab first.")
            return

        description = self.description_var.get().strip() or self.default_description()
        try:
            result = self.manager.create_backup(filename, description)
            self.set_status(f"Created {result['filename']}")
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc))

    def backup_all_visible(self):
        rows = self.backup_tree.get_children()
        if not rows:
            messagebox.showinfo("No files", "There are no files listed to back up.")
            return

        description = self.description_var.get().strip() or self.default_description()
        count = 0
        errors = []
        last_filename = None

        for row in rows:
            filename = self.backup_file_map.get(row)
            if not filename:
                continue
            try:
                result = self.manager.create_backup(filename, description)
                count += 1
                last_filename = result["filename"]
            except Exception as exc:
                errors.append(f"{filename}: {exc}")

        self.refresh_all()
        if last_filename:
            self.select_restore_by_filename(last_filename)

        if errors:
            messagebox.showwarning(
                "Backup finished",
                f"Created {count} backup(s).\n\nSome files had issues:\n" + "\n".join(errors[:10]),
            )
        else:
            self.set_status(f"Created {count} backup(s)")
            self.notebook.select(self.restore_tab)

    def populate_restore_extension(self):
        data = self.get_selected_restore_backup()
        if not data:
            return
        if data["extension"] in (".py", ".html"):
            self.restore_ext_var.set(data["extension"])

    def restore_selected_backup(self):
        data = self.get_selected_restore_backup()
        if not data:
            messagebox.showinfo("Select backup", "Select a backup revision from the Restore tab first.")
            return

        target_ext = data["extension"] if data["extension"] != "unknown" else self.restore_ext_var.get()
        backup_filename = data["backup"]["filename"]
        target_name = f"{data['base_name']}{target_ext}"

        ok = messagebox.askyesno(
            "Confirm restore",
            f"Restore this backup?\n\n{backup_filename}\n\nTarget file:\n{target_name}\n\nIf the target already exists, a .before_restore safety copy will be created.",
        )
        if not ok:
            return

        try:
            result = self.manager.restore_backup(backup_filename, target_ext=target_ext)
            self.refresh_all()
            message = f"Restored to:\n{result['target']}"
            if result["safety"]:
                message += f"\n\nSafety copy created:\n{result['safety']}"
            self.set_status(f"Restored {backup_filename}")
            messagebox.showinfo("Restore complete", message)
        except Exception as exc:
            messagebox.showerror("Restore failed", str(exc))

    def select_restore_by_filename(self, backup_filename):
        for row, data in self.restore_file_map.items():
            if data["backup"]["filename"] == backup_filename:
                self.restore_tree.selection_set(row)
                self.restore_tree.focus(row)
                self.restore_tree.see(row)
                self.populate_restore_extension()
                return


if __name__ == "__main__":
    app = BackupGUI()
    app.mainloop()