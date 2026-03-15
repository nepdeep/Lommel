import os
import glob
import shutil
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


BACKUP_DIR = "backup"
BASE_EXCLUDED_NAMES = {
    "backup.py",
    "bkup_html.py",
    "bkup_python.py",
    "bkup_combined.py",
    "gitpushui.py",
}
BACKUP_PATTERN = r"^(.+)R(\d+)\.backup\.(.+)$"


class BackupManager:
    def __init__(self, root_dir=None, backup_dir=BACKUP_DIR):
        self.root_dir = Path(root_dir or os.getcwd()).resolve()
        self.backup_dir = self.root_dir / backup_dir

    def get_excluded_names(self):
        excluded = {name.lower() for name in BASE_EXCLUDED_NAMES}
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
        return cleaned[:60].strip(" ._") or "backup"

    def get_next_backup_number(self, base_filename):
        revision = 1
        while True:
            pattern = str(self.backup_dir / f"{base_filename}R{revision:02d}.*")
            if not glob.glob(pattern):
                return revision
            revision += 1

    def detect_available_files(self):
        html_files = sorted(
            [p.name for p in self.root_dir.glob("*.html") if p.is_file()],
            key=str.lower,
        )

        excluded_py_names = self.get_excluded_names()
        py_files = sorted(
            [
                p.name
                for p in self.root_dir.glob("*.py")
                if p.is_file() and p.name.lower() not in excluded_py_names
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
        if selected_type == "both":
            return sorted(set(html_files + py_files), key=str.lower)
        return []

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

            group = data.setdefault(
                base_name,
                {
                    "extension": ext,
                    "revisions": [],
                },
            )
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
        detected_ext = self.detect_original_extension(base_name)
        ext = target_ext or detected_ext
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
        self.geometry("1220x760")
        self.minsize(1040, 640)
        self.configure(bg="#eef1f5")

        self.manager = BackupManager()
        self.selected_type = tk.StringVar(value="both")
        self.search_var = tk.StringVar()
        self.description_var = tk.StringVar(value=self.default_description())
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.root_dir_var = tk.StringVar(value=str(self.manager.root_dir))
        self.ext_choice_var = tk.StringVar(value=".py")
        self.source_map = {}
        self.backup_map = {}
        self.current_backup_rows = []

        self._setup_style()
        self._build_ui()
        self.refresh_all()

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = "#eef1f5"
        card = "#ffffff"
        soft = "#f7f9fc"
        accent = "#1f4d7a"
        accent2 = "#3d7ab8"
        text = "#1f2937"
        muted = "#64748b"
        border = "#d9e2ec"

        self.colors = {
            "bg": bg,
            "card": card,
            "soft": soft,
            "accent": accent,
            "accent2": accent2,
            "text": text,
            "muted": muted,
            "border": border,
        }

        style.configure("App.TFrame", background=bg)
        style.configure("Card.TFrame", background=card, relief="flat")
        style.configure("Soft.TFrame", background=soft)
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", background=card, foreground=text, font=("Segoe UI Semibold", 14))
        style.configure("CardSub.TLabel", background=card, foreground=muted, font=("Segoe UI", 9))
        style.configure("Section.TLabelframe", background=card, bordercolor=border, relief="solid")
        style.configure("Section.TLabelframe.Label", background=card, foreground=text, font=("Segoe UI Semibold", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8), background=card)
        style.map("TButton", background=[("active", soft)])
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(12, 8), foreground="white", background=accent, borderwidth=0)
        style.map("Accent.TButton", background=[("active", accent2)])
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 8), background=soft)
        style.map("Secondary.TButton", background=[("active", "#edf2f7")])
        style.configure("TRadiobutton", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("TEntry", padding=8)
        style.configure("TCombobox", padding=6)
        style.configure(
            "Treeview",
            background=card,
            fieldbackground=card,
            foreground=text,
            bordercolor=border,
            rowheight=30,
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
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", text)])
        style.map("Treeview.Heading", background=[("active", "#e8eef5")])
        style.configure("Status.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="App.TFrame", padding=(20, 18, 20, 8))
        header.grid(row=0, column=0, sticky="nsew")
        header.columnconfigure(0, weight=1)

        title_frame = ttk.Frame(header, style="App.TFrame")
        title_frame.grid(row=0, column=0, sticky="w")
        ttk.Label(title_frame, text="Backup Manager", font=("Segoe UI Semibold", 22), background=self.colors["bg"], foreground=self.colors["text"]).grid(row=0, column=0, sticky="w")
        ttk.Label(title_frame, text="Elegant local backup and restore for HTML and Python files", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

        actions = ttk.Frame(header, style="App.TFrame")
        actions.grid(row=0, column=1, sticky="e")
        ttk.Button(actions, text="Refresh", style="Secondary.TButton", command=self.refresh_all).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Open Backup Folder", style="Secondary.TButton", command=self.open_backup_folder).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Open Working Folder", style="Accent.TButton", command=self.open_working_folder).grid(row=0, column=2)

        body = ttk.Frame(self, style="App.TFrame", padding=(20, 8, 20, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

        status_bar = ttk.Frame(self, style="App.TFrame", padding=(20, 0, 20, 14))
        status_bar.grid(row=2, column=0, sticky="ew")
        status_bar.columnconfigure(0, weight=1)
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_bar, textvariable=self.root_dir_var, style="Status.TLabel").grid(row=0, column=1, sticky="e")

    def _build_left_panel(self, parent):
        left = ttk.Frame(parent, style="Card.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        left.configure(width=330)
        left.grid_propagate(False)

        ttk.Label(left, text="Workspace", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(left, text="Choose folder, file type, and backup options", style="CardSub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 12))

        folder_frame = ttk.LabelFrame(left, text="Folder", style="Section.TLabelframe", padding=12)
        folder_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        folder_frame.columnconfigure(0, weight=1)
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.root_dir_var)
        self.folder_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(folder_frame, text="Browse", style="Secondary.TButton", command=self.choose_folder).grid(row=1, column=0, sticky="ew", pady=(10, 0))

        type_frame = ttk.LabelFrame(left, text="File Type", style="Section.TLabelframe", padding=12)
        type_frame.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        ttk.Radiobutton(type_frame, text="HTML", value="html", variable=self.selected_type, command=self.refresh_all).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(type_frame, text="Python", value="py", variable=self.selected_type, command=self.refresh_all).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Radiobutton(type_frame, text="Both", value="both", variable=self.selected_type, command=self.refresh_all).grid(row=2, column=0, sticky="w", pady=(6, 0))

        desc_frame = ttk.LabelFrame(left, text="Backup Description", style="Section.TLabelframe", padding=12)
        desc_frame.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        desc_frame.columnconfigure(0, weight=1)
        ttk.Entry(desc_frame, textvariable=self.description_var).grid(row=0, column=0, sticky="ew")
        helper = ttk.Frame(desc_frame, style="Card.TFrame")
        helper.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        helper.columnconfigure((0, 1), weight=1)
        ttk.Button(helper, text="Use Timestamp", style="Secondary.TButton", command=self.set_timestamp_description).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(helper, text="Clear", style="Secondary.TButton", command=lambda: self.description_var.set("")).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        actions_frame = ttk.LabelFrame(left, text="Actions", style="Section.TLabelframe", padding=12)
        actions_frame.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        actions_frame.columnconfigure(0, weight=1)
        ttk.Button(actions_frame, text="Backup Selected File", style="Accent.TButton", command=self.backup_selected_file).grid(row=0, column=0, sticky="ew")
        ttk.Button(actions_frame, text="Backup All Visible Files", style="Secondary.TButton", command=self.backup_all_visible).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions_frame, text="Restore Selected Revision", style="Secondary.TButton", command=self.restore_selected_backup).grid(row=2, column=0, sticky="ew", pady=(10, 0))

        extras_frame = ttk.LabelFrame(left, text="Extras", style="Section.TLabelframe", padding=12)
        extras_frame.grid(row=6, column=0, sticky="ew")
        extras_frame.columnconfigure(0, weight=1)
        ttk.Checkbutton(extras_frame, text="Auto refresh after actions", variable=self.auto_refresh_var).grid(row=0, column=0, sticky="w")
        ttk.Button(extras_frame, text="Copy Selected Backup Name", style="Secondary.TButton", command=self.copy_selected_backup_name).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(extras_frame, text="Open Selected Backup File", style="Secondary.TButton", command=self.open_selected_backup_file).grid(row=2, column=0, sticky="ew", pady=(10, 0))

    def _build_right_panel(self, parent):
        right = ttk.Frame(parent, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        top_card = ttk.Frame(right, style="Card.TFrame", padding=16)
        top_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        top_card.columnconfigure(0, weight=1)

        top_header = ttk.Frame(top_card, style="Card.TFrame")
        top_header.grid(row=0, column=0, sticky="ew")
        top_header.columnconfigure(0, weight=1)
        ttk.Label(top_header, text="Source Files", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top_header, text="Select a working file to back up", style="CardSub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

        search_row = ttk.Frame(top_card, style="Card.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(12, 10))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Filter:", background=self.colors["card"], foreground=self.colors["muted"], font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=(0, 8))
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew")
        search_entry.bind("<KeyRelease>", lambda event: self.refresh_source_tree())

        source_tree_wrap = ttk.Frame(top_card, style="Card.TFrame")
        source_tree_wrap.grid(row=2, column=0, sticky="nsew")
        source_tree_wrap.columnconfigure(0, weight=1)
        source_tree_wrap.rowconfigure(0, weight=1)

        self.source_tree = ttk.Treeview(
            source_tree_wrap,
            columns=("type", "nextrev", "status"),
            show="headings",
            selectmode="browse",
            height=11,
        )
        self.source_tree.heading("type", text="Type")
        self.source_tree.heading("nextrev", text="Next Rev")
        self.source_tree.heading("status", text="Name")
        self.source_tree.column("type", width=80, anchor="center")
        self.source_tree.column("nextrev", width=90, anchor="center")
        self.source_tree.column("status", width=520, anchor="w")
        self.source_tree.grid(row=0, column=0, sticky="nsew")
        self.source_tree.bind("<<TreeviewSelect>>", lambda event: self.sync_backup_selection_by_source())
        self.source_tree.bind("<Double-1>", lambda event: self.backup_selected_file())

        source_scroll = ttk.Scrollbar(source_tree_wrap, orient="vertical", command=self.source_tree.yview)
        source_scroll.grid(row=0, column=1, sticky="ns")
        self.source_tree.configure(yscrollcommand=source_scroll.set)

        bottom_card = ttk.Frame(right, style="Card.TFrame", padding=16)
        bottom_card.grid(row=1, column=0, sticky="nsew")
        bottom_card.columnconfigure(0, weight=1)
        bottom_card.rowconfigure(1, weight=1)

        bottom_header = ttk.Frame(bottom_card, style="Card.TFrame")
        bottom_header.grid(row=0, column=0, sticky="ew")
        bottom_header.columnconfigure(0, weight=1)
        ttk.Label(bottom_header, text="Available Backups", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(bottom_header, text="Browse revisions and restore any selected backup", style="CardSub.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

        backup_tree_wrap = ttk.Frame(bottom_card, style="Card.TFrame")
        backup_tree_wrap.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        backup_tree_wrap.columnconfigure(0, weight=1)
        backup_tree_wrap.rowconfigure(0, weight=1)

        self.backup_tree = ttk.Treeview(
            backup_tree_wrap,
            columns=("file", "rev", "modified", "size", "description"),
            show="headings",
            selectmode="browse",
            height=13,
        )
        self.backup_tree.heading("file", text="Base File")
        self.backup_tree.heading("rev", text="Rev")
        self.backup_tree.heading("modified", text="Modified")
        self.backup_tree.heading("size", text="Size")
        self.backup_tree.heading("description", text="Description")
        self.backup_tree.column("file", width=220, anchor="w")
        self.backup_tree.column("rev", width=70, anchor="center")
        self.backup_tree.column("modified", width=160, anchor="center")
        self.backup_tree.column("size", width=90, anchor="center")
        self.backup_tree.column("description", width=420, anchor="w")
        self.backup_tree.grid(row=0, column=0, sticky="nsew")
        self.backup_tree.bind("<Double-1>", lambda event: self.restore_selected_backup())
        self.backup_tree.bind("<<TreeviewSelect>>", lambda event: self.populate_extension_choice())

        backup_scroll = ttk.Scrollbar(backup_tree_wrap, orient="vertical", command=self.backup_tree.yview)
        backup_scroll.grid(row=0, column=1, sticky="ns")
        self.backup_tree.configure(yscrollcommand=backup_scroll.set)

        details = ttk.Frame(bottom_card, style="Card.TFrame")
        details.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        details.columnconfigure(2, weight=1)
        ttk.Label(details, text="Unknown type restore as:", background=self.colors["card"], foreground=self.colors["muted"], font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        ext_box = ttk.Combobox(details, textvariable=self.ext_choice_var, values=(".py", ".html"), state="readonly", width=8)
        ext_box.grid(row=0, column=1, sticky="w", padx=(10, 18))
        ttk.Label(details, text="Double-click a row to restore quickly", background=self.colors["card"], foreground=self.colors["muted"], font=("Segoe UI", 10)).grid(row=0, column=2, sticky="e")

    def default_description(self):
        return datetime.now().strftime("backup %Y-%m-%d %H-%M")

    def set_status(self, text):
        self.status_var.set(text)
        self.update_idletasks()

    def choose_folder(self):
        selected = filedialog.askdirectory(initialdir=str(self.manager.root_dir), title="Choose working folder")
        if not selected:
            return
        self.manager = BackupManager(root_dir=selected)
        self.root_dir_var.set(str(self.manager.root_dir))
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

    def open_backup_folder(self):
        self.manager.ensure_backup_directory()
        self.open_path(self.manager.backup_dir)

    def open_working_folder(self):
        self.open_path(self.manager.root_dir)

    def refresh_all(self):
        self.refresh_source_tree()
        self.refresh_backup_tree()
        if not self.description_var.get().strip():
            self.description_var.set(self.default_description())
        total_sources = len(self.source_tree.get_children())
        total_backups = len(self.backup_tree.get_children())
        self.set_status(f"Loaded {total_sources} source file(s) and {total_backups} backup revision(s)")

    def refresh_source_tree(self):
        for item in self.source_tree.get_children():
            self.source_tree.delete(item)
        self.source_map.clear()

        selected_type = self.selected_type.get()
        files = self.manager.get_files_by_type(selected_type)
        backup_data = self.manager.get_backup_files(selected_type)
        search = self.search_var.get().strip().lower()

        for filename in files:
            if search and search not in filename.lower():
                continue
            ext = Path(filename).suffix.lower().replace(".", "").upper()
            base = Path(filename).stem
            latest_rev = backup_data.get(base, {}).get("revisions", [])
            next_rev = f"R{(latest_rev[0]['revision'] + 1) if latest_rev else 1:02d}"
            iid = self.source_tree.insert("", "end", values=(ext, next_rev, filename))
            self.source_map[iid] = filename

    def refresh_backup_tree(self):
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)
        self.backup_map.clear()
        self.current_backup_rows.clear()

        selected_type = self.selected_type.get()
        backup_data = self.manager.get_backup_files(selected_type)
        search = self.search_var.get().strip().lower()

        for base_name in sorted(backup_data.keys(), key=str.lower):
            if search and search not in base_name.lower():
                continue
            for rev in backup_data[base_name]["revisions"]:
                modified = rev["modified"].strftime("%Y-%m-%d %H:%M")
                size = self.manager.human_size(rev["size"])
                row = self.backup_tree.insert(
                    "",
                    "end",
                    values=(base_name, f"R{rev['revision']:02d}", modified, size, rev["description"]),
                )
                self.backup_map[row] = {
                    "base_name": base_name,
                    "backup": rev,
                    "extension": backup_data[base_name]["extension"],
                }
                self.current_backup_rows.append(row)

    def get_selected_source_file(self):
        selection = self.source_tree.selection()
        if not selection:
            return None
        return self.source_map.get(selection[0])

    def get_selected_backup(self):
        selection = self.backup_tree.selection()
        if not selection:
            return None
        return self.backup_map.get(selection[0])

    def set_timestamp_description(self):
        self.description_var.set(self.default_description())

    def backup_selected_file(self):
        filename = self.get_selected_source_file()
        if not filename:
            messagebox.showinfo("Select file", "Select a source file first.")
            return

        description = self.description_var.get().strip() or self.default_description()
        try:
            result = self.manager.create_backup(filename, description)
            self.set_status(f"Created {result['filename']}")
            if self.auto_refresh_var.get():
                self.refresh_all()
                self.select_backup_by_filename(result["filename"])
        except Exception as exc:
            messagebox.showerror("Backup failed", str(exc))

    def backup_all_visible(self):
        visible_rows = self.source_tree.get_children()
        if not visible_rows:
            messagebox.showinfo("No files", "No visible source files to back up.")
            return

        description = self.description_var.get().strip() or self.default_description()
        count = 0
        failed = []
        last_file = None

        for row in visible_rows:
            filename = self.source_map.get(row)
            if not filename:
                continue
            try:
                result = self.manager.create_backup(filename, description)
                count += 1
                last_file = result["filename"]
            except Exception as exc:
                failed.append(f"{filename}: {exc}")

        if self.auto_refresh_var.get():
            self.refresh_all()
        if last_file:
            self.select_backup_by_filename(last_file)

        if failed:
            messagebox.showwarning(
                "Backup completed with issues",
                f"Created {count} backup(s).\n\nIssues:\n" + "\n".join(failed[:10]),
            )
        else:
            self.set_status(f"Created {count} backup(s)")

    def restore_selected_backup(self):
        data = self.get_selected_backup()
        if not data:
            messagebox.showinfo("Select backup", "Select a backup revision first.")
            return

        backup_filename = data["backup"]["filename"]
        target_ext = data["extension"]
        if target_ext == "unknown":
            target_ext = self.ext_choice_var.get()

        target_name = f"{data['base_name']}{target_ext if target_ext != 'unknown' else ''}"
        confirm = messagebox.askyesno(
            "Confirm restore",
            f"Restore:\n{backup_filename}\n\nTo:\n{target_name}\n\nA safety copy will be created if the target already exists.",
        )
        if not confirm:
            return

        try:
            result = self.manager.restore_backup(backup_filename, target_ext=target_ext)
            msg = f"Restored to:\n{result['target']}"
            if result["safety"]:
                msg += f"\n\nSafety copy:\n{result['safety']}"
            self.set_status(f"Restored {backup_filename}")
            if self.auto_refresh_var.get():
                self.refresh_all()
            messagebox.showinfo("Restore complete", msg)
        except Exception as exc:
            messagebox.showerror("Restore failed", str(exc))

    def sync_backup_selection_by_source(self):
        filename = self.get_selected_source_file()
        if not filename:
            return
        base = Path(filename).stem
        for row, data in self.backup_map.items():
            if data["base_name"] == base:
                self.backup_tree.selection_set(row)
                self.backup_tree.focus(row)
                self.backup_tree.see(row)
                self.populate_extension_choice()
                break

    def select_backup_by_filename(self, backup_filename):
        for row, data in self.backup_map.items():
            if data["backup"]["filename"] == backup_filename:
                self.backup_tree.selection_set(row)
                self.backup_tree.focus(row)
                self.backup_tree.see(row)
                self.populate_extension_choice()
                return

    def populate_extension_choice(self):
        data = self.get_selected_backup()
        if not data:
            return
        ext = data["extension"]
        if ext in (".py", ".html"):
            self.ext_choice_var.set(ext)

    def copy_selected_backup_name(self):
        data = self.get_selected_backup()
        if not data:
            messagebox.showinfo("Select backup", "Select a backup revision first.")
            return
        backup_filename = data["backup"]["filename"]
        self.clipboard_clear()
        self.clipboard_append(backup_filename)
        self.set_status(f"Copied {backup_filename}")

    def open_selected_backup_file(self):
        data = self.get_selected_backup()
        if not data:
            messagebox.showinfo("Select backup", "Select a backup revision first.")
            return
        self.open_path(data["backup"]["path"])


if __name__ == "__main__":
    app = BackupGUI()
    app.mainloop()
