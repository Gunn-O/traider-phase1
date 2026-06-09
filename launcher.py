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
import json
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

# Auto-resume: api_server writes this file on every /api/start, removes entries on
# /api/stop. Each entry = one bot config. Launcher re-issues /api/start for each
# session on boot so multi-bot setups survive WU reboots.
SESSIONS_FILE = ROOT / 'last_sessions.json'


def _try_auto_resume(log) -> None:
    if not SESSIONS_FILE.is_file():
        return
    try:
        sessions = json.loads(SESSIONS_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        log(f"[!] last_sessions.json unreadable: {e}")
        return
    if not isinstance(sessions, list) or not sessions:
        return
    log(f"[~] Auto-resuming {len(sessions)} bot(s)...")
    for cfg in sessions:
        bot_label = f"{cfg.get('tf')}/{cfg.get('mode')}/{cfg.get('symbol')}"
        try:
            req = urllib.request.Request(
                f'http://{BACKEND_HOST}:{BACKEND_PORT}/api/start',
                data=json.dumps(cfg).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                log(f"[✓] Resumed {bot_label} (HTTP {r.status})")
        except Exception as e:
            log(f"[!] Resume {bot_label} failed: {e}")


# ── Detection helpers ──────────────────────────────────────────

def find_mt5_path() -> str | None:
    for p in MT5_PATH_CANDIDATES:
        if p and Path(p).is_file():
            return p
    return None


def is_mt5_running() -> bool:
    try:
        # CREATE_NO_WINDOW ป้องกัน console เด้งทุก 5 วินาที จาก health-loop
        kwargs = {'capture_output': True, 'text': True, 'timeout': 5}
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq terminal64.exe'], **kwargs)
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

        # Windows: hide console + suppress window flashes from child processes
        # CREATE_NO_WINDOW alone doesn't propagate through cmd.exe / npm.cmd / node;
        # STARTUPINFO with SW_HIDE forces every spawned console to start hidden.
        creationflags = 0
        startupinfo = None
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        try:
            # Resolve npm.cmd / .cmd files to absolute path so shell=True isn't needed —
            # shell=True spawns cmd.exe which flashes a console even with CREATE_NO_WINDOW.
            if use_shell and isinstance(cmd, list) and cmd and cmd[0] in ('npm', 'npx', 'node'):
                resolved = shutil_which(cmd[0]) or shutil_which(cmd[0] + '.cmd')
                if resolved:
                    cmd = [resolved] + cmd[1:]
                    use_shell = False  # call directly — no shell needed

            if use_shell:
                proc = subprocess.Popen(
                    ' '.join(cmd) if isinstance(cmd, list) else cmd,
                    cwd=str(cwd) if cwd else None,
                    env=env, creationflags=creationflags, shell=True,
                    startupinfo=startupinfo,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                proc = subprocess.Popen(
                    cmd, cwd=str(cwd) if cwd else None,
                    env=env, creationflags=creationflags,
                    startupinfo=startupinfo,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            self.procs.append(proc)
            self.log(f"[+] {name} started (pid={proc.pid})")
            return proc
        except Exception as e:
            self.log(f"[!] {name} FAILED to start: {e}")
            return None

    def _kill_tree(self, pid: int) -> bool:
        """
        Kill process and all descendants. On Windows, terminate() ฆ่าได้แค่ parent —
        npm.cmd → cmd.exe → node.exe → vite workers ต้องใช้ taskkill /F /T เพื่อล้าง tree.
        """
        if sys.platform == 'win32':
            try:
                r = subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(pid)],
                    capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return r.returncode == 0
            except Exception:
                return False
        return False  # POSIX: rely on terminate() which sends SIGTERM to group

    def _kill_by_port(self, port: int) -> int:
        """
        Fallback for taskkill /T missing detached children (vite sometimes spawns
        workers that escape the tree). Find PID(s) listening on `port` and kill.
        Returns count of PIDs killed.
        """
        if sys.platform != 'win32':
            return 0
        killed = 0
        try:
            r = subprocess.run(
                ['netstat', '-ano', '-p', 'TCP'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            pids = set()
            target = f':{port}'
            for line in r.stdout.splitlines():
                # Lines look like:  TCP    127.0.0.1:3000   0.0.0.0:0   LISTENING   12345
                parts = line.split()
                if len(parts) >= 5 and 'LISTENING' in line:
                    local = parts[1]
                    if local.endswith(target):
                        try: pids.add(int(parts[-1]))
                        except ValueError: pass
            for pid in pids:
                try:
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(pid)],
                        capture_output=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    killed += 1
                except Exception:
                    pass
        except Exception as e:
            self.log(f"[!] _kill_by_port({port}) failed: {e}")
        return killed

    def stop_all(self):
        killed = 0
        for proc in self.procs:
            try:
                if sys.platform == 'win32':
                    # Tree-kill: handles npm → node → vite worker chain
                    if self._kill_tree(proc.pid):
                        killed += 1
                        continue
                # POSIX or taskkill failed — fall back to terminate
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                killed += 1
            except Exception as e:
                self.log(f"[!] kill pid={proc.pid} failed: {e}")

        # Safety net: kill anything still listening on backend/frontend ports.
        # vite occasionally spawns workers that detach from the tree → taskkill /T misses them.
        leftover = self._kill_by_port(BACKEND_PORT) + self._kill_by_port(FRONTEND_PORT)
        if leftover:
            self.log(f"[x] Killed {leftover} extra process(es) holding ports {BACKEND_PORT}/{FRONTEND_PORT}")

        self.log(f"[x] Stopped {killed}/{len(self.procs)} tracked + {leftover} leftover")
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

        # 2b. Auto-resume bot from previous session (after launcher restart, WU reboot, etc.)
        if ok_be:
            _try_auto_resume(self.log)

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
    gui = LauncherGUI(root)
    # Auto-trigger Start All so the launcher boots services without a click —
    # required for the scheduled-task path (Windows Update reboot → user logon →
    # task fires → launcher must come up working).
    root.after(500, gui.start_all)
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
