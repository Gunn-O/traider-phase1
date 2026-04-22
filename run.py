"""
Startup Script — Run XAUUSD Bot + Dashboard

Usage:
    python run.py

What it does:
1. Start FastAPI API server (dashboard + WebSocket)
2. Auto-open browser at http://127.0.0.1:8080
3. Keep running until Ctrl+C

Note: Bot control is done via dashboard (START button)
      This script only runs the API server.
"""

import sys
import time
import threading
import webbrowser
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def start_api_server():
    """Start FastAPI server in separate thread"""
    import uvicorn
    from api_server import app

    logger.info("🚀 Starting API server...")

    uvicorn.run(
        app,
        host="127.0.0.1",  # localhost only — DO NOT change to 0.0.0.0
        port=8080,
        log_level="warning",  # Reduce uvicorn noise
        access_log=False      # Disable access log
    )


def open_browser_delayed():
    """Open browser after short delay (wait for server to start)"""
    time.sleep(2.0)  # Wait 2 seconds for server to be ready

    url = "http://127.0.0.1:8080"
    logger.info(f"🌐 Opening browser: {url}")

    try:
        webbrowser.open(url)
    except Exception as e:
        logger.warning(f"Failed to open browser automatically: {e}")
        logger.info(f"Please open manually: {url}")


def print_banner():
    """Print startup banner"""
    print("=" * 70)
    print("🤖 XAUUSD TRADING BOT DASHBOARD")
    print("=" * 70)
    print("📊 Dashboard:    http://127.0.0.1:8080")
    print("📡 API Docs:     http://127.0.0.1:8080/docs")
    print("🔌 WebSocket:    ws://127.0.0.1:8080/ws")
    print("=" * 70)
    print("\n⚡ Server starting...")
    print("   Press Ctrl+C to stop\n")


def main():
    """Main entry point"""
    print_banner()

    # Start API server in main thread (blocking)
    # This ensures proper shutdown on Ctrl+C
    try:
        # Open browser in background thread
        browser_thread = threading.Thread(target=open_browser_delayed, daemon=True)
        browser_thread.start()

        # Start API server (blocking)
        start_api_server()

    except KeyboardInterrupt:
        logger.info("\n\n🛑 Shutting down gracefully...")
        logger.info("Goodbye! 👋")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
