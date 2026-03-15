"""
GitPushUI.py  —  Simple Git Push Tool
Just point it at a folder, type a commit message, and hit Push.
"""

import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox

# ── Colours ──────────────────────────────────
BG       = "#0d1117"
SURFACE  = "#161b22"
BORDER   = "#30363d"
GREEN    = "#238636"
GREEN_HV = "#2ea043"
BLUE     = "#1f6feb"
BLUE_HV  = "#388bfd"
YELLOW   = "#d29922"
RED      = "#f85149"
FG       = "#e6edf3"
DIM      = "#8b949e"
MONO     = ("Consolas", 10)
BOLD     = ("Segoe UI Semibold", 11)

# ── Helpers ───────────────────────────────────

def git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=str(cwd),
        text=True, capture_output=True, shell=False
    )

def find_repo(path=None):
    p = Path(path).resolve() if path else Path.cwd().resolve()
    if p.is_file():
        p = p.parent
    for d in [p] + list(p.parents):
        if (d / ".git").exists():
            return d
    return None

def btn(parent, label, cmd, bg, hv, **kw):
    kw.setdefault("padx", 18)
    kw.setdefault("pady", 9)
    b = tk.Button(parent, text=label, command=cmd,
                  bg=bg, fg=FG, activebackground=hv, activeforeground=FG,
                  relief="flat", bd=0, font=BOLD, cursor="hand2", **kw)
    b.bind("<Enter>", lambda e: b.config(bg=hv))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

# ── App ───────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git Push UI")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(600, 480)
        self._center(700, 560)
        self.repo = None
        self._build()
        self.after(100, self._load_default_repo)

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        # ── Top bar ──
        top = tk.Frame(self, bg=SURFACE, pady=12)
        top.pack(fill="x")
        tk.Label(top, text="  Git Push UI", font=("Segoe UI Semibold", 13),
                 bg=SURFACE, fg=FG).pack(side="left")
        btn(top, "Change Folder", self._pick_folder,
            SURFACE, BORDER, pady=5).pack(side="right", padx=10)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Repo path ──
        rf = tk.Frame(self, bg=BG, padx=16, pady=8)
        rf.pack(fill="x")
        tk.Label(rf, text="Folder:", font=BOLD, bg=BG, fg=DIM).pack(side="left")
        self._repo_lbl = tk.Label(rf, text="—", font=MONO, bg=BG, fg=DIM)
        self._repo_lbl.pack(side="left", padx=6)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Status ──
        sf = tk.Frame(self, bg=BG, padx=16, pady=10)
        sf.pack(fill="x")
        self._status_var = tk.StringVar(value="No repo loaded")
        self._status_lbl = tk.Label(sf, textvariable=self._status_var,
                                    font=("Segoe UI", 10), bg=BG, fg=DIM,
                                    wraplength=660, justify="left")
        self._status_lbl.pack(anchor="w")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Commit message ──
        mf = tk.Frame(self, bg=BG, padx=16, pady=14)
        mf.pack(fill="x")
        tk.Label(mf, text="Commit message:", font=BOLD,
                 bg=BG, fg=DIM).pack(anchor="w")
        mr = tk.Frame(mf, bg=BG)
        mr.pack(fill="x", pady=(6, 0))
        self._msg = tk.Entry(mr, font=MONO, bg=SURFACE, fg=FG,
                             insertbackground=FG, relief="flat",
                             highlightthickness=1,
                             highlightbackground=BORDER,
                             highlightcolor=GREEN)
        self._msg.pack(side="left", fill="x", expand=True, ipady=9, padx=(0,10))
        self._msg.bind("<Return>", lambda e: self._push())

        # ── Big push button ──
        self._push_btn = btn(mr, "⬆  Push to GitHub", self._push, BLUE, BLUE_HV)
        self._push_btn.pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=(10,0))

        # ── Log ──
        lh = tk.Frame(self, bg=BG, padx=16, pady=6)
        lh.pack(fill="x")
        tk.Label(lh, text="Log", font=BOLD, bg=BG, fg=DIM).pack(side="left")
        tk.Button(lh, text="Clear", font=("Segoe UI", 9),
                  bg=BG, fg=DIM, activebackground=SURFACE,
                  relief="flat", bd=0, cursor="hand2",
                  command=self._clear_log).pack(side="right")

        self._log_box = scrolledtext.ScrolledText(
            self, font=MONO, bg=SURFACE, fg=FG,
            insertbackground=FG, relief="flat",
            state="disabled", wrap="word", padx=12, pady=10,
            highlightthickness=0)
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(0,16))
        self._log_box.tag_config("ok",   foreground=GREEN)
        self._log_box.tag_config("err",  foreground=RED)
        self._log_box.tag_config("warn", foreground=YELLOW)
        self._log_box.tag_config("dim",  foreground=DIM)

    # ── Repo loading ──────────────────────────

    def _load_default_repo(self):
        start = sys.argv[1] if len(sys.argv) > 1 else None
        repo  = find_repo(start)
        if repo:
            self._set_repo(repo)
        else:
            self._log("No repo found — use 'Change Folder' to pick one.", "warn")
            self._status_var.set("No repo loaded")

    def _pick_folder(self):
        d = filedialog.askdirectory(title="Select your project folder")
        if not d:
            return
        repo = find_repo(d)
        if repo:
            self._set_repo(repo)
        else:
            if messagebox.askyesno("Init repo?",
                    f"No git repo found in:\n{d}\n\nInitialise one here?"):
                r = git(["init"], Path(d))
                if r.returncode == 0:
                    self._set_repo(Path(d))
                    self._log("git init done. Add a remote URL via:\n"
                              "  git remote add origin https://github.com/USER/REPO.git", "warn")
                else:
                    messagebox.showerror("Error", r.stderr)

    def _set_repo(self, repo):
        self.repo = repo
        self._repo_lbl.config(text=str(repo))
        self._refresh_status()
        self._log(f"Loaded: {repo}", "dim")

    def _refresh_status(self):
        if not self.repo:
            return
        r = git(["status", "--short"], self.repo)
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        remote_r = git(["remote", "get-url", "origin"], self.repo)
        remote = remote_r.stdout.strip() if remote_r.returncode == 0 else None

        if not remote:
            self._status_var.set("No remote set — add one with: git remote add origin <url>")
            self._status_lbl.config(fg=RED)
        elif lines:
            self._status_var.set(f"{len(lines)} file(s) changed — ready to push")
            self._status_lbl.config(fg=YELLOW)
        else:
            self._status_var.set("Everything up to date")
            self._status_lbl.config(fg=GREEN)

    # ── Core push logic ───────────────────────

    def _push(self):
        if not self.repo:
            messagebox.showwarning("No folder", "Please select a project folder first.")
            return

        msg = self._msg.get().strip()
        if not msg:
            messagebox.showwarning("No message", "Please enter a commit message.")
            self._msg.focus_set()
            return

        remote_r = git(["remote", "get-url", "origin"], self.repo)
        if remote_r.returncode != 0:
            messagebox.showerror(
                "No remote",
                "No GitHub remote is set.\n\n"
                "Run this once in your project folder:\n"
                "  git remote add origin https://github.com/USER/REPO.git")
            return

        self._push_btn.config(state="disabled", text="Pushing...")
        self.update()

        try:
            # 1. Stage everything
            self._log("Staging all files...", "dim")
            r = git(["add", "."], self.repo)
            if r.returncode != 0:
                self._log(r.stderr or "git add failed", "err"); return

            # 2. Commit (skip if nothing staged)
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(self.repo), shell=False)
            if staged.returncode == 0:
                self._log("Nothing new to commit — pushing existing commits.", "dim")
            else:
                self._log(f'Committing: "{msg}"', "dim")
                r = git(["commit", "-m", msg], self.repo)
                if r.stdout.strip(): self._log(r.stdout.strip())
                if r.returncode != 0:
                    self._log(r.stderr or "Commit failed", "err"); return
                self._log("Committed.", "ok")

            # 3. Push
            branch_r = git(["branch", "--show-current"], self.repo)
            branch   = branch_r.stdout.strip() or "main"

            # If local branch is 'master', rename it to 'main' to match GitHub default
            if branch == "master":
                git(["branch", "-M", "main"], self.repo)
                branch = "main"

            self._log(f"Pushing branch '{branch}' to GitHub...", "dim")

            r = git(["push", "--set-upstream", "origin", branch], self.repo)
            if r.stdout.strip(): self._log(r.stdout.strip())
            if r.stderr.strip(): self._log(r.stderr.strip(),
                                           "dim" if r.returncode == 0 else "err")

            if r.returncode == 0:
                self._log("All files pushed to GitHub successfully!", "ok")
                self._msg.delete(0, "end")
                self._refresh_status()
            else:
                stderr = r.stderr.lower()
                if any(k in stderr for k in ("401","403","authentication",
                                              "credential","permission denied",
                                              "could not read")):
                    self._log(
                        "Auth failed — Windows should show a login popup.\n"
                        "If not, run this once in a terminal:\n"
                        "  git push\n"
                        "and sign in when prompted.", "warn")
                elif "rejected" in stderr:
                    self._log(
                        "Push rejected — remote has changes you don't have.\n"
                        "Run:  git pull  then try again.", "warn")

        finally:
            self._push_btn.config(state="normal", text="⬆  Push to GitHub")

    # ── Log helpers ───────────────────────────

    def _log(self, text, tag="plain"):
        self._log_widget_write(text, tag)

    def _log_widget_write(self, text, tag):
        self._log_box.config(state="normal")
        self._log_box.insert("end", text + "\n", tag)
        self._log_box.see("end")
        self._log_box.config(state="disabled")

    def _clear_log(self):
        self._log_box.config(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.config(state="disabled")


if __name__ == "__main__":
    App().mainloop()