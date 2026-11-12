"""Start the offline daily walkthrough with a fresh local data directory."""
import argparse
from pathlib import Path
import socket
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766, help='localhost port, or 0 for a free port')
    parser.add_argument('--history-data-dir', type=Path, default=ROOT / 'data',
                        help='read-only source for the imported HS300 dataset and its original history bundle')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')

    import uvicorn
    from app.demo import create_demo_app

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('127.0.0.1', args.port))
            sock.listen(128)
        except OSError as exc:
            parser.exit(1, f'Cannot listen on 127.0.0.1:{args.port}: {exc}\n')
        port = sock.getsockname()[1]
        runtime = ROOT / '.runtime'
        runtime.mkdir(exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='phase11-demo-', dir=runtime))
        print(f'Phase 11 sample walkthrough: http://127.0.0.1:{port}/', flush=True)
        print(f'Isolated sample ledger: {folder}', flush=True)
        app = create_demo_app(folder, port, history_data_dir=args.history_data_dir)
        uvicorn.Server(uvicorn.Config(app)).run(sockets=[sock])


if __name__ == '__main__':
    main()
