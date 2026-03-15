"""
GitPushUI.py
============
A dark-themed GUI for git add -> commit -> push.

Authentication uses the GitHub CLI (gh) browser-based OAuth flow:
  - If 'gh' is installed and already logged in  -> push works immediately.
  - If 'gh' is installed but NOT logged in      -> a dialog opens, browser
    launches, user clicks "Authorize", done.
  - If 'gh' is NOT installed                    -> a dialog explains how to
    install it (one URL, one command).

Requires: Python 3.8+, tkinter (stdlib), git, gh CLI
"""

import subprocess
import sys
import re
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext


# ─────────────────────────────────────────────────────────────
#  Git / gh helpers
# ─────────────────────────────────────────────────────────────

def run_cmd(cmd, cwd=None, allow_fail=False, input_text=None):
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        shell=False,
        input=input_text,
    )
    return result


def run_git(args, cwd, allow_fail=False):
    return run_cmd(["git"] + args, cwd=cwd, allow_fail=allow_fail)


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


# ── GitHub CLI helpers ────────────────────────────────────────

def gh_installed():
    try:
        r = run_cmd(["gh", "--version"], allow_fail=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def gh_logged_in():
    try:
        r = run_cmd(["gh", "auth", "status"], allow_fail=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def gh_setup_git():
    """Configure git to use gh as the credential helper."""
    try:
        return run_cmd(["gh", "auth", "setup-git"], allow_fail=True)
    except FileNotFoundError:
        return None


def gh_whoami():
    try:
        r = run_cmd(["gh", "api", "user", "--jq", ".login"], allow_fail=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except FileNotFoundError:
        return ""


def diagnose(repo):
    issues = []
    if not get_git_config("user.name", repo):
        issues.append(("no_name",   "Git user.name is not set"))
    if not get_git_config("user.email", repo):
        issues.append(("no_email",  "Git user.email is not set"))
    if not get_remote_url(repo):
        issues.append(("no_remote", "No remote 'origin' is configured"))
    return issues


# ─────────────────────────────────────────────────────────────
#  Palette & fonts
# ─────────────────────────────────────────────────────────────

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

GH_INSTALL_URL = "https://cli.github.com/"


def styled_btn(parent, text, command, color, hover, **kw):
    kw.setdefault("padx", 14)
    kw.setdefault("pady", 7)
    b = tk.Button(
        parent, text=text, command=command,
        bg=color, fg=FG, activebackground=hover, activeforeground=FG,
        relief="flat", bd=0, font=SANS_SB, cursor="hand2", **kw
    )
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


def make_entry(parent, show=None, **kw):
    return tk.Entry(
        parent, font=MONO, bg=SURFACE, fg=FG,
        insertbackground=FG, relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=PUSH_CLR,
        show=show or "",
        **kw,
    )


# ─────────────────────────────────────────────────────────────
#  "Install gh CLI" dialog
# ─────────────────────────────────────────────────────────────

class InstallGHDialog(tk.Toplevel):
    """Shown when 'gh' is not found on PATH."""
    def __init__(self, master, on_installed):
        super().__init__(master)
        self.on_installed = on_installed
        self.title("GitHub CLI Required")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._center(520, 370)
        self._build()

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        hdr = tk.Frame(self, bg=SURFACE, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="GitHub CLI Not Found",
                 font=TITLE_F, bg=SURFACE, fg=FG).pack()
        tk.Label(hdr, text="One-time install needed for browser login",
                 font=("Segoe UI", 9), bg=SURFACE, fg=FG_DIM).pack()

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG, padx=28, pady=22)
        body.pack(fill="both", expand=True)

        tk.Label(body,
                 text="The GitHub CLI (gh) enables one-click browser login\n"
                      "so you never need to type passwords or tokens.",
                 font=("Segoe UI", 10), bg=BG, fg=FG,
                 justify="left").pack(anchor="w")

        steps_frame = tk.Frame(body, bg=SURFACE, padx=16, pady=14)
        steps_frame.pack(fill="x", pady=(16, 0))

        for line in [
            "1.  Click 'Download & Install gh' below",
            "2.  Run the installer  (Windows .msi / Mac .pkg / Linux pkg)",
            "3.  Come back here and click  'I Have Installed It'",
        ]:
            tk.Label(steps_frame, text=line, font=("Segoe UI", 9),
                     bg=SURFACE, fg=FG, justify="left",
                     anchor="w").pack(fill="x", pady=2)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        btn_row = tk.Frame(self, bg=BG, padx=28, pady=14)
        btn_row.pack(fill="x")
        styled_btn(btn_row, "Download & Install gh",
                   lambda: webbrowser.open(GH_INSTALL_URL),
                   PUSH_CLR, PUSH_HV).pack(side="left")
        styled_btn(btn_row, "I Have Installed It  ->",
                   self._recheck, ACCENT, ACCENT_HV).pack(side="right")

    def _recheck(self):
        if gh_installed():
            self.destroy()
            self.on_installed()
        else:
            messagebox.showwarning(
                "Not Found",
                "gh still not found on PATH.\n\n"
                "Make sure to restart your terminal / this script after installing.",
                parent=self,
            )


# ─────────────────────────────────────────────────────────────
#  GitHub Browser Login dialog  (gh auth login --web)
# ─────────────────────────────────────────────────────────────

class GitHubBrowserLoginDialog(tk.Toplevel):
    """
    Runs 'gh auth login --web' in a background thread.
    Parses the one-time activation code from its output,
    opens the browser automatically, and waits for approval.

    Flow:
      1. gh prints a one-time code like  ABCD-1234
      2. gh opens (or tells us to open) github.com/login/device
      3. User pastes/confirms the code in the browser
      4. gh exits 0  ->  we call on_success(username)
    """
    def __init__(self, master, on_success, on_cancel=None):
        super().__init__(master)
        self.on_success = on_success
        self.on_cancel  = on_cancel
        self._proc      = None
        self._done      = False

        self.title("GitHub Login")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._center(500, 400)
        self._build()
        self.after(300, self._start_auth)

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        hdr = tk.Frame(self, bg=SURFACE, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="GitHub Browser Login",
                 font=TITLE_F, bg=SURFACE, fg=FG).pack()
        tk.Label(hdr, text="Authorise once — stays logged in forever",
                 font=("Segoe UI", 9), bg=SURFACE, fg=FG_DIM).pack()

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG, padx=28, pady=22)
        body.pack(fill="both", expand=True)

        # Status
        self._status_lbl = tk.Label(
            body, text="Starting authentication...",
            font=("Segoe UI", 10), bg=BG, fg=FG_DIM,
            wraplength=440, justify="left")
        self._status_lbl.pack(anchor="w")

        # Code box (hidden until code arrives)
        self._code_frame = tk.Frame(body, bg=BG)

        tk.Label(self._code_frame,
                 text="One-time code (paste in browser if asked):",
                 font=("Segoe UI", 9), bg=BG, fg=FG_DIM).pack(anchor="w")

        code_row = tk.Frame(self._code_frame, bg=BG)
        code_row.pack(fill="x", pady=(6, 0))

        self._code_var = tk.StringVar(value="")
        tk.Label(code_row, textvariable=self._code_var,
                 font=("Consolas", 26, "bold"), bg=SURFACE, fg=ACCENT,
                 padx=20, pady=12,
                 relief="flat", highlightthickness=1,
                 highlightbackground=BORDER).pack(side="left")

        self._copy_btn = tk.Button(
            code_row, text="Copy", font=("Segoe UI", 9),
            bg=SURFACE, fg=FG_DIM, activebackground=BORDER,
            activeforeground=FG, relief="flat", bd=0, padx=10,
            cursor="hand2", command=self._copy_code)
        self._copy_btn.pack(side="left", padx=(8, 0))

        self._instr_lbl = tk.Label(
            body, text="",
            font=("Segoe UI", 9), bg=BG, fg=FG_DIM,
            wraplength=440, justify="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        btn_row = tk.Frame(self, bg=BG, padx=28, pady=12)
        btn_row.pack(fill="x")
        styled_btn(btn_row, "Cancel", self._cancel,
                   SURFACE, BORDER).pack(side="left")
        self._open_btn = styled_btn(
            btn_row, "Open Browser Manually",
            lambda: webbrowser.open("https://github.com/login/device"),
            PUSH_CLR, PUSH_HV)
        # shown after code arrives

    # ── Auth background thread ────────────────

    def _start_auth(self):
        threading.Thread(target=self._run_gh_auth, daemon=True).start()

    def _run_gh_auth(self):
        try:
            self._proc = subprocess.Popen(
                ["gh", "auth", "login",
                 "--hostname", "github.com",
                 "--git-protocol", "https",
                 "--web"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in self._proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                self.after(0, lambda l=line: self._handle_gh_line(l))
                if self._done:
                    break

            self._proc.wait()
            rc = self._proc.returncode

            if self._done:
                return

            if rc == 0:
                self.after(0, self._on_auth_ok)
            else:
                self.after(0, lambda: self._on_auth_fail(
                    "Authentication failed. Please try again."))

        except FileNotFoundError:
            self.after(0, lambda: self._on_auth_fail(
                "gh not found. Please install the GitHub CLI."))
        except Exception as ex:
            self.after(0, lambda: self._on_auth_fail(str(ex)))

    def _handle_gh_line(self, line):
        lower = line.lower()

        # One-time code e.g. "ABCD-1234"
        m = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", line)
        if m:
            self._show_code(m.group(1))

        # Activation URL -> open browser
        if "github.com/login/device" in lower or "activate" in lower:
            url_m = re.search(r"https://\S+", line)
            url = url_m.group(0) if url_m else "https://github.com/login/device"
            webbrowser.open(url)
            self._status_lbl.config(
                text="Browser opened — approve the request on GitHub, then return here.")

        # Success
        if any(k in lower for k in ("logged in", "authentication complete",
                                     "you are now", "logged into")):
            self._done = True
            self._on_auth_ok()
            return

        # Generic status forward
        if line.strip() and not m:
            self._status_lbl.config(text=line.strip())

    def _show_code(self, code):
        self._code_var.set(code)
        self._code_frame.pack(fill="x", pady=(18, 0))
        self._instr_lbl.config(
            text="Your browser opened automatically.\n"
                 "If it did not, click 'Open Browser Manually' and enter the code above.")
        self._instr_lbl.pack(anchor="w", pady=(10, 0))
        self._open_btn.pack(side="right")
        self._status_lbl.config(
            text="Waiting for you to approve in the browser...")

    def _copy_code(self):
        self.clipboard_clear()
        self.clipboard_append(self._code_var.get())
        self._copy_btn.config(text="Copied!")
        self.after(2000, lambda: self._copy_btn.config(text="Copy"))

    def _on_auth_ok(self):
        self._status_lbl.config(
            text="Authenticated! Configuring git credential helper...",
            fg=ACCENT)
        gh_setup_git()
        user = gh_whoami()
        self._done = True
        self.after(800, lambda: self._finish(user))

    def _finish(self, user):
        if self.winfo_exists():
            self.destroy()
        self.on_success(user)

    def _on_auth_fail(self, msg):
        if self.winfo_exists():
            self._status_lbl.config(text=f"Error: {msg}", fg=ERR)

    def _cancel(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
        if self.winfo_exists():
            self.destroy()
        if self.on_cancel:
            self.on_cancel()


# ─────────────────────────────────────────────────────────────
#  Setup Wizard  (git config / remote)
# ─────────────────────────────────────────────────────────────

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
                "desc":  "Your display name attached to every commit.",
                "label": "Your Name",
                "key":   "user.name",
                "ph":    "e.g.  Jane Doe",
            })
        if "no_email" in keys:
            steps.append({
                "title": "Set Git Email",
                "desc":  "Use the same address as your GitHub account.",
                "label": "Email Address",
                "key":   "user.email",
                "ph":    "e.g.  jane@example.com",
            })
        if "no_remote" in keys:
            steps.append({
                "title": "Link GitHub Remote",
                "desc":  "Paste the HTTPS URL of your GitHub repo.\n"
                         "(Create it on GitHub first if needed.)",
                "label": "Remote URL",
                "key":   "__remote__",
                "ph":    "https://github.com/user/repo.git",
                "extra": True,
            })
        steps.append({
            "title": "All Done!",
            "desc":  "Git configuration is complete.",
            "final": True,
        })
        return steps

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _render(self):
        self._clear()
        s = self.steps[self.step]

        prog = tk.Frame(self, bg=BORDER, height=4)
        prog.pack(fill="x")
        pct = self.step / max(len(self.steps) - 1, 1)
        tk.Frame(prog, bg=ACCENT, height=4,
                 width=int(520 * pct)).place(x=0, y=0)

        hdr = tk.Frame(self, bg=SURFACE, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Git Setup Wizard",
                 font=TITLE_F, bg=SURFACE, fg=FG).pack()
        tk.Label(hdr, text=f"Step {self.step + 1} of {len(self.steps)}",
                 font=("Segoe UI", 9), bg=SURFACE, fg=FG_DIM).pack()

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG, padx=30, pady=24)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=s["title"], font=("Segoe UI Semibold", 12),
                 bg=BG, fg=FG, anchor="w").pack(fill="x")
        tk.Label(body, text=s["desc"], font=("Segoe UI", 10),
                 bg=BG, fg=FG_DIM, justify="left",
                 wraplength=440).pack(fill="x", pady=(6, 18))

        if s.get("final"):
            tk.Label(body, text="Configuration complete",
                     font=("Segoe UI", 11), bg=BG, fg=ACCENT).pack(pady=10)
            styled_btn(body, "Open Main Window", self._finish,
                       ACCENT, ACCENT_HV).pack(pady=8)
            return

        tk.Label(body, text=s["label"], font=SANS_SB,
                 bg=BG, fg=FG_DIM).pack(anchor="w")
        self._entry = make_entry(body)
        self._entry.pack(fill="x", ipady=8, pady=(4, 4))
        self._entry.insert(0, s["ph"])
        self._entry.config(fg=FG_DIM)
        self._entry.bind("<FocusIn>",  lambda e: self._ph_clear(s["ph"]))
        self._entry.bind("<FocusOut>", lambda e: self._ph_restore(s["ph"]))

        if s.get("extra"):
            tk.Button(body, text="Create repo on GitHub ->",
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
            styled_btn(btn_row, "<- Back", self._back,
                       SURFACE, BORDER).pack(side="left")
        styled_btn(btn_row, "Apply & Continue ->", self._next,
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
        val = self._entry.get().strip()
        return "" if val == self.steps[self.step].get("ph", "") else val

    def _next(self):
        s   = self.steps[self.step]
        val = self._get_value()
        if not val:
            self._err_lbl.config(text="This field cannot be empty.")
            return
        self._err_lbl.config(text="")
        if s["key"] == "__remote__":
            r = run_git(["remote", "add", "origin", val],
                        self.repo, allow_fail=True)
            if r.returncode != 0:
                run_git(["remote", "set-url", "origin", val], self.repo)
            branch = get_current_branch(self.repo)
            run_git(["branch", "-M", branch], self.repo, allow_fail=True)
        else:
            run_git(["config", s["key"], val], self.repo)
        self.step += 1
        self._render()

    def _back(self):
        self.step = max(0, self.step - 1)
        self._render()

    def _finish(self):
        self.destroy()
        self.on_done()


# ─────────────────────────────────────────────────────────────
#  Init-repo dialog
# ─────────────────────────────────────────────────────────────

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
                 text="Choose a folder to initialise as a new Git repo,\n"
                      "or select an existing repo folder.",
                 font=("Segoe UI", 10), bg=BG, fg=FG_DIM).pack(pady=(0, 20))

        row = tk.Frame(self, bg=BG)
        row.pack(padx=28, fill="x")
        self._path_var = tk.StringVar(value=str(Path.cwd()))
        make_entry(row, textvariable=self._path_var, width=38).pack(
            side="left", ipady=7, fill="x", expand=True)
        tk.Button(row, text="Browse", font=SANS, bg=SURFACE, fg=FG,
                  activebackground=BORDER, activeforeground=FG,
                  relief="flat", padx=8, cursor="hand2",
                  command=self._browse).pack(side="left", padx=(6, 0), ipady=7)

        self._err = tk.Label(self, text="", font=("Segoe UI", 9),
                             bg=BG, fg=ERR)
        self._err.pack()

        styled_btn(self, "Initialise & Continue ->", self._init,
                   ACCENT, ACCENT_HV).pack(pady=18)

    def _browse(self):
        d = filedialog.askdirectory(title="Select project folder")
        if d:
            self._path_var.set(d)

    def _init(self):
        folder = Path(self._path_var.get()).resolve()
        if not folder.exists():
            self._err.config(text="Folder does not exist."); return
        r = run_git(["init"], folder, allow_fail=True)
        if r.returncode != 0:
            self._err.config(text=f"git init failed: {r.stderr.strip()}")
            return
        self.destroy()
        self.on_done(folder)


# ─────────────────────────────────────────────────────────────
#  Main Application Window
# ─────────────────────────────────────────────────────────────

class GitPushUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git Push UI")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(620, 560)
        self._center(740, 640)

        self.repo        = None
        self._gh_user    = ""

        self._build_ui()
        self.after(120, self._startup)

    def _center(self, w, h):
        self.geometry(f"{w}x{h}")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Build static UI ───────────────────────

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=SURFACE)
        top.pack(fill="x")
        tk.Label(top, text="  Git Push UI",
                 font=("Segoe UI Semibold", 12),
                 bg=SURFACE, fg=FG, pady=14).pack(side="left")

        self._branch_lbl = tk.Label(top, text="",
                                    font=("Segoe UI", 9),
                                    bg=SURFACE, fg=FG_DIM, padx=8)
        self._branch_lbl.pack(side="right")

        self._auth_lbl = tk.Label(top, text="",
                                  font=("Segoe UI", 9),
                                  bg=SURFACE, fg=FG_DIM, padx=12,
                                  cursor="hand2")
        self._auth_lbl.pack(side="right")
        self._auth_lbl.bind("<Button-1>", lambda e: self._ensure_gh_auth())

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Repo bar
        rbar = tk.Frame(self, bg=BG, padx=16, pady=10)
        rbar.pack(fill="x")
        tk.Label(rbar, text="Repo:", font=SANS_SB,
                 bg=BG, fg=FG_DIM).pack(side="left")
        self._repo_var = tk.StringVar(value="—")
        tk.Label(rbar, textvariable=self._repo_var,
                 font=MONO, bg=BG, fg=FG_DIM).pack(side="left", padx=6)
        styled_btn(rbar, "Change...", self._pick_repo,
                   SURFACE, BORDER, pady=4).pack(side="right")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Status
        sf = tk.Frame(self, bg=BG, padx=16, pady=10)
        sf.pack(fill="x")
        tk.Label(sf, text="Status", font=("Segoe UI Semibold", 10),
                 bg=BG, fg=FG_DIM).pack(anchor="w")
        self._status_var = tk.StringVar(value="Loading...")
        self._status_lbl = tk.Label(sf, textvariable=self._status_var,
                                    font=("Segoe UI", 10),
                                    bg=BG, fg=FG, wraplength=700,
                                    justify="left")
        self._status_lbl.pack(anchor="w", pady=(2, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Commit row
        cf = tk.Frame(self, bg=BG, padx=16, pady=14)
        cf.pack(fill="x")
        tk.Label(cf, text="Commit Message",
                 font=("Segoe UI Semibold", 10),
                 bg=BG, fg=FG_DIM).pack(anchor="w")
        msg_row = tk.Frame(cf, bg=BG)
        msg_row.pack(fill="x", pady=(6, 0))
        self._msg_entry = make_entry(msg_row)
        self._msg_entry.pack(side="left", fill="x", expand=True,
                             ipady=9, padx=(0, 10))
        self._msg_entry.bind("<Return>", lambda e: self._do_commit())
        styled_btn(msg_row, "Commit", self._do_commit,
                   ACCENT, ACCENT_HV).pack(side="left")

        # Push row
        pf = tk.Frame(self, bg=BG, padx=16, pady=4)
        pf.pack(fill="x")
        self._remote_lbl = tk.Label(pf, text="Remote: —",
                                    font=("Segoe UI", 9),
                                    bg=BG, fg=FG_DIM)
        self._remote_lbl.pack(side="left")
        styled_btn(pf, "Push to Remote", self._do_push,
                   PUSH_CLR, PUSH_HV).pack(side="right")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=(10, 0))

        # Log
        log_hdr = tk.Frame(self, bg=BG, padx=16, pady=8)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text="Output Log",
                 font=("Segoe UI Semibold", 10),
                 bg=BG, fg=FG_DIM).pack(side="left")
        tk.Button(log_hdr, text="Clear", font=("Segoe UI", 9),
                  bg=BG, fg=FG_DIM, activebackground=SURFACE,
                  activeforeground=FG, relief="flat", bd=0, cursor="hand2",
                  command=self._clear_log).pack(side="right")

        self._log = scrolledtext.ScrolledText(
            self, font=MONO, bg=SURFACE, fg=FG,
            insertbackground=FG, relief="flat",
            state="disabled", wrap="word", padx=14, pady=10,
            highlightthickness=0)
        self._log.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._log.tag_config("ok",    foreground=ACCENT)
        self._log.tag_config("err",   foreground=ERR)
        self._log.tag_config("warn",  foreground=WARN)
        self._log.tag_config("info",  foreground=FG_DIM)
        self._log.tag_config("plain", foreground=FG)

    # ── Startup ───────────────────────────────

    def _startup(self):
        start = sys.argv[1] if len(sys.argv) > 1 else None
        repo  = find_repo_path(start)
        if repo:
            self._load_repo(repo)
        else:
            self._log_msg("No git repository found.", "warn")
            InitRepoDialog(self, lambda f: self._load_repo(f))
        self._check_gh_status()

    def _check_gh_status(self):
        if not gh_installed():
            self._auth_lbl.config(
                text="gh not installed — click to fix", fg=WARN)
            return
        if gh_logged_in():
            user = gh_whoami()
            self._gh_user = user
            label = f"GitHub: {user}" if user else "GitHub: logged in"
            self._auth_lbl.config(text=label, fg=ACCENT)
        else:
            self._auth_lbl.config(
                text="Not logged in to GitHub — click to login", fg=WARN)

    # ── gh auth flow ──────────────────────────

    def _ensure_gh_auth(self, then=None):
        """Ensure gh is installed and logged in, then call 'then'."""
        if not gh_installed():
            InstallGHDialog(
                self,
                on_installed=lambda: self._ensure_gh_auth(then))
            return

        if gh_logged_in():
            gh_setup_git()
            self._check_gh_status()
            if then:
                then()
            return

        def on_success(user):
            self._gh_user = user
            self._check_gh_status()
            self._log_msg(f"GitHub login successful as '{user}'", "ok")
            if then:
                then()

        GitHubBrowserLoginDialog(self, on_success=on_success)

    # ── Repo management ───────────────────────

    def _load_repo(self, repo):
        self.repo = repo
        self._repo_var.set(str(repo))
        self._log_msg(f"Repo: {repo}", "info")
        self._refresh_ui()
        issues = diagnose(repo)
        if issues:
            desc = " | ".join(d for _, d in issues)
            self._log_msg(f"Setup needed: {desc}", "warn")
            self._status_var.set("Setup needed — launching wizard...")
            self.after(400, lambda: SetupWizard(
                self, repo, issues, self._after_wizard))
        else:
            self._log_msg("Git config OK", "ok")

    def _after_wizard(self):
        self._refresh_ui()
        remaining = diagnose(self.repo)
        if remaining:
            SetupWizard(self, self.repo, remaining, self._after_wizard)
        else:
            self._log_msg("Configuration complete", "ok")

    def _pick_repo(self):
        d = filedialog.askdirectory(title="Select repository folder")
        if not d:
            return
        repo = find_repo_path(d)
        if not repo:
            if messagebox.askyesno(
                    "No repo", f"No .git found in:\n{d}\n\nInitialise here?"):
                r = run_git(["init"], Path(d))
                if r.returncode == 0:
                    self._load_repo(Path(d))
                else:
                    messagebox.showerror("Error", r.stderr)
        else:
            self._load_repo(repo)

    def _refresh_ui(self):
        if not self.repo:
            return
        branch = get_current_branch(self.repo)
        remote = get_remote_url(self.repo)
        self._branch_lbl.config(text=f"branch: {branch}  ")
        self._remote_lbl.config(text=f"Remote: {remote or '(not set)'}")

        if has_untracked_or_modified(self.repo):
            r     = run_git(["status", "--short"], self.repo, allow_fail=True)
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
            self._log_msg("Commit message is empty.", "warn"); return

        issues = diagnose(self.repo)
        if issues:
            self._log_msg("Setup incomplete — opening wizard.", "warn")
            SetupWizard(self, self.repo, issues, self._after_wizard)
            return

        if not has_untracked_or_modified(self.repo):
            self._log_msg("Nothing to commit.", "info"); return

        self._log_msg("Staging all changes...", "info")
        self._log_output(run_git(["add", "."], self.repo))

        if not has_staged_changes(self.repo):
            self._log_msg("No staged changes.", "info"); return

        self._log_msg(f'Committing: "{msg}"', "info")
        r = run_git(["commit", "-m", msg], self.repo)
        self._log_output(r)

        if r.returncode == 0:
            self._log_msg("Commit successful", "ok")
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
            self._log_msg("Setup incomplete — opening wizard.", "warn")
            SetupWizard(self, self.repo, issues, self._after_wizard)
            return

        # Always ensure authenticated before pushing
        self._ensure_gh_auth(then=self._push_now)

    def _push_now(self):
        remote = get_remote_url(self.repo)
        if not remote:
            self._log_msg("No remote configured.", "err"); return

        branch = get_current_branch(self.repo)
        self._log_msg(f"Pushing '{branch}' to {remote} ...", "info")

        r = run_git(["push", "--set-upstream", "origin", branch],
                    self.repo, allow_fail=True)
        self._log_output(r)

        if r.returncode == 0:
            self._log_msg("Push successful", "ok")
            self._refresh_ui()
        else:
            stderr = r.stderr.lower()
            if any(k in stderr for k in
                   ("authentication", "credential", "authorization",
                    "403", "401", "permission denied")):
                self._log_msg(
                    "Auth error — re-login required. Retrying...", "warn")
                run_cmd(["gh", "auth", "logout",
                         "--hostname", "github.com"], allow_fail=True)
                self._ensure_gh_auth(then=self._push_now)
            elif "rejected" in stderr:
                self._log_msg(
                    "Push rejected — pull and merge remote changes first.",
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
            self._log_msg(result.stderr.strip(),
                          "err" if result.returncode != 0 else "info")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")


# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = GitPushUI()
    app.mainloop()