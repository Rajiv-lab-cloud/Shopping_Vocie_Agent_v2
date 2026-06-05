"""
run.py — One-click startup for the Voice Shopping Agent.

What this does automatically:
  1. Checks Python version
  2. Installs missing dependencies from requirements.txt
  3. Validates .env / GROQ_API_KEY
  4. Initialises the Postgres database + seeds 50 products
  5. Starts the FastAPI server via uvicorn
  6. Opens the demo in your browser

Usage:
    python run.py
    python run.py --port 8080
    python run.py --no-browser
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Force UTF-8 output on Windows so box-drawing and emoji render correctly
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Colour helpers (works on Windows 10+ and all POSIX terminals)
os.system("")  # enable ANSI on Windows


def c(text, code):
    return f"\033[{code}m{text}\033[0m"


def green(t):
    return c(t, "92")


def yellow(t):
    return c(t, "93")


def red(t):
    return c(t, "91")


def cyan(t):
    return c(t, "96")


def bold(t):
    return c(t, "1")


def dim(t):
    return c(t, "2")


BANNER = f"""
{cyan("+--------------------------------------------------+")}
{cyan("|")}   {bold("ShopBot  --  Voice AI Shopping Assistant")}      {cyan("|")}
{cyan("|")}   {dim("Powered by Groq  |  PostgreSQL  |  FastAPI")}      {cyan("|")}
{cyan("+--------------------------------------------------+")}
"""

ROOT = Path(__file__).parent


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════


def step(msg: str):
    print(f"\n{cyan('▶')} {bold(msg)}")


def ok(msg: str):
    print(f"  {green('✔')} {msg}")


def warn(msg: str):
    print(f"  {yellow('⚠')} {msg}")


def fail(msg: str):
    print(f"\n  {red('✖')} {msg}")
    sys.exit(1)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# CHECKS
# ══════════════════════════════════════════════════════════════════════════════


def check_python():
    step("Checking Python version")
    major, minor = sys.version_info[:2]
    if major < 3 or minor < 10:
        fail(f"Python 3.10+ required. You have {major}.{minor}.")
    ok(f"Python {major}.{minor} ✓")


def install_dependencies():
    step("Checking / installing dependencies")
    req = ROOT / "requirements.txt"
    if not req.exists():
        fail("requirements.txt not found.")

    try:
        import fastapi, groq, psycopg, sentence_transformers, pgvector  # noqa

        ok("All core dependencies already installed.")
        return
    except ImportError:
        pass

    warn("Some dependencies missing — running pip install…")
    result = run(
        [sys.executable, "-m", "pip", "install", "-r", str(req), "-q"],
        capture_output=False,
    )
    if result.returncode != 0:
        fail("pip install failed. Check the error above and re-run.")
    ok("Dependencies installed.")


def build_frontend():
    step("Building frontend")
    frontend_dir = ROOT / "frontend"
    if (frontend_dir / "package.json").exists():
        warn("Building latest frontend changes (npm install && npm run build)…")
        cmd = "npm install && npm run build" if sys.platform != "win32" else 'cmd.exe /c "npm install && npm run build"'
        result = run(
            cmd,
            cwd=str(frontend_dir),
            shell=True,
            capture_output=False,
        )
        if result.returncode != 0:
            fail("Frontend build failed. Please ensure Node.js is installed.")
        ok("Frontend built successfully.")


def check_env():
    step("Checking environment configuration")
    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"

    # Auto-copy .env.example → .env if .env doesn't exist
    if not env_file.exists():
        if env_example.exists():
            shutil.copy(env_example, env_file)
            warn(".env not found — created from .env.example")
            warn(f"  → Open {env_file} and set GROQ_API_KEY before continuing.")
        else:
            fail(".env file not found and no .env.example to copy from.")

    # Load .env
    from dotenv import load_dotenv

    load_dotenv(env_file)

    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key == "your_groq_api_key_here":
        print()
        print(red("  ╔════════════════════════════════════════════════╗"))
        print(red("  ║  GROQ_API_KEY is missing or not set!           ║"))
        print(red("  ║                                                ║"))
        print(red("  ║  1. Get a free key at https://console.groq.com ║"))
        print(red("  ║  2. Open .env and set:                         ║"))
        print(red("  ║     GROQ_API_KEY=gsk_your_key_here             ║"))
        print(red("  ║  3. Re-run:  python run.py                     ║"))
        print(red("  ╚════════════════════════════════════════════════╝"))
        print()
        sys.exit(1)

    ok(f"GROQ_API_KEY configured (…{key[-6:]})")


def init_database():
    step("Initialising database")
    sys.path.insert(0, str(ROOT))

    from db.database import get_db, init_db

    try:
        init_db()
    except Exception as e:
        fail(f"Could not connect to the database. Is Docker running?\n     Make sure to start Docker Desktop and run 'docker-compose up -d'.\n     Details: {e}")

    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) FROM products").fetchone()
        count = row["count"] if isinstance(row, dict) else row[0]

    if count == 0:
        warn("No products found — seeding catalog…")
        from db.seed import seed

        seed()
        with get_db() as conn:
            row = conn.execute("SELECT COUNT(*) FROM products").fetchone()
            count = row["count"] if isinstance(row, dict) else row[0]
        ok(f"Seeded {count} products into database.")
    else:
        ok(f"Database ready — {count} products loaded.")


def check_port(port: int) -> bool:
    """Return True if the port is free."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


# ══════════════════════════════════════════════════════════════════════════════
# LAUNCH SERVER
# ══════════════════════════════════════════════════════════════════════════════


def launch_server(port: int, open_browser: bool, reload: bool):
    step(f"Starting ShopBot API server on port {port}")

    original_port = port
    while not check_port(port):
        warn(f"Port {port} is already in use — trying next port...")
        port += 1
        if port > original_port + 10:
            warn(
                f"Could not find an open port. Please kill the process running on {original_port}."
            )
            return

    url = f"http://localhost:{port}/"
    docs_url = f"http://localhost:{port}/docs"
    health_url = f"http://localhost:{port}/health"

    print(f"""
  {green("━" * 50)}
  {bold("🚀 ShopBot is starting!")}

  {cyan("App UI    →")} {bold(url)}
  {cyan("API Docs  →")} {bold(docs_url)}
  {cyan("Health    →")} {bold(health_url)}

  {dim("Press Ctrl+C to stop")}
  {green("━" * 50)}
""")

    # Open browser after a short delay
    if open_browser:
        import threading

        def _open():
            time.sleep(2.5)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    # Launch uvicorn
    import uvicorn

    # Change into the ROOT directory so uvicorn can find "api.main"
    os.chdir(str(ROOT))

    try:
        uvicorn.run(
            "api.main:app",
            host="0.0.0.0",
            port=port,
            log_level="info",
            reload=reload,
        )
    except KeyboardInterrupt:
        print(f"\n\n  {yellow('Shutting down ShopBot. Goodbye! 👋')}\n")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the Voice Shopping Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                    Start on default port 8000
  python run.py --port 8080        Start on port 8080
  python run.py --no-browser       Don't auto-open the browser
  python run.py --no-reload        Disable auto-reload (production mode)
        """,
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Server port (default: 8000)"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Skip auto-opening the browser"
    )
    parser.add_argument(
        "--no-reload", action="store_true", help="Disable uvicorn auto-reload"
    )
    return parser.parse_args()


def main():
    print(BANNER)
    args = parse_args()

    try:
        check_python()
        install_dependencies()
        build_frontend()
        check_env()
        init_database()
        print(f"\n  {green('✔')} {bold('All checks passed! Launching server…')}")
        launch_server(
            port=args.port,
            open_browser=not args.no_browser,
            reload=not args.no_reload,
        )
    except KeyboardInterrupt:
        print(f"\n\n  {yellow('Cancelled. Goodbye! 👋')}\n")
    except SystemExit:
        raise
    except Exception as exc:
        fail(f"Unexpected error: {exc}")


if __name__ == "__main__":
    main()
