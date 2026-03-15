import subprocess
import sys
import os
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext


# ─────────────────────────────────────────────
#  Git helpers
# ─────────────────────────────────────────────

def run_git(args, cwd, allow_fail=False):
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        shell=False
    )
    return result


def find_repo_path(start_path=None):
    current = Path(start_path).resolve() if start_path else Path.cwd().resolve()
    if current.is_file():
        current = current.parent
    for p in [current] + list(current.parents):
        if (p / ".git").exists():
            return p
    return None


def get_git_config(key, cwd=None):
    r = run_git(["config", key], cwd or Path.cwd(), allow_fail=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def has_untracked_or_modified(repo):
    r = run_git(["status", "--porcelain"], repo, allow_fail=True)
    return bool(r.stdout.strip())


def has_staged_changes(repo):
    r = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(repo), shell=False
    )
    return r.returncode == 1


def get_remote_url(repo):
    r = run_git(["remote", "get-url", "origin"], repo, allow_fail=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def get_current_branch(repo):
    r = run_git(["branch", "--show-current"], repo, allow_fail=True)
    return r.stdout.strip() if r.returncode == 0 else "main"


def diagnose(repo):
    """Return a list of (issue_key, description) for any problems found."""
    issues = []
    if not get_git_config("user.name", repo):
        issues.append(("no_name",    "Git user.name is not set"))
    if not get_git_config("user.email", repo):
        issues.append(("no_email",   "Git user.email is not set"))
    if not get_remote_url(repo):
        issues.append(("no_remote",  "No remote 'origin' is configured"))
    return issues


# ─────────────────────────────────────────────
#  Palette & fonts
# ─────────────────────────────────────────────

BG        = "#0d1117"
SURFACE   = "#161b22"
BORDER    = "#30363d"
ACCENT    = "#238636"
ACCENT_HV = "#2ea043"
PUSH_CLR  = "#1f6feb"
PUSH_HV   = "#388bfd"
WARN      = "#d29922"
ERR       = "#f85149"
FG        = "#e6edf3"
FG_DIM    = "#8b949e"
MONO      = ("Consolas", 10)
SANS      = ("Segoe UI", 10)
SANS_SB   = ("Segoe UI Semibold", 10)
TITLE_F   = ("Segoe UI Semibold", 13)


def styled_btn(parent, text, command, color, hover, **kw):
    kw.setdefault("padx", 14)
    kw.setdefault("pady", 7)
    b = tk.Button(
        parent, text=text, command=command,
        bg=color, fg=FG, activebackground=hover, activeforeground=FG,
        relief="flat", bd=0,
        font=SANS_SB, cursor="hand2", **kw
    )
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


# ─────────────────────────────────────────────
#  Setup Wizard  (first-time / repair)
# ─────────────────────────────────────────────

class SetupWizard(tk.Toplevel):
    def __init__(self, master, repo, issues, on_done):
        super().__init__(master)
        self.repo    = repo
        self.issues  = issues
        self.on_done = on_done
        self.step    = 0
        self.steps   = self._build_steps()

        self.title("Git Setup Wizard")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._center(520, 420)
        self._render()

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_steps(self):
        steps = []
        keys  = {k for k, _ in self.issues}

        if "no_name" in keys:
            steps.append({
                "title": "Set Git Username",
                "desc":  "Git needs a display name attached to every commit.\n"
                         "This can be your real name or a handle.",
                "label": "Your Name",
                "key":   "user.name",
                "ph":    "e.g.  Jane Doe",
            })

        if "no_email" in keys:
            steps.append({
                "title": "Set Git Email",
                "desc":  "Git attaches an email address to every commit.\n"
                         "Use the same address as your GitHub account.",
                "label": "Email Address",
                "key":   "user.email",
                "ph":    "e.g.  jane@example.com",
            })

        if "no_remote" in keys:
            steps.append({
                "title": "Link GitHub Remote",
                "desc":  "Paste the HTTPS or SSH URL of the GitHub repo\n"
                         "you want to push to (create it on GitHub first).",
                "label": "Remote URL",
                "key":   "__remote__",
                "ph":    "https://github.com/user/repo.git",
                "extra": True,
            })

        steps.append({
            "title": "All Done!",
            "desc":  "Your Git configuration looks good.\n"
                     "You can now commit and push from the main window.",
            "final": True,
        })
        return steps

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _render(self):
        self._clear()
        s = self.steps[self.step]

        # Progress bar
        prog_frame = tk.Frame(self, bg=BORDER, height=4)
        prog_frame.pack(fill="x")
        pct = self.step / max(len(self.steps) - 1, 1)
        inner = tk.Frame(prog_frame, bg=ACCENT, height=4,
                         width=int(520 * pct))
        inner.place(x=0, y=0)

        # Header
        hdr = tk.Frame(self, bg=SURFACE, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Git Setup Wizard", font=TITLE_F,
                 bg=SURFACE, fg=FG).pack()
        tk.Label(hdr,
                 text=f"Step {self.step + 1} of {len(self.steps)}",
                 font=("Segoe UI", 9), bg=SURFACE, fg=FG_DIM).pack()

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x")

        # Body
        body = tk.Frame(self, bg=BG, padx=30, pady=24)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=s["title"], font=("Segoe UI Semibold", 12),
                 bg=BG, fg=FG, anchor="w").pack(fill="x")
        tk.Label(body, text=s["desc"], font=("Segoe UI", 10),
                 bg=BG, fg=FG_DIM, justify="left", wraplength=440).pack(
                     fill="x", pady=(6, 18))

        if s.get("final"):
            tk.Label(body, text="✅  Configuration complete",
                     font=("Segoe UI", 11), bg=BG, fg=ACCENT).pack(pady=10)
            styled_btn(body, "Open Main Window", self._finish,
                       ACCENT, ACCENT_HV).pack(pady=8)
            return

        tk.Label(body, text=s["label"], font=SANS_SB,
                 bg=BG, fg=FG_DIM).pack(anchor="w")
        self._entry = tk.Entry(body, font=MONO, bg=SURFACE, fg=FG,
                               insertbackground=FG, relief="flat",
                               highlightthickness=1,
                               highlightbackground=BORDER,
                               highlightcolor=PUSH_CLR)
        self._entry.pack(fill="x", ipady=8, pady=(4, 4))
        self._entry.insert(0, "")
        self._entry.config(fg=FG_DIM)
        self._entry.bind("<FocusIn>",  lambda e: self._ph_clear(s["ph"]))
        self._entry.bind("<FocusOut>", lambda e: self._ph_restore(s["ph"]))
        self._entry.insert(0, s["ph"])

        if s.get("extra"):
            tk.Button(body, text="🔗  Open GitHub to create a repo",
                      font=("Segoe UI", 9), bg=BG, fg=PUSH_CLR,
                      activeforeground=PUSH_HV, relief="flat", bd=0,
                      cursor="hand2",
                      command=lambda: webbrowser.open(
                          "https://github.com/new")).pack(anchor="w", pady=2)

        self._err_lbl = tk.Label(body, text="", font=("Segoe UI", 9),
                                 bg=BG, fg=ERR)
        self._err_lbl.pack(anchor="w")

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x", pady=(12, 0))
        if self.step > 0:
            styled_btn(btn_row, "← Back", self._back,
                       SURFACE, BORDER).pack(side="left")
        styled_btn(btn_row, "Apply & Continue →", self._next,
                   ACCENT, ACCENT_HV).pack(side="right")

    def _ph_clear(self, ph):
        if self._entry.get() == ph:
            self._entry.delete(0, "end")
            self._entry.config(fg=FG)

    def _ph_restore(self, ph):
        if not self._entry.get():
            self._entry.insert(0, ph)
            self._entry.config(fg=FG_DIM)

    def _get_value(self):
        s   = self.steps[self.step]
        val = self._entry.get().strip()
        return "" if val == s.get("ph", "") else val

    def _next(self):
        s   = self.steps[self.step]
        val = self._get_value()
        if not val:
            self._err_lbl.config(text="⚠  This field cannot be empty.")
            return
        self._err_lbl.config(text="")

        key = s["key"]
        if key == "__remote__":
            r = run_git(["remote", "add", "origin", val], self.repo,
                        allow_fail=True)
            if r.returncode != 0:
                # already exists – update it
                run_git(["remote", "set-url", "origin", val], self.repo)
            # Try to init & set upstream
            branch = get_current_branch(self.repo)
            run_git(["branch", "-M", branch], self.repo, allow_fail=True)
        else:
            run_git(["config", key, val], self.repo)

        self.step += 1
        self._render()

    def _back(self):
        self.step = max(0, self.step - 1)
        self._render()

    def _finish(self):
        self.destroy()
        self.on_done()


# ─────────────────────────────────────────────
#  Init-repo dialog (no .git found)
# ─────────────────────────────────────────────

class InitRepoDialog(tk.Toplevel):
    def __init__(self, master, on_done):
        super().__init__(master)
        self.on_done = on_done
        self.title("Initialise Repository")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._center(500, 300)
        self._build()

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        tk.Label(self, text="No Git Repository Found",
                 font=("Segoe UI Semibold", 13),
                 bg=BG, fg=FG).pack(pady=(28, 4))
        tk.Label(self,
                 text="Choose a folder to initialise as a new Git repository,\n"
                      "or select an existing repo folder.",
                 font=("Segoe UI", 10), bg=BG, fg=FG_DIM).pack(pady=(0, 20))

        row = tk.Frame(self, bg=BG)
        row.pack(padx=28, fill="x")
        self._path_var = tk.StringVar(value=str(Path.cwd()))
        e = tk.Entry(row, textvariable=self._path_var,
                     font=MONO, bg=SURFACE, fg=FG,
                     insertbackground=FG, relief="flat",
                     highlightthickness=1,
                     highlightbackground=BORDER,
                     highlightcolor=PUSH_CLR, width=38)
        e.pack(side="left", ipady=7, fill="x", expand=True)
        tk.Button(row, text="Browse", font=SANS, bg=SURFACE, fg=FG,
                  activebackground=BORDER, activeforeground=FG,
                  relief="flat", padx=8, cursor="hand2",
                  command=self._browse).pack(side="left", padx=(6, 0),
                                             ipady=7)

        self._err = tk.Label(self, text="", font=("Segoe UI", 9),
                             bg=BG, fg=ERR)
        self._err.pack()

        styled_btn(self, "Initialise & Continue →", self._init,
                   ACCENT, ACCENT_HV).pack(pady=18)

    def _browse(self):
        d = filedialog.askdirectory(title="Select project folder")
        if d:
            self._path_var.set(d)

    def _init(self):
        folder = Path(self._path_var.get()).resolve()
        if not folder.exists():
            self._err.config(text="⚠  Folder does not exist.")
            return
        r = run_git(["init"], folder, allow_fail=True)
        if r.returncode != 0:
            self._err.config(text=f"⚠  git init failed: {r.stderr.strip()}")
            return
        self.destroy()
        self.on_done(folder)


# ─────────────────────────────────────────────
#  Main Application Window
# ─────────────────────────────────────────────

class GitPushUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git Push UI")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(620, 540)
        self._center(720, 620)

        self.repo = None
        self._build_ui()
        self.after(100, self._auto_detect_repo)

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Build UI ──────────────────────────────

    def _build_ui(self):
        # ── Top bar ──
        top = tk.Frame(self, bg=SURFACE, pady=0)
        top.pack(fill="x")

        tk.Label(top, text="  ⎇  Git Push UI",
                 font=("Segoe UI Semibold", 12),
                 bg=SURFACE, fg=FG, pady=14).pack(side="left")

        self._branch_lbl = tk.Label(top, text="",
                                    font=("Segoe UI", 9),
                                    bg=SURFACE, fg=FG_DIM, padx=12)
        self._branch_lbl.pack(side="right")

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x")

        # ── Repo path bar ──
        rbar = tk.Frame(self, bg=BG, padx=16, pady=10)
        rbar.pack(fill="x")

        tk.Label(rbar, text="Repo:", font=SANS_SB,
                 bg=BG, fg=FG_DIM).pack(side="left")
        self._repo_var = tk.StringVar(value="—")
        tk.Label(rbar, textvariable=self._repo_var,
                 font=MONO, bg=BG, fg=FG_DIM).pack(side="left", padx=6)

        styled_btn(rbar, "Change…", self._pick_repo,
                   SURFACE, BORDER, pady=4).pack(side="right")

        sep2 = tk.Frame(self, bg=BORDER, height=1)
        sep2.pack(fill="x")

        # ── Status panel ──
        status_frame = tk.Frame(self, bg=BG, padx=16, pady=10)
        status_frame.pack(fill="x")

        tk.Label(status_frame, text="Status",
                 font=("Segoe UI Semibold", 10),
                 bg=BG, fg=FG_DIM).pack(anchor="w")

        self._status_var = tk.StringVar(value="Loading…")
        self._status_lbl = tk.Label(status_frame,
                                    textvariable=self._status_var,
                                    font=("Segoe UI", 10),
                                    bg=BG, fg=FG, wraplength=680,
                                    justify="left")
        self._status_lbl.pack(anchor="w", pady=(2, 0))

        sep3 = tk.Frame(self, bg=BORDER, height=1)
        sep3.pack(fill="x")

        # ── Commit section ──
        commit_frame = tk.Frame(self, bg=BG, padx=16, pady=14)
        commit_frame.pack(fill="x")

        tk.Label(commit_frame, text="Commit Message",
                 font=("Segoe UI Semibold", 10),
                 bg=BG, fg=FG_DIM).pack(anchor="w")

        msg_row = tk.Frame(commit_frame, bg=BG)
        msg_row.pack(fill="x", pady=(6, 0))

        self._msg_entry = tk.Entry(
            msg_row, font=MONO,
            bg=SURFACE, fg=FG, insertbackground=FG,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT
        )
        self._msg_entry.pack(side="left", fill="x", expand=True,
                             ipady=9, padx=(0, 10))
        self._msg_entry.bind("<Return>", lambda e: self._do_commit())

        self._commit_btn = styled_btn(
            msg_row, "Commit", self._do_commit, ACCENT, ACCENT_HV)
        self._commit_btn.pack(side="left")

        # ── Push section ──
        push_frame = tk.Frame(self, bg=BG, padx=16, pady=4)
        push_frame.pack(fill="x")

        self._remote_lbl = tk.Label(push_frame, text="Remote: —",
                                    font=("Segoe UI", 9),
                                    bg=BG, fg=FG_DIM)
        self._remote_lbl.pack(side="left")

        self._push_btn = styled_btn(
            push_frame, "⬆  Push to Remote",
            self._do_push, PUSH_CLR, PUSH_HV)
        self._push_btn.pack(side="right")

        sep4 = tk.Frame(self, bg=BORDER, height=1)
        sep4.pack(fill="x", pady=(10, 0))

        # ── Log ──
        log_hdr = tk.Frame(self, bg=BG, padx=16, pady=8)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text="Output Log",
                 font=("Segoe UI Semibold", 10),
                 bg=BG, fg=FG_DIM).pack(side="left")
        tk.Button(log_hdr, text="Clear", font=("Segoe UI", 9),
                  bg=BG, fg=FG_DIM, activebackground=SURFACE,
                  activeforeground=FG, relief="flat", bd=0,
                  cursor="hand2",
                  command=self._clear_log).pack(side="right")

        self._log = scrolledtext.ScrolledText(
            self, font=MONO, bg=SURFACE, fg=FG,
            insertbackground=FG, relief="flat",
            state="disabled", wrap="word",
            padx=14, pady=10,
            highlightthickness=0
        )
        self._log.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # colour tags
        self._log.tag_config("ok",    foreground=ACCENT)
        self._log.tag_config("err",   foreground=ERR)
        self._log.tag_config("warn",  foreground=WARN)
        self._log.tag_config("info",  foreground=FG_DIM)
        self._log.tag_config("plain", foreground=FG)

    # ── Repo management ───────────────────────

    def _auto_detect_repo(self):
        start = sys.argv[1] if len(sys.argv) > 1 else None
        repo  = find_repo_path(start)
        if repo:
            self._load_repo(repo)
        else:
            self._log_msg("No git repository found in current directory.",
                          "warn")
            InitRepoDialog(self, self._after_init)

    def _after_init(self, folder):
        self._load_repo(folder)

    def _pick_repo(self):
        d = filedialog.askdirectory(title="Select repository folder")
        if not d:
            return
        repo = find_repo_path(d)
        if not repo:
            # offer to init
            if messagebox.askyesno(
                    "No repo", f"No .git found in:\n{d}\n\nInitialise here?"):
                r = run_git(["init"], Path(d))
                if r.returncode == 0:
                    self._load_repo(Path(d))
                else:
                    messagebox.showerror("Error", r.stderr)
        else:
            self._load_repo(repo)

    def _load_repo(self, repo):
        self.repo = repo
        self._repo_var.set(str(repo))
        self._log_msg(f"Repo loaded: {repo}", "info")
        self._refresh_ui()
        self._run_diagnostics()

    def _run_diagnostics(self):
        if not self.repo:
            return
        issues = diagnose(self.repo)
        if issues:
            msg = "Issues found:\n" + "\n".join(f"  • {d}" for _, d in issues)
            self._log_msg(msg, "warn")
            self._status_var.set(
                "⚠  Setup needed — launching wizard…")
            self.after(400, lambda: SetupWizard(
                self, self.repo, issues, self._after_wizard))
        else:
            self._log_msg("Git config OK ✓", "ok")

    def _after_wizard(self):
        self._refresh_ui()
        # re-diagnose
        remaining = diagnose(self.repo)
        if remaining:
            self._log_msg("Some issues still present — re-opening wizard.",
                          "warn")
            SetupWizard(self, self.repo, remaining, self._after_wizard)
        else:
            self._log_msg("All configuration complete ✓", "ok")

    def _refresh_ui(self):
        if not self.repo:
            return
        branch = get_current_branch(self.repo)
        remote = get_remote_url(self.repo)
        self._branch_lbl.config(text=f"branch: {branch}")
        self._remote_lbl.config(
            text=f"Remote: {remote or '(not set)'}")

        if has_untracked_or_modified(self.repo):
            r = run_git(["status", "--short"], self.repo, allow_fail=True)
            lines = r.stdout.strip().splitlines()
            self._status_var.set(
                f"{len(lines)} changed file(s) — ready to stage & commit")
            self._status_lbl.config(fg=WARN)
        else:
            self._status_var.set("Working tree clean — nothing to commit")
            self._status_lbl.config(fg=ACCENT)

    # ── Commit ────────────────────────────────

    def _do_commit(self):
        if not self.repo:
            self._log_msg("No repository selected.", "err"); return

        msg = self._msg_entry.get().strip()
        if not msg:
            self._log_msg("⚠  Commit message is empty.", "warn"); return

        issues = diagnose(self.repo)
        if issues:
            self._log_msg("Cannot commit — setup is incomplete.", "err")
            SetupWizard(self, self.repo, issues, self._after_wizard)
            return

        if not has_untracked_or_modified(self.repo):
            self._log_msg("Nothing to commit.", "info"); return

        self._log_msg("Staging all changes…", "info")
        r = run_git(["add", "."], self.repo)
        self._log_output(r)

        if not has_staged_changes(self.repo):
            self._log_msg("No staged changes.", "info"); return

        self._log_msg(f'Committing: "{msg}"', "info")
        r = run_git(["commit", "-m", msg], self.repo)
        self._log_output(r)

        if r.returncode == 0:
            self._log_msg("Commit successful ✓", "ok")
            self._msg_entry.delete(0, "end")
            self._refresh_ui()
        else:
            self._log_msg("Commit failed.", "err")

    # ── Push ──────────────────────────────────

    def _do_push(self):
        if not self.repo:
            self._log_msg("No repository selected.", "err"); return

        issues = diagnose(self.repo)
        if issues:
            self._log_msg("Cannot push — setup is incomplete.", "err")
            SetupWizard(self, self.repo, issues, self._after_wizard)
            return

        remote = get_remote_url(self.repo)
        if not remote:
            self._log_msg("No remote configured. Run setup wizard first.",
                          "err"); return

        branch = get_current_branch(self.repo)
        self._log_msg(f"Pushing '{branch}' → {remote} …", "info")

        r = run_git(["push", "--set-upstream", "origin", branch],
                    self.repo, allow_fail=True)
        self._log_output(r)

        if r.returncode == 0:
            self._log_msg("Push successful ✓", "ok")
        else:
            stderr = r.stderr.lower()
            if "authentication" in stderr or "credential" in stderr:
                self._log_msg(
                    "Auth failed. Check your credentials / SSH key.", "err")
            elif "rejected" in stderr:
                self._log_msg(
                    "Push rejected — pull & merge remote changes first.",
                    "warn")
            else:
                self._log_msg("Push failed — see output above.", "err")

    # ── Log helpers ───────────────────────────

    def _log_msg(self, text, tag="plain"):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _log_output(self, result):
        if result.stdout.strip():
            self._log_msg(result.stdout.strip(), "plain")
        if result.stderr.strip():
            tag = "err" if result.returncode != 0 else "info"
            self._log_msg(result.stderr.strip(), tag)

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")


# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = GitPushUI()
    app.mainloop()