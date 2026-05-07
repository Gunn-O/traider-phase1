"""
Tra(i)der Smart Desktop Launcher

หน้าที่:
1. ตรวจ MT5 Desktop เปิดอยู่หรือไม่ → ถ้าไม่ → start (path จาก env หรือ default Exness)
2. รัน Backend API server (uvicorn / api_server.py)
3. รัน Frontend dev server (vite / npm run dev)
4. รอจนทั้ง 2 พร้อม (HTTP 200) แล้วเปิด browser ที่ http://localhost:3000
5. แสดง status window ผ่าน Tk + ปุ่มปิดระบบทั้งหมด
6. Health-check ทุก 5 วินาที — ถ้า service ตาย แสดงสถานะ + ลอง restart

Build เป็น .exe:
    pyinstaller --noconfirm --onefile --windowed \
                --name TraiderLauncher --icon=app_icon.ico launcher.py

Run โดยตรง:
    python launcher.py
"""
from __future__ import annotations
import os
import sys
import time
import socket
import subprocess
import threading
import urllib.request
import webbrowser
from pathlib import Path

# ── GUI ────────────────────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

# ── Config ─────────────────────────────────────────────────────
def _resolve_project_root() -> Path:
    """
    Find project root containing venv/ and api_server.py
    - When run as .py:    Path(__file__).parent
    - When frozen .exe:   sys.executable.parent (usually project root if exe sits there)
                          fallback to walking up looking for venv/
    """
    if getattr(sys, 'frozen', False):
        candidate = Path(sys.executable).resolve().parent
    else:
        candidate = Path(__file__).resolve().parent

    # Walk up looking for project markers
    for p in [candidate, *candidate.parents]:
        if (p / 'venv').is_dir() and (p / 'api_server.py').is_file():
            return p
    return candidate  # fallback

ROOT = _resolve_project_root()

# MT5 detection — try env first, then common installation paths
MT5_PATH_CANDIDATES = [
    os.getenv('MT5_TERMINAL_PATH', ''),
    r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe',
    r'C:\Program Files\MetaTrader 5\terminal64.exe',
    r'C:\Program Files (x86)\MetaTrader 5\terminal64.exe',
]

VENV_PYTHON = ROOT / 'venv' / 'Scripts' / 'python.exe'
NODE_NPM = r'C:\Program Files\nodejs\npm.cmd'  # fallback if not in PATH

BACKEND_HOST = '127.0.0.1'
BACKEND_PORT = 8080
FRONTEND_HOST = 'localhost'
FRONTEND_PORT = 3000
BROWSER_URL = f'http://{FRONTEND_HOST}:{FRONTEND_PORT}'

STARTUP_TIMEOUT_SEC = 60
HEALTH_CHECK_INTERVAL_SEC = 5


# ── Detection helpers ──────────────────────────────────────────

def find_mt5_path() -> str | None:
    for p in MT5_PATH_CANDIDATES:
        if p and Path(p).is_file():
            return p
    return None


def is_mt5_running() -> bool:
    try:
        r = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq terminal64.exe'],
            capture_output=True, text=True, timeout=5,
        )
        return 'terminal64.exe' in r.stdout
    except Exception:
        return False


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


# ── Service launchers ──────────────────────────────────────────

class ServiceManager:
    """Track all subprocesses + provide cleanup"""

    def __init__(self, log_callback=None):
        self.procs: list[subprocess.Popen] = []
        self.log = log_callback or (lambda msg: print(msg))

    def start(self, name: str, cmd: list[str], cwd: Path | None = None,
              env_extra: dict | None = None, use_shell: bool = False) -> subprocess.Popen:
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        if env_extra:
            env.update(env_extra)
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            # Windows .cmd files (npm.cmd) require shell=True OR full path resolution
            if use_shell:
                proc = subprocess.Popen(
                    ' '.join(cmd) if isinstance(cmd, list) else cmd,
                    cwd=str(cwd) if cwd else None,
                    env=env, creationflags=creationflags, shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                proc = subprocess.Popen(
                    cmd, cwd=str(cwd) if cwd else None,
                    env=env, creationflags=creationflags,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            self.procs.append(proc)
            self.log(f"[+] {name} started (pid={proc.pid})")
            return proc
        except Exception as e:
            self.log(f"[!] {name} FAILED to start: {e}")
            return None

    def stop_all(self):
        for proc in self.procs:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.log(f"[x] Stopped {len(self.procs)} processes")
        self.procs.clear()


# ── Startup orchestration ──────────────────────────────────────

def ensure_mt5(log) -> bool:
    """Start MT5 if not already running. Returns True on success."""
    if is_mt5_running():
        log("[✓] MT5 already running")
        return True
    mt5_path = find_mt5_path()
    if not mt5_path:
        log("[!] MT5 path not found — set MT5_TERMINAL_PATH env or install MT5")
        return False
    log(f"[~] Starting MT5: {mt5_path}")
    try:
        # Detached so it survives launcher exit
        subprocess.Popen([mt5_path], creationflags=subprocess.DETACHED_PROCESS if sys.platform == 'win32' else 0)
    except Exception as e:
        log(f"[!] MT5 start failed: {e}")
        return False
    # Wait up to 15s for process to appear
    for _ in range(15):
        if is_mt5_running():
            log("[✓] MT5 started")
            return True
        time.sleep(1)
    log("[!] MT5 process not detected after 15s")
    return False


def ensure_backend(svc: ServiceManager, log) -> bool:
    if http_ok(f'http://{BACKEND_HOST}:{BACKEND_PORT}/api/status'):
        log(f"[✓] Backend already running on {BACKEND_PORT}")
        return True
    if not VENV_PYTHON.is_file():
        log(f"[!] venv python not found: {VENV_PYTHON}")
        return False
    log(f"[~] Starting backend (api_server.py)…")
    svc.start('Backend', [str(VENV_PYTHON), 'api_server.py'], cwd=ROOT)
    return wait_until(lambda: http_ok(f'http://{BACKEND_HOST}:{BACKEND_PORT}/api/status'),
                      STARTUP_TIMEOUT_SEC, log, 'Backend')


def ensure_frontend(svc: ServiceManager, log) -> bool:
    if http_ok(BROWSER_URL):
        log(f"[✓] Frontend already running on {FRONTEND_PORT}")
        return True
    # Find npm.cmd absolute path (PATH may not include nodejs in launched process)
    npm_path = shutil_which('npm') or shutil_which('npm.cmd') or NODE_NPM
    if not Path(npm_path).is_file():
        log(f"[!] npm not found at {npm_path}")
        return False
    log(f"[~] Starting frontend (npm run dev) via shell…")
    # npm.cmd ต้องใช้ shell=True บน Windows — Popen ไม่สามารถ exec .cmd ตรง ๆ
    svc.start('Frontend', ['npm', 'run', 'dev'],
              cwd=ROOT / 'frontend', use_shell=True)
    return wait_until(lambda: http_ok(BROWSER_URL),
                      STARTUP_TIMEOUT_SEC, log, 'Frontend')


def shutil_which(cmd: str) -> str | None:
    import shutil
    return shutil.which(cmd)


def wait_until(check_fn, timeout: int, log, label: str) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_fn():
            log(f"[✓] {label} ready")
            return True
        time.sleep(1)
    log(f"[!] {label} not ready after {timeout}s")
    return False


# ── GUI ───────────────────────────────────────────────────────

class LauncherGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Tra(i)der Launcher")
        root.geometry("560x450")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.svc = ServiceManager(log_callback=self.log)
        self.status_vars = {
            'mt5':      tk.StringVar(value='⏳ Checking…'),
            'backend':  tk.StringVar(value='⏳ Checking…'),
            'frontend': tk.StringVar(value='⏳ Checking…'),
        }
        self._build_ui()
        self.health_thread = None
        self.health_running = False

    def _build_ui(self):
        title = tk.Label(self.root, text="Tra(i)der Trading Bot",
                         font=('Segoe UI', 16, 'bold'), pady=10)
        title.pack()

        frame = tk.Frame(self.root)
        frame.pack(pady=10, padx=20, fill='x')

        for label, key in [('MT5 Terminal', 'mt5'),
                           ('Backend API (8080)', 'backend'),
                           ('Frontend UI (3000)', 'frontend')]:
            row = tk.Frame(frame)
            row.pack(fill='x', pady=4)
            tk.Label(row, text=label, width=22, anchor='w',
                     font=('Segoe UI', 10)).pack(side='left')
            tk.Label(row, textvariable=self.status_vars[key],
                     font=('Segoe UI', 10, 'bold')).pack(side='left')

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        self.start_btn = ttk.Button(btn_frame, text='▶ Start All',
                                    command=self.start_all, width=16)
        self.start_btn.pack(side='left', padx=5)
        self.open_btn = ttk.Button(btn_frame, text='🌐 Open Dashboard',
                                   command=self.open_dashboard, width=18, state='disabled')
        self.open_btn.pack(side='left', padx=5)
        self.stop_btn = ttk.Button(btn_frame, text='⏹ Stop All',
                                   command=self.stop_all, width=14, state='disabled')
        self.stop_btn.pack(side='left', padx=5)

        # Log box
        log_label = tk.Label(self.root, text='Log:', anchor='w')
        log_label.pack(fill='x', padx=20)
        self.log_box = scrolledtext.ScrolledText(self.root, height=12,
                                                 font=('Consolas', 9), state='disabled')
        self.log_box.pack(fill='both', expand=True, padx=20, pady=(0, 10))

    def log(self, msg: str):
        ts = time.strftime('%H:%M:%S')
        line = f"[{ts}] {msg}\n"
        self.log_box.config(state='normal')
        self.log_box.insert('end', line)
        self.log_box.see('end')
        self.log_box.config(state='disabled')

    def set_status(self, key: str, ok: bool, msg: str = ''):
        icon = '✅' if ok else '❌'
        self.status_vars[key].set(f"{icon} {msg or ('OK' if ok else 'OFF')}")

    def start_all(self):
        self.start_btn.config(state='disabled')
        threading.Thread(target=self._start_thread, daemon=True).start()

    def _start_thread(self):
        # 1. MT5
        ok_mt5 = ensure_mt5(self.log)
        self.set_status('mt5', ok_mt5, 'Running' if ok_mt5 else 'Not detected')

        # 2. Backend
        ok_be = ensure_backend(self.svc, self.log)
        self.set_status('backend', ok_be, f'Listening :{BACKEND_PORT}' if ok_be else 'Failed')

        # 3. Frontend
        ok_fe = ensure_frontend(self.svc, self.log)
        self.set_status('frontend', ok_fe, f'Listening :{FRONTEND_PORT}' if ok_fe else 'Failed')

        # 4. Open browser
        if ok_be and ok_fe:
            self.log(f"[~] Opening browser at {BROWSER_URL}")
            webbrowser.open(BROWSER_URL)
            self.open_btn.config(state='normal')

        self.stop_btn.config(state='normal')

        # Start health monitor
        self.health_running = True
        self.health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self.health_thread.start()

    def _health_loop(self):
        while self.health_running:
            time.sleep(HEALTH_CHECK_INTERVAL_SEC)
            self.set_status('mt5', is_mt5_running(),
                            'Running' if is_mt5_running() else 'Not detected')
            self.set_status('backend', http_ok(f'http://{BACKEND_HOST}:{BACKEND_PORT}/api/status'),
                            f'Listening :{BACKEND_PORT}' if http_ok(f'http://{BACKEND_HOST}:{BACKEND_PORT}/api/status') else 'OFF')
            self.set_status('frontend', is_port_open(FRONTEND_HOST, FRONTEND_PORT),
                            f'Listening :{FRONTEND_PORT}' if is_port_open(FRONTEND_HOST, FRONTEND_PORT) else 'OFF')

    def open_dashboard(self):
        webbrowser.open(BROWSER_URL)

    def stop_all(self):
        self.health_running = False
        self.svc.stop_all()
        for k in self.status_vars:
            self.status_vars[k].set('⏹ Stopped')
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.open_btn.config(state='disabled')

    def on_close(self):
        self.stop_all()
        self.root.destroy()


def main_gui():
    root = tk.Tk()
    LauncherGUI(root)
    root.mainloop()


def main_cli():
    """Headless mode — no GUI, just launch + open browser"""
    print("=" * 50)
    print("  Tra(i)der Smart Launcher (CLI)")
    print("=" * 50)
    log = print
    svc = ServiceManager(log_callback=log)
    ok_mt5 = ensure_mt5(log)
    ok_be = ensure_backend(svc, log)
    ok_fe = ensure_frontend(svc, log)
    if ok_be and ok_fe:
        log(f"[~] Opening browser at {BROWSER_URL}")
        webbrowser.open(BROWSER_URL)
    log("\n--- Status ---")
    log(f"  MT5      : {'OK' if ok_mt5 else 'FAIL'}")
    log(f"  Backend  : {'OK' if ok_be else 'FAIL'}")
    log(f"  Frontend : {'OK' if ok_fe else 'FAIL'}")
    log("\nPress Ctrl+C to stop all services")
    try:
        while True:
            time.sleep(HEALTH_CHECK_INTERVAL_SEC)
    except KeyboardInterrupt:
        log("\n[~] Shutting down…")
        svc.stop_all()


if __name__ == '__main__':
    if HAS_GUI and '--cli' not in sys.argv:
        main_gui()
    else:
        main_cli()
