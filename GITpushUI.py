"""
GitPushUI.py  —  Simple Git Push Tool

Startup:
  - If already inside a cloned repo  -> load it directly, skip clone dialog
  - If not                           -> show clone/open dialog

Workflow:
  1. App auto-detects + stages all changed files
  2. Type commit message -> click Commit
  3. Click Push to send to GitHub
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

# ── Git helpers ───────────────────────────────

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

def styled_entry(parent, **kw):
    return tk.Entry(parent, font=MONO, bg=SURFACE, fg=FG,
                    insertbackground=FG, relief="flat",
                    highlightthickness=1, highlightbackground=BORDER,
                    highlightcolor=BLUE, **kw)


# ─────────────────────────────────────────────
#  Clone / Open dialog  (only shown when no repo found)
# ─────────────────────────────────────────────

class CloneDialog(tk.Toplevel):
    def __init__(self, master, on_ready, startup=False):
        super().__init__(master)
        self.on_ready = on_ready
        self.title("Connect to GitHub Repo")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        # Only close the whole app if this is the first-run startup dialog
        if startup:
            self.protocol("WM_DELETE_WINDOW", master.destroy)
        else:
            self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._center(560, 460)
        self._build()

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        hdr = tk.Frame(self, bg=SURFACE, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  Connect to GitHub Repo",
                 font=("Segoe UI Semibold", 13), bg=SURFACE, fg=FG).pack(side="left")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG, padx=24, pady=20)
        body.pack(fill="both", expand=True)

        # Option 1: Clone
        tk.Label(body, text="Option 1 — Clone from GitHub",
                 font=BOLD, bg=BG, fg=FG).pack(anchor="w")
        tk.Label(body, text="GitHub repo URL:",
                 font=("Segoe UI", 9), bg=BG, fg=DIM).pack(anchor="w", pady=(8,2))

        self._url = styled_entry(body)
        self._url.pack(fill="x", ipady=8)
        self._url.insert(0, "https://github.com/user/repo.git")
        self._url.config(fg=DIM)
        self._url.bind("<FocusIn>",  self._url_in)
        self._url.bind("<FocusOut>", self._url_out)

        tk.Label(body, text="Clone into folder:",
                 font=("Segoe UI", 9), bg=BG, fg=DIM).pack(anchor="w", pady=(10,2))
        fr = tk.Frame(body, bg=BG)
        fr.pack(fill="x")
        self._dest = styled_entry(fr)
        self._dest.pack(side="left", fill="x", expand=True, ipady=8, padx=(0,8))
        self._dest.insert(0, str(Path(__file__).parent.resolve()))
        btn(fr, "Browse", self._pick_dest, SURFACE, BORDER, pady=6).pack(side="left")

        self._err = tk.Label(body, text="", font=("Segoe UI", 9), bg=BG, fg=RED)
        self._err.pack(anchor="w", pady=(6,0))
        btn(body, "Clone & Open", self._do_clone,
            GREEN, GREEN_HV).pack(anchor="e", pady=(4,0))

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(16,12))

        # Option 2: Open existing
        tk.Label(body, text="Option 2 — Open existing local repo",
                 font=BOLD, bg=BG, fg=FG).pack(anchor="w")
        btn(body, "Open Local Folder", self._open_local,
            SURFACE, BORDER, pady=6).pack(anchor="w", pady=(8,0))

    def _url_in(self, e):
        if self._url.get() == "https://github.com/user/repo.git":
            self._url.delete(0, "end")
            self._url.config(fg=FG)

    def _url_out(self, e):
        if not self._url.get().strip():
            self._url.insert(0, "https://github.com/user/repo.git")
            self._url.config(fg=DIM)

    def _pick_dest(self):
        d = filedialog.askdirectory(title="Choose folder to clone into")
        if d:
            self._dest.delete(0, "end")
            self._dest.insert(0, d)

    def _do_clone(self):
        url  = self._url.get().strip()
        dest = self._dest.get().strip()

        if not url or url == "https://github.com/user/repo.git":
            self._err.config(text="Please enter a GitHub repo URL.", fg=RED); return
        if not dest:
            self._err.config(text="Please choose a destination folder.", fg=RED); return

        dest_path = Path(dest)
        if not dest_path.exists():
            self._err.config(text="Destination folder does not exist.", fg=RED); return

        repo_name  = url.rstrip("/").split("/")[-1].replace(".git", "")
        clone_into = dest_path / repo_name

        # Already cloned? Just open it.
        if clone_into.exists() and (clone_into / ".git").exists():
            self._err.config(text="Already cloned — opening existing copy.", fg=YELLOW)
            self.after(600, lambda: self._finish(clone_into))
            return

        self._err.config(text=f"Cloning into {clone_into} ...", fg=YELLOW)
        self.update()

        r = subprocess.run(
            ["git", "clone", url, str(clone_into)],
            text=True, capture_output=True, shell=False
        )
        if r.returncode == 0:
            self._err.config(text="Cloned successfully!", fg=GREEN)
            self.after(600, lambda: self._finish(clone_into))
        else:
            self._err.config(text=f"Clone failed: {r.stderr.strip()}", fg=RED)

    def _open_local(self):
        d = filedialog.askdirectory(title="Select your local repo folder")
        if not d:
            return
        repo = find_repo(d)
        if repo:
            self._finish(repo)
        else:
            self._err.config(
                text="No git repo found there. Clone first using Option 1.", fg=RED)

    def _finish(self, repo_path):
        self.destroy()
        self.on_ready(Path(repo_path))


# ─────────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git Push UI")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(600, 520)
        self._center(700, 620)
        self.repo = None
        self._committed = False   # tracks whether there's something ready to push
        self._build()
        self.after(100, self._startup)

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Build UI ──────────────────────────────

    def _build(self):
        # Top bar
        top = tk.Frame(self, bg=SURFACE, pady=12)
        top.pack(fill="x")
        tk.Label(top, text="  Git Push UI",
                 font=("Segoe UI Semibold", 13), bg=SURFACE, fg=FG).pack(side="left")
        btn(top, "Change Repo", self._change_repo,
            SURFACE, BORDER, pady=5).pack(side="right", padx=10)
        btn(top, "Pull Latest", self._do_pull,
            SURFACE, BORDER, pady=5).pack(side="right", padx=(0, 4))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Repo path
        rf = tk.Frame(self, bg=BG, padx=16, pady=8)
        rf.pack(fill="x")
        tk.Label(rf, text="Folder:", font=BOLD, bg=BG, fg=DIM).pack(side="left")
        self._repo_lbl = tk.Label(rf, text="—", font=MONO, bg=BG, fg=DIM)
        self._repo_lbl.pack(side="left", padx=6)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Status (changed files)
        sf = tk.Frame(self, bg=BG, padx=16, pady=10)
        sf.pack(fill="x")
        tk.Label(sf, text="Status", font=BOLD, bg=BG, fg=DIM).pack(anchor="w")
        self._status_var = tk.StringVar(value="Waiting for repo...")
        self._status_lbl = tk.Label(sf, textvariable=self._status_var,
                                    font=("Segoe UI", 10), bg=BG, fg=DIM,
                                    wraplength=660, justify="left")
        self._status_lbl.pack(anchor="w", pady=(4, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Commit section ──
        cf = tk.Frame(self, bg=BG, padx=16, pady=14)
        cf.pack(fill="x")
        tk.Label(cf, text="Step 1 — Commit", font=BOLD, bg=BG, fg=DIM).pack(anchor="w")
        tk.Label(cf, text="Describe what you changed:",
                 font=("Segoe UI", 9), bg=BG, fg=DIM).pack(anchor="w", pady=(4, 2))

        msg_row = tk.Frame(cf, bg=BG)
        msg_row.pack(fill="x", pady=(4, 0))
        self._msg = styled_entry(msg_row)
        self._msg.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 10))
        self._msg.bind("<Return>", lambda e: self._do_commit())

        self._commit_btn = btn(msg_row, "Commit", self._do_commit, GREEN, GREEN_HV)
        self._commit_btn.pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Push section ──
        pf = tk.Frame(self, bg=BG, padx=16, pady=14)
        pf.pack(fill="x")
        tk.Label(pf, text="Step 2 — Push", font=BOLD, bg=BG, fg=DIM).pack(anchor="w")
        tk.Label(pf, text="Send committed changes to GitHub:",
                 font=("Segoe UI", 9), bg=BG, fg=DIM).pack(anchor="w", pady=(4, 6))

        self._push_btn = btn(pf, "⬆  Push to GitHub", self._do_push, BLUE, BLUE_HV)
        self._push_btn.pack(anchor="w")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=(6, 0))

        # Log
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
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._log_box.tag_config("ok",   foreground=GREEN)
        self._log_box.tag_config("err",  foreground=RED)
        self._log_box.tag_config("warn", foreground=YELLOW)
        self._log_box.tag_config("dim",  foreground=DIM)

    # ── Startup: check for existing repo first ─

    def _startup(self):
        # Check 1: argument passed to script
        start = sys.argv[1] if len(sys.argv) > 1 else None
        repo  = find_repo(start) if start else None

        # Check 2: current working directory
        if not repo:
            repo = find_repo(Path.cwd())

        # Check 3: same folder as the script itself
        if not repo:
            repo = find_repo(Path(__file__).parent)

        if repo:
            self._log(f"Found existing repo — skipping clone.", "ok")
            self._set_repo(repo)
        else:
            self._log("No local repo found — opening setup.", "dim")
            CloneDialog(self, on_ready=self._set_repo, startup=True)

    def _change_repo(self):
        CloneDialog(self, on_ready=self._set_repo)

    # ── Repo ──────────────────────────────────

    def _set_repo(self, repo):
        self.repo = Path(repo)
        self._repo_lbl.config(text=str(self.repo))
        self._refresh_status()
        self._log(f"Repo: {self.repo}", "dim")

    def _refresh_status(self):
        if not self.repo:
            return
        r     = git(["status", "--short"], self.repo)
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]

        remote_r = git(["remote", "get-url", "origin"], self.repo)
        remote   = remote_r.stdout.strip() if remote_r.returncode == 0 else None

        if not remote:
            self._status_var.set("No GitHub remote set.")
            self._status_lbl.config(fg=RED)
        elif lines:
            flist = "\n  ".join(lines[:8])
            extra = f"  ... and {len(lines)-8} more" if len(lines) > 8 else ""
            self._status_var.set(
                f"{len(lines)} file(s) changed:\n  {flist}{extra}")
            self._status_lbl.config(fg=YELLOW)
        else:
            self._status_var.set("Everything up to date with GitHub")
            self._status_lbl.config(fg=GREEN)

    # ── Pull ──────────────────────────────────

    def _do_pull(self):
        if not self.repo:
            messagebox.showwarning("No repo", "No repo loaded yet."); return
        self._log("Pulling latest from GitHub...", "dim")
        r = git(["pull"], self.repo)
        if r.stdout.strip(): self._log(r.stdout.strip())
        if r.stderr.strip(): self._log(r.stderr.strip(),
                                       "dim" if r.returncode == 0 else "err")
        if r.returncode == 0:
            self._log("Pull complete.", "ok")
            self._refresh_status()
        else:
            self._log("Pull failed — see above.", "err")

    # ── Commit ────────────────────────────────

    def _do_commit(self):
        if not self.repo:
            messagebox.showwarning("No repo", "No repo loaded yet."); return

        msg = self._msg.get().strip() or "new commit"

        self._commit_btn.config(state="disabled", text="Committing...")
        self.update()

        try:
            # Stage everything
            self._log("Staging all files...", "dim")
            r = git(["add", "."], self.repo)
            if r.returncode != 0:
                self._log(r.stderr or "git add failed", "err"); return

            # Check if anything is staged
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(self.repo), shell=False)
            if staged.returncode == 0:
                self._log("No changes to commit — everything already committed.", "warn")
                return

            # Commit
            self._log(f'Committing: "{msg}"', "dim")
            r = git(["commit", "-m", msg], self.repo)
            if r.stdout.strip(): self._log(r.stdout.strip())
            if r.returncode != 0:
                self._log(r.stderr or "Commit failed", "err"); return

            self._log("Committed successfully. Now click Push to upload.", "ok")
            self._msg.delete(0, "end")
            self._committed = True
            self._refresh_status()

        finally:
            self._commit_btn.config(state="normal", text="Commit")

    # ── Push ──────────────────────────────────

    def _do_push(self):
        if not self.repo:
            messagebox.showwarning("No repo", "No repo loaded yet."); return

        remote_r = git(["remote", "get-url", "origin"], self.repo)
        if remote_r.returncode != 0:
            messagebox.showerror("No remote",
                "No GitHub remote is set.\n\n"
                "Run this once in a terminal inside your project folder:\n"
                "  git remote add origin https://github.com/USER/REPO.git")
            return

        self._push_btn.config(state="disabled", text="Pushing...")
        self.update()

        try:
            # Branch (rename master -> main if needed)
            branch_r = git(["branch", "--show-current"], self.repo)
            branch   = branch_r.stdout.strip() or "main"
            if branch == "master":
                git(["branch", "-M", "main"], self.repo)
                branch = "main"

            self._log(f"Pushing '{branch}' to GitHub...", "dim")
            r = git(["push", "--set-upstream", "origin", branch], self.repo)
            if r.stdout.strip(): self._log(r.stdout.strip())
            if r.stderr.strip(): self._log(r.stderr.strip(),
                                           "dim" if r.returncode == 0 else "err")

            if r.returncode == 0:
                self._log("All files pushed to GitHub successfully!", "ok")
                self._committed = False
                self._refresh_status()
            else:
                stderr = r.stderr.lower()
                if any(k in stderr for k in ("401","403","authentication",
                                              "credential","permission denied")):
                    self._log(
                        "Auth failed — a Windows login popup should appear.\n"
                        "If not, open a terminal and run:  git push", "warn")
                elif "rejected" in stderr or "fetch first" in stderr:
                    self._log("Push rejected — force pushing your local files...", "warn")
                    rf = git(["push", "--force", "origin", branch], self.repo)
                    if rf.stdout.strip(): self._log(rf.stdout.strip())
                    if rf.stderr.strip(): self._log(rf.stderr.strip(),
                                           "dim" if rf.returncode == 0 else "err")
                    if rf.returncode == 0:
                        self._log("Force push successful!", "ok")
                        self._committed = False
                        self._refresh_status()
                    else:
                        self._log("Force push failed — see above.", "err")

        finally:
            self._push_btn.config(state="normal", text="⬆  Push to GitHub")

    # ── Log ───────────────────────────────────

    def _log(self, text, tag="plain"):
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