#!/usr/bin/env python3
"""
Tra(i)der Phase I v2.1 - Development Server Runner
Starts both FastAPI backend and Vite frontend dev server
"""

import subprocess
import sys
import os
import signal
import time
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent

# Process tracking
processes = []

def cleanup(signum=None, frame=None):
    """Kill all child processes on exit"""
    print("\n🛑 Shutting down servers...")
    for proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except:
            proc.kill()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def main():
    print("🚀 Starting Tra(i)der Phase I v2.1 Development Servers\n")

    # Check if virtual environment is activated
    venv_path = PROJECT_ROOT / "venv"
    if not os.environ.get("VIRTUAL_ENV"):
        print("⚠️  Warning: Virtual environment not activated")
        print(f"   Run: source {venv_path}/bin/activate\n")

    # Start FastAPI backend
    print("📡 Starting FastAPI backend on http://localhost:8080")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--reload", "--port", "8080"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    processes.append(backend_proc)

    # Wait for backend to start
    time.sleep(2)

    # Start Vite frontend
    print("🎨 Starting Vite frontend on http://localhost:3000")
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=PROJECT_ROOT / "frontend",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    processes.append(frontend_proc)

    print("\n✅ Servers started!")
    print("   Frontend: http://localhost:3000")
    print("   Backend:  http://localhost:8080")
    print("   API Docs: http://localhost:8080/docs")
    print("\n   Press Ctrl+C to stop all servers\n")

    # Stream output from both processes
    try:
        while True:
            # Check if processes are still running
            if backend_proc.poll() is not None:
                print("❌ Backend crashed!")
                break
            if frontend_proc.poll() is not None:
                print("❌ Frontend crashed!")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()

if __name__ == "__main__":
    main()
