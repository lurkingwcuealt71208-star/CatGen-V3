import subprocess
import sys
import os
import time
import json
import venv
import shutil
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import logging

# Set up logging to /logs
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "launcher.log")
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)

def is_venv():
    return (hasattr(sys, 'real_prefix') or (sys.base_prefix != sys.prefix))

# Load launcher config (allow setting github repo)
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
launcher_config = {}
try:
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            launcher_config = json.load(f)
except Exception:
    launcher_config = {}

class LauncherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CatGen Launcher")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Apply black -> cyan gradient style (approximate with colors)
        self.root.configure(bg='#050505')
        
        self.label = tk.Label(root, text="CatGen v4 ALPHA", font=("Arial", 16, "bold"), fg="#00FFFF", bg="#050505")
        self.label.pack(pady=12)

        # Detect OS and display installer/porting info
        try:
            if sys.platform == "win32":
                os_name = "Windows"
            elif sys.platform == "darwin":
                os_name = "macOS"
            else:
                os_name = "Linux"
        except Exception:
            os_name = "Unknown OS"

        self.os_label = tk.Label(root, text=f"{os_name}: detected installing for {os_name}",
                                 font=("Arial", 10), fg="#00FFAA", bg="#050505")
        self.os_label.pack(pady=6)

        self.status_label = tk.Label(root, text="Initializing...", font=("Arial", 10), fg="white", bg="#050505")
        self.status_label.pack(pady=8)
        
        self.progress = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=10)
        
        self.launch_btn = tk.Button(root, text="Launch Game", state="disabled", command=self.launch_game, 
                                   bg="#008B8B", fg="white", font=("Arial", 12, "bold"), width=15)
        self.launch_btn.pack(pady=20)

        # Additional controls: Update from GitHub, Recreate venv
        controls_frame = tk.Frame(root, bg="#050505")
        controls_frame.pack(pady=4)

        self.update_btn = tk.Button(controls_frame, text="Update (GitHub)", state="disabled", command=self.update_from_github,
                        bg="#005F5F", fg="white", font=("Arial", 10), width=14)
        self.update_btn.grid(row=0, column=0, padx=6)

        self.recreate_btn = tk.Button(controls_frame, text="Recreate venv", state="disabled", command=self.recreate_venv,
                          bg="#5F0000", fg="white", font=("Arial", 10), width=14)
        self.recreate_btn.grid(row=0, column=1, padx=6)
        
        self.log_dir = log_dir
        
        # Start background tasks
        threading.Thread(target=self.run_setup, daemon=True).start()
        # If configured, perform automatic update check after a short delay
        if launcher_config.get('auto_update'):
            def _auto():
                time.sleep(2)
                try:
                    self.update_from_github(auto=True)
                except Exception:
                    pass
            threading.Thread(target=_auto, daemon=True).start()

    def update_status(self, text, progress_val=None):
        self.status_label.config(text=text)
        if progress_val is not None:
            self.progress['value'] = progress_val
        logging.info(text)

    def run_setup(self):
        try:
            # 1. Venv check
            self.update_status("Checking virtual environment...", 20)
            venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
            if not os.path.exists(venv_dir):
                self.update_status("Creating virtual environment...", 30)
                venv.create(venv_dir, with_pip=True)
            
            # 2. Dependencies
            self.update_status("Verifying dependencies...", 50)
            python_exe = os.path.join(venv_dir, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(venv_dir, "bin", "python")
            req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
            if os.path.exists(req_file):
                subprocess.check_call([python_exe, "-m", "pip", "install", "-r", req_file], 
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            
            # 3. Shortcut Check
            self.update_status("Checking shortcut...", 80)
            self.check_shortcut()
            
            self.update_status("Ready to Play!", 100)
            self.launch_btn.config(state="normal")
            self.update_btn.config(state="normal")
            self.recreate_btn.config(state="normal")
            
        except Exception as e:
            logging.error(f"Setup error: {e}", exc_info=True)
            self.update_status(f"Error: {str(e)}")
            messagebox.showerror("Launcher Error", f"An error occurred during setup:\n{e}")

    def check_shortcut(self):
        if sys.platform != "win32": return
        
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_path = os.path.join(desktop, "CatGen.lnk")
        if os.path.exists(shortcut_path): return
        
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    if json.load(f).get("declined_shortcut"): return
            except: pass
            
        if messagebox.askyesno("Create Shortcut", "Would you like to create a desktop shortcut for CatGen?"):
            self.create_shortcut()
        else:
            try:
                config = {}
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f: config = json.load(f)
                config["declined_shortcut"] = True
                with open(config_path, 'w') as f: json.dump(config, f, indent=4)
            except: pass

    def create_shortcut(self):
        try:
            import winshell
            from win32com.client import Dispatch
            desktop = winshell.desktop()
            path = os.path.join(desktop, "CatGen.lnk")
            root_dir = os.path.dirname(os.path.abspath(__file__))
            python_exe = os.path.join(root_dir, ".venv", "Scripts", "python.exe")
            main_script = os.path.join(root_dir, "main.py")
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = python_exe
            shortcut.Arguments = f'"{main_script}"'
            shortcut.WorkingDirectory = root_dir
            shortcut.save()
            logging.info("Desktop shortcut created.")
        except Exception as e:
            logging.error(f"Shortcut error: {e}")

    def recreate_venv(self):
        """Delete and recreate the .venv folder and reinstall dependencies."""
        def _worker():
            try:
                self.update_status("Removing .venv...", 10)
                root_dir = os.path.dirname(os.path.abspath(__file__))
                venv_dir = os.path.join(root_dir, ".venv")
                if os.path.exists(venv_dir):
                    shutil.rmtree(venv_dir)
                self.update_status("Creating virtual environment...", 30)
                venv.create(venv_dir, with_pip=True)
                python_exe = os.path.join(venv_dir, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(venv_dir, "bin", "python")
                req_file = os.path.join(root_dir, "requirements.txt")
                if os.path.exists(req_file):
                    self.update_status("Installing dependencies...", 60)
                    subprocess.check_call([python_exe, "-m", "pip", "install", "-r", req_file])
                self.update_status("Virtualenv recreated", 100)
            except Exception as e:
                logging.error(f"Recreate venv error: {e}", exc_info=True)
                messagebox.showerror("Venv Error", f"Failed to recreate venv:\n{e}")

        threading.Thread(target=_worker, daemon=True).start()

    def update_from_github(self, auto=False):
        """Attempt to update the project from GitHub.
        If `auto` is True, perform a silent check and only update when remote `version` > local `version`.
        """
        def _version_greater(a, b):
            try:
                pa = tuple(int(x) for x in str(a).split('.'))
                pb = tuple(int(x) for x in str(b).split('.'))
                return pa > pb
            except Exception:
                return str(a) > str(b)

        def _worker():
            root_dir = os.path.dirname(os.path.abspath(__file__))
            zip_url = launcher_config.get('github_zip', "https://github.com/yourusername/CatGenV3/archive/refs/heads/main.zip")
            try:
                self.update_status("Checking for updates...", 5)
                import urllib.request, zipfile, io
                with urllib.request.urlopen(zip_url, timeout=30) as resp:
                    data = resp.read()
                z = zipfile.ZipFile(io.BytesIO(data))

                # Try to find config.json in archive to check version
                remote_version = None
                for name in z.namelist():
                    if name.endswith('config.json'):
                        with z.open(name) as f:
                            try:
                                remote_cfg = json.load(io.TextIOWrapper(f, encoding='utf-8'))
                                remote_version = remote_cfg.get('version')
                            except Exception:
                                remote_version = None
                        break

                local_version = launcher_config.get('version')
                if auto:
                    if remote_version is None:
                        logging.info("Auto-update: remote version not found; skipping")
                        self.update_status("No update available", 100)
                        return
                    if local_version is not None and not _version_greater(remote_version, local_version):
                        logging.info("Auto-update: already up-to-date")
                        self.update_status("No update available", 100)
                        return

                self.update_status("Downloading and applying update...", 30)
                # Extract to temporary folder and copy files
                tmpdir = os.path.join(root_dir, "_tmp_zip")
                if os.path.exists(tmpdir): shutil.rmtree(tmpdir)
                z.extractall(tmpdir)
                top = next(os.scandir(tmpdir)).path
                # Copy files over (preserve launcher log and user data)
                for item in os.listdir(top):
                    s = os.path.join(top, item)
                    d = os.path.join(root_dir, item)
                    if os.path.exists(d):
                        if os.path.isdir(d): shutil.rmtree(d)
                        else: os.remove(d)
                    if os.path.isdir(s): shutil.copytree(s, d)
                    else: shutil.copy2(s, d)
                shutil.rmtree(tmpdir)

                self.update_status("Update complete. Reinstalling deps...", 70)
                # Reinstall requirements into venv
                venv_dir = os.path.join(root_dir, ".venv")
                python_exe = os.path.join(venv_dir, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(venv_dir, "bin", "python")
                req_file = os.path.join(root_dir, "requirements.txt")
                if os.path.exists(req_file) and os.path.exists(python_exe):
                    subprocess.check_call([python_exe, "-m", "pip", "install", "-r", req_file])

                self.update_status("Update finished", 100)
                if not auto:
                    messagebox.showinfo("Update", "Update from GitHub finished. Relaunch launcher to apply changes.")
            except Exception as e:
                logging.error(f"Update error: {e}", exc_info=True)
                if not auto:
                    messagebox.showerror("Update Error", f"Failed to update from GitHub:\n{e}")

        threading.Thread(target=_worker, daemon=True).start()

    def launch_game(self):
        try:
            root_dir = os.path.dirname(os.path.abspath(__file__))
            python_exe = os.path.join(root_dir, ".venv", "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(root_dir, ".venv", "bin", "python")
            main_script = os.path.join(root_dir, "main.py")
            
            # Use DETACHED_PROCESS to ensure the game survives launcher close
            # and CREATE_NO_WINDOW to hide the python console for main.py
            kwargs = {}
            if sys.platform == "win32":
                kwargs['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            
            subprocess.Popen([python_exe, main_script], cwd=root_dir, **kwargs)
            logging.info("Game launched. Closing launcher.")
            self.root.destroy()
            sys.exit(0)
        except Exception as e:
            logging.error(f"Launch error: {e}")
            messagebox.showerror("Launch Error", f"Could not start game:\n{e}")

if __name__ == "__main__":
    # If not in venv and it exists, we should probably run from there, 
    # but for simplicity of a standalone launcher, it's better to stay in system python
    # and just use the venv's python to run the game.
    
    root = tk.Tk()
    app = LauncherGUI(root)
    root.mainloop()
