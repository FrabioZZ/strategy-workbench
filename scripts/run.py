"""Single-instance localhost launcher on Windows and Linux."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    config = Settings.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with (config.data_dir / "server.lock").open("a+b") as lock:
        lock.seek(0)
        lock.write(b"1")
        lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit("This data directory is already used by another server. Stop it first.")
        import uvicorn
        from app.main import create_app
        print(f"Open http://127.0.0.1:{args.port}")
        uvicorn.run(create_app(config), host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
