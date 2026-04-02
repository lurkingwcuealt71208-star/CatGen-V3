from __future__ import annotations

import io
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import venv
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

SOURCE_ROOT = Path(__file__).resolve().parent
SOURCE_CONFIG_PATH = SOURCE_ROOT / "config.json"
DEFAULT_SOURCE_CONFIG = {
    "version": "0.0.0",
    "github_api": "https://api.github.com/repos/PLACEHOLDER/CatGenV3/releases/latest",
    "github_zip": "https://github.com/PLACEHOLDER/CatGenV3/archive/refs/heads/main.zip",
}


def _user_data_dir() -> Path:
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".local" / "share"))
    return base / "CatGen"


STATE_DIR = _user_data_dir()
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = STATE_DIR / "launcher.log"
STATE_PATH = STATE_DIR / "launcher_state.json"

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="w",
)


def _load_source_config() -> dict:
    if SOURCE_CONFIG_PATH.exists():
        try:
            with SOURCE_CONFIG_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                merged = dict(DEFAULT_SOURCE_CONFIG)
                merged.update(data)
                return merged
        except Exception as exc:
            logging.warning("Failed to read source config: %s", exc)
    return dict(DEFAULT_SOURCE_CONFIG)


SOURCE_CONFIG = _load_source_config()
LOCAL_VERSION = str(SOURCE_CONFIG.get("version", "0.0.0"))
GITHUB_API = str(SOURCE_CONFIG.get("github_api", DEFAULT_SOURCE_CONFIG["github_api"]))
GITHUB_ZIP = str(SOURCE_CONFIG.get("github_zip", DEFAULT_SOURCE_CONFIG["github_zip"]))

DEFAULT_STATE = {
    "install_dir": "",
    "auto_update": False,
    "declined_shortcut": False,
}


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            with STATE_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                state = dict(DEFAULT_STATE)
                state.update(data)
                return state
        except Exception as exc:
            logging.warning("Failed to read launcher state: %s", exc)
    return dict(DEFAULT_STATE)


def _requirements_path() -> Path:
    override = os.environ.get("CATGEN_REQUIREMENTS_PATH")
    if override:
        candidate = Path(override).expanduser()
        if candidate.exists():
            return candidate
    return SOURCE_ROOT / "requirements.txt"


def _save_state(state: dict) -> None:
    try:
        with STATE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=4)
    except Exception as exc:
        logging.error("Failed to save launcher state: %s", exc)


def _default_install_dir() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop / "CatGen"
    return Path.home() / "CatGen"


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _ignore_source_files(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        ".venv",
        "Logs",
        "__pycache__",
        ".pytest_cache",
        ".git",
        "MacOS",
        "Linux",
        "launcher.py",
        "launcher_core.py",
    }
    result: set[str] = set()
    for name in names:
        if name in ignored or name.endswith(".pyc") or name.endswith(".pyo") or name.endswith(".log"):
            result.add(name)
    return result


def _version_tuple(raw_version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(raw_version).lstrip("v").split(".")[:3])
    except Exception:
        return (0, 0, 0)


def _is_valid_install(install_dir: Path | None) -> bool:
    if install_dir is None:
        return False
    main_script = install_dir / "Main" / "main.py"
    return main_script.exists()


def _python_executable(install_dir: Path) -> Path:
    if sys.platform == "win32":
        candidates = [install_dir / ".venv" / "Scripts" / "python.exe"]
    else:
        candidates = [install_dir / ".venv" / "bin" / "python3", install_dir / ".venv" / "bin" / "python"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _ensure_venv(install_dir: Path) -> Path:
    python_exe = _python_executable(install_dir)
    if not python_exe.exists():
        logging.info("Creating virtual environment in %s", install_dir)
        venv.create(str(install_dir / ".venv"), with_pip=True)
    return _python_executable(install_dir)


def _install_requirements(install_dir: Path) -> None:
    requirements = install_dir / "requirements.txt"
    source_requirements = _requirements_path()
    if source_requirements.exists():
        requirements = source_requirements
    if not requirements.exists():
        return
    python_exe = _ensure_venv(install_dir)
    command = [str(python_exe), "-m", "pip", "install", "-r", str(requirements), "--quiet"]
    if sys.platform == "win32":
        completed = subprocess.run(
            command,
            creationflags=subprocess.CREATE_NO_WINDOW,
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "pip install failed").strip()
        raise RuntimeError(f"Dependency installation failed (exit {completed.returncode}): {stderr}")


def _copy_source_to_install(install_dir: Path) -> None:
    install_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SOURCE_ROOT,
        install_dir,
        dirs_exist_ok=True,
        ignore=_ignore_source_files,
    )


def _apply_update(zip_url: str, install_dir: Path, status_cb) -> bool:
    try:
        status_cb("Downloading update ...", 10)
        with urllib.request.urlopen(zip_url, timeout=60) as response:
            zip_data = response.read()
        status_cb("Extracting update ...", 60)
        archive = zipfile.ZipFile(io.BytesIO(zip_data))

        backup_dir = install_dir.parent / f"CatGen_backup_{int(time.time())}"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(
            install_dir,
            backup_dir,
            ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", "Logs"),
        )
        logging.info("Backup created at %s", backup_dir)

        names = archive.namelist()
        top_prefix = ""
        if names:
            first = names[0]
            if "/" in first:
                top_prefix = first.split("/")[0] + "/"

        for name in names:
            if top_prefix and not name.startswith(top_prefix):
                continue
            relative_name = name[len(top_prefix):] if top_prefix else name
            if not relative_name or relative_name.startswith(".venv"):
                continue
            if relative_name in {"launcher.py", "launcher_core.py"}:
                continue
            if relative_name.startswith("MacOS/") or relative_name.startswith("Linux/"):
                continue
            target = install_dir / relative_name
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        status_cb("Update applied", 100)
        return True
    except Exception as exc:
        logging.error("Update failed: %s", exc, exc_info=True)
        status_cb(f"Update failed: {exc}", 0)
        return False


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.state = _load_state()
        self.install_dir: Path | None = None
        self._pending_initial_prompt = False

        root.title("CatGen Launcher")
        root.geometry("520x380")
        root.resizable(False, False)

        self._bg = tk.Canvas(root, width=520, height=380, highlightthickness=0, bd=0)
        self._bg.place(x=0, y=0, width=520, height=380)
        self._draw_background()

        tk.Label(
            root,
            text="CatGen Launcher",
            font=("Arial", 20, "bold"),
            fg="#00cccc",
            bg="#0a0a0a",
        ).pack(pady=(16, 2))
        self._version_label = tk.Label(
            root,
            text=f"v{LOCAL_VERSION}  —  {platform.system()}",
            font=("Arial", 10),
            fg="#e0e0e0",
            bg="#0a0a0a",
        )
        self._version_label.pack()

        self._install_label_var = tk.StringVar(value="Install path not selected")
        self._install_label = tk.Label(
            root,
            textvariable=self._install_label_var,
            font=("Arial", 9),
            fg="#e0e0e0",
            bg="#0a0a0a",
            wraplength=470,
        )
        self._install_label.pack(pady=(10, 4))

        self._status_var = tk.StringVar(value="Waiting for install path ...")
        self._status_label = tk.Label(
            root,
            textvariable=self._status_var,
            font=("Arial", 10),
            fg="#e0e0e0",
            bg="#0a0a0a",
            wraplength=470,
        )
        self._status_label.pack(pady=(6, 6))

        style = ttk.Style()
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure(
            "Launcher.Horizontal.TProgressbar",
            troughcolor="#1a1a1a",
            background="#00cccc",
            lightcolor="#00cccc",
            darkcolor="#00cccc",
        )
        self._progress = ttk.Progressbar(
            root,
            orient="horizontal",
            length=410,
            mode="determinate",
            style="Launcher.Horizontal.TProgressbar",
        )
        self._progress.pack(pady=(0, 10))

        main_row = tk.Frame(root, bg="#0a0a0a")
        main_row.pack(pady=4)
        self._launch_btn = self._button(main_row, "Launch", self._launch_game, width=11, fg="#00ffcc")
        self._update_btn = self._button(main_row, "Update", self._manual_update, width=11)
        self._reinstall_btn = self._button(main_row, "Reinstall", self._reinstall, width=11)
        self._remove_btn = self._button(main_row, "Remove", self._remove_install, width=11, bg="#4b0000")

        for widget in (self._launch_btn, self._update_btn, self._reinstall_btn, self._remove_btn):
            widget.pack(side="left", padx=6)

        bottom_row = tk.Frame(root, bg="#0a0a0a")
        bottom_row.pack(pady=(8, 2))
        self._change_path_btn = self._button(bottom_row, "Change install path", self._change_install_path, width=18)
        self._quit_btn = self._button(bottom_row, "Quit", self.root.destroy, width=10, bg="#222222")
        self._change_path_btn.pack(side="left", padx=6)
        self._quit_btn.pack(side="left", padx=6)

        self._set_buttons_enabled(False)

        if self.state.get("auto_update"):
            threading.Thread(target=self._auto_update_check, daemon=True).start()

        root.after(0, self._bootstrap)

    def _draw_background(self) -> None:
        for y in range(380):
            t = max(0.0, min(1.0, y / 379))
            r = int(10 * (1 - t))
            g = int(10 + 140 * t)
            b = int(10 + 140 * t)
            self._bg.create_line(0, y, 520, y, fill=f"#{r:02x}{g:02x}{b:02x}")

    def _button(self, parent, text, command, width=12, bg="#004444", fg="#e0e0e0") -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground="#006666",
            activeforeground="#e0e0e0",
            font=("Arial", 10, "bold"),
            width=width,
            relief="flat",
            cursor="hand2",
        )

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._launch_btn.configure(state=state)
        self._update_btn.configure(state=state)
        self._reinstall_btn.configure(state=state)
        self._remove_btn.configure(state=state)

    def _set_status(self, message: str, percent: int | None = None, color: str = "#e0e0e0") -> None:
        def _apply() -> None:
            self._status_var.set(message)
            self._status_label.configure(fg=color)
            if percent is not None:
                self._progress.configure(value=percent)
        self.root.after(0, _apply)
        logging.info("%s", message)

    def _call_ui(self, func, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)

        result: dict[str, object] = {}
        finished = threading.Event()

        def _runner() -> None:
            try:
                result["value"] = func(*args, **kwargs)
            except Exception as exc:
                result["error"] = exc
            finally:
                finished.set()

        self.root.after(0, _runner)
        finished.wait()
        if "error" in result:
            raise result["error"]  # type: ignore[misc]
        return result.get("value")

    def _askyesno(self, title: str, message: str) -> bool:
        return bool(self._call_ui(messagebox.askyesno, title, message, parent=self.root))

    def _showinfo(self, title: str, message: str) -> None:
        self._call_ui(messagebox.showinfo, title, message, parent=self.root)

    def _showerror(self, title: str, message: str) -> None:
        self._call_ui(messagebox.showerror, title, message, parent=self.root)

    def _refresh_install_label(self) -> None:
        if self.install_dir is None:
            self._install_label_var.set("Install path not selected")
        else:
            self._install_label_var.set(f"Install path: {self.install_dir}")

    def _current_version(self) -> str:
        if self.install_dir is not None:
            config_path = self.install_dir / "config.json"
            if config_path.exists():
                try:
                    with config_path.open("r", encoding="utf-8") as handle:
                        data = json.load(handle)
                    if isinstance(data, dict) and data.get("version"):
                        return str(data.get("version"))
                except Exception:
                    pass
        return LOCAL_VERSION

    def _bootstrap(self) -> None:
        saved_path = str(self.state.get("install_dir", "")).strip()
        if saved_path:
            candidate = Path(saved_path).expanduser()
            if _is_valid_install(candidate):
                self.install_dir = candidate.resolve()
                self._refresh_install_label()
                self._set_status("Found existing install", 10)
                self._setup_ready()
                return

        self._pending_initial_prompt = True
        chosen = self._prompt_for_install_path()
        self._pending_initial_prompt = False
        if chosen is None:
            self.root.destroy()
            return

        self._start_install_or_attach(chosen)

    def _prompt_for_install_path(self) -> Path | None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Install Directory")
        dialog.geometry("520x180")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#0a0a0a")

        choice: dict[str, Path | None] = {"value": None}
        default_dir = self.state.get("install_dir") or str(_default_install_dir())
        path_var = tk.StringVar(value=str(default_dir))

        tk.Label(
            dialog,
            text="Choose where CatGen will be installed.",
            font=("Arial", 12, "bold"),
            fg="#00cccc",
            bg="#0a0a0a",
        ).pack(pady=(14, 6))
        tk.Label(
            dialog,
            text="The launcher will use a CatGen folder on Desktop or the closest equivalent by default.",
            font=("Arial", 9),
            fg="#e0e0e0",
            bg="#0a0a0a",
        ).pack(pady=(0, 10))

        entry = tk.Entry(dialog, textvariable=path_var, width=70)
        entry.pack(padx=14, pady=(0, 12), fill="x")

        button_row = tk.Frame(dialog, bg="#0a0a0a")
        button_row.pack(pady=4)

        def _pick_directory() -> None:
            start_dir = path_var.get().strip() or str(_default_install_dir())
            selected = filedialog.askdirectory(parent=dialog, initialdir=start_dir, title="Choose install directory")
            if selected:
                path_var.set(selected)

        def _use_selected() -> None:
            raw_value = path_var.get().strip()
            if not raw_value:
                return
            choice["value"] = Path(raw_value).expanduser().resolve()
            dialog.destroy()

        def _quit() -> None:
            choice["value"] = None
            dialog.destroy()

        tk.Button(button_row, text="Change install path", command=_pick_directory, width=18).pack(side="left", padx=6)
        tk.Button(button_row, text="Ok", command=_use_selected, width=10).pack(side="left", padx=6)
        tk.Button(button_row, text="Quit", command=_quit, width=10).pack(side="left", padx=6)

        dialog.protocol("WM_DELETE_WINDOW", _quit)
        self.root.wait_window(dialog)
        return choice["value"]

    def _start_install_or_attach(self, install_dir: Path) -> None:
        install_dir = install_dir.expanduser().resolve()
        if _path_within(install_dir, SOURCE_ROOT):
            self._showerror("Invalid path", "Choose an install directory outside the launcher folder.")
            if self._pending_initial_prompt:
                chosen = self._prompt_for_install_path()
                if chosen is None:
                    self.root.destroy()
                    return
                self._start_install_or_attach(chosen)
            return

        self.install_dir = install_dir
        self.state["install_dir"] = str(install_dir)
        _save_state(self.state)
        self._refresh_install_label()

        if _is_valid_install(install_dir):
            self._set_status("Using existing install", 20)
            self._setup_ready()
            return

        self._set_buttons_enabled(False)
        threading.Thread(target=self._install_worker, args=(install_dir,), daemon=True).start()

    def _install_worker(self, install_dir: Path) -> None:
        try:
            self._set_status("Copying game files ...", 10)
            _copy_source_to_install(install_dir)
            self._set_status("Creating virtual environment ...", 35)
            _ensure_venv(install_dir)
            self._set_status("Installing dependencies ...", 60)
            _install_requirements(install_dir)
            self.install_dir = install_dir
            self.state["install_dir"] = str(install_dir)
            _save_state(self.state)
            self._set_status("Install complete", 100, color="#44ff88")
            self._setup_ready()
        except Exception as exc:
            logging.error("Install failed: %s", exc, exc_info=True)
            self._set_status(f"Install failed: {exc}", 0, color="#ff4444")
            self._showerror("Install Error", str(exc))

    def _setup_ready(self) -> None:
        self._refresh_install_label()
        self._set_buttons_enabled(True)
        self._set_status(f"Ready for {self.install_dir}", 100, color="#44ff88")

    def _manual_update(self) -> None:
        if self.install_dir is None or not _is_valid_install(self.install_dir):
            self._showerror("Update", "No valid install is selected.")
            return
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _check_for_update(self) -> tuple[bool, str, str]:
        request = urllib.request.Request(
            GITHUB_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "CatGenLauncher"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode())
        remote_version = data.get("tag_name", "").lstrip("v") or data.get("name", "0.0.0")
        assets = data.get("assets", [])
        download_url = next(
            (asset["browser_download_url"] for asset in assets if asset.get("name", "").endswith(".zip")),
            GITHUB_ZIP,
        )
        return _version_tuple(remote_version) > _version_tuple(self._current_version()), remote_version, download_url

    def _update_worker(self) -> None:
        assert self.install_dir is not None
        try:
            self._set_status("Checking for updates ...", 10)
            available, remote_version, download_url = self._check_for_update()
            if not available:
                self._set_status("Already up to date", 100, color="#44ff88")
                return
            if not self._askyesno(
                "Update available",
                f"CatGen v{remote_version} is available. Apply update now?",
            ):
                self._set_status("Update cancelled", 100, color="#e0e0e0")
                return
            ok = _apply_update(download_url, self.install_dir, self._set_status)
            if ok:
                self._ensure_post_update_dependencies()
                self._showinfo("Updated", "Update complete. Restart the launcher if needed.")
        except Exception as exc:
            logging.error("Update check failed: %s", exc, exc_info=True)
            self._set_status(f"Update failed: {exc}", 0, color="#ff4444")
            self._showerror("Update Error", str(exc))

    def _ensure_post_update_dependencies(self) -> None:
        if self.install_dir is None:
            return
        try:
            self._set_status("Verifying dependencies ...", 75)
            _ensure_venv(self.install_dir)
            _install_requirements(self.install_dir)
            self._set_status("Update applied", 100, color="#44ff88")
        except Exception as exc:
            logging.error("Post-update dependency check failed: %s", exc, exc_info=True)
            self._set_status(f"Update applied with warnings: {exc}", 100, color="#ffcc66")

    def _auto_update_check(self) -> None:
        time.sleep(2)
        if self.install_dir is None or not _is_valid_install(self.install_dir):
            return
        try:
            available, remote_version, download_url = self._check_for_update()
            if not available:
                return
            if self._askyesno(
                "Update available",
                f"CatGen v{remote_version} is available. Update now?",
            ):
                ok = _apply_update(download_url, self.install_dir, self._set_status)
                if ok:
                    self._ensure_post_update_dependencies()
        except Exception as exc:
            logging.warning("Auto update check failed: %s", exc)

    def _reinstall(self) -> None:
        if self.install_dir is None:
            self._showerror("Reinstall", "No install is selected.")
            return
        if not self._askyesno(
            "Reinstall",
            "This will reinstall the game files into the selected directory. Continue?",
        ):
            return
        threading.Thread(target=self._install_worker, args=(self.install_dir,), daemon=True).start()

    def _remove_install(self) -> None:
        if self.install_dir is None:
            self._showerror("Remove", "No install is selected.")
            return
        if not self._askyesno(
            "Remove install",
            f"This will delete the install directory:\n\n{self.install_dir}\n\nContinue?",
        ):
            return
        try:
            if self.install_dir.exists():
                shutil.rmtree(self.install_dir)
            self.state["install_dir"] = ""
            _save_state(self.state)
            self.install_dir = None
            self._refresh_install_label()
            self._set_buttons_enabled(False)
            self._set_status("Install removed", 0, color="#44ff88")
            chosen = self._prompt_for_install_path()
            if chosen is None:
                self.root.destroy()
                return
            self._start_install_or_attach(chosen)
        except Exception as exc:
            logging.error("Remove failed: %s", exc, exc_info=True)
            self._showerror("Remove Error", str(exc))

    def _change_install_path(self) -> None:
        chosen = self._prompt_for_install_path()
        if chosen is None:
            return
        self._start_install_or_attach(chosen)

    def _launch_game(self) -> None:
        if self.install_dir is None or not _is_valid_install(self.install_dir):
            self._showerror("Launch", "No valid install is selected.")
            return
        main_script = self.install_dir / "Main" / "main.py"
        if not main_script.exists():
            self._showerror("Launch", "Main/main.py is missing from the selected install.")
            return
        python_exe = _python_executable(self.install_dir)
        if not python_exe.exists():
            self._showerror("Launch", ".venv is missing. Reinstall the game first.")
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    [str(python_exe), str(main_script)],
                    cwd=str(self.install_dir),
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.Popen([str(python_exe), str(main_script)], cwd=str(self.install_dir))
            self.root.after(400, self.root.destroy)
        except Exception as exc:
            logging.error("Launch failed: %s", exc, exc_info=True)
            self._showerror("Launch Error", str(exc))


def main() -> None:
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
