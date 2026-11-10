"""Self-contained Windows portable launcher. No user path configuration needed."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def configure():
    os.chdir(ROOT)
    data = ROOT / 'user-data'
    data.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = (data / 'server.log').open('a', encoding='utf-8', buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    os.environ['DATA_DIR'] = str(data)
    os.environ['ASR_MODEL_PATH'] = str(ROOT / 'resources/models/faster-whisper-small')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['PATH'] = str(ROOT / 'runtime/node') + os.pathsep + os.environ.get('PATH', '')
    browser = ROOT / 'runtime/browser/chrome-headless-shell.exe'
    if browser.exists():
        os.environ['QUANT_BROWSER_PATH'] = str(browser)
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    data = configure()
    # One portable instance per extracted folder. The lock is released by Windows
    # even after a crash, unlike a stale PID marker.
    import msvcrt
    with (data / 'portable.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'1')
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            state = json.loads((data / 'instance.json').read_text(encoding='utf-8'))
            if not args.no_browser:
                webbrowser.open(state['url'])
            return
        from app.config import Settings
        from app.trading.history import import_bundle
        history = ROOT / 'resources/history/hs300-20240101-20261101'
        initialized = data / 'bundled-history-v1.json'
        if history.is_dir() and not initialized.exists():
            result = import_bundle(history, data)
            initialized.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding='utf-8')
        from app.main import create_app
        import uvicorn
        # Hold the listening socket while constructing the server: no port race.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', args.port))
        sock.listen(128)
        url = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        (data / 'instance.json').write_text(json.dumps({'pid': os.getpid(), 'url': url}), encoding='utf-8')
        if not args.no_browser:
            def open_when_ready():
                for _ in range(120):
                    try:
                        with urllib.request.urlopen(url + '/api/status', timeout=1) as response:
                            if response.status == 200:
                                webbrowser.open(url)
                                return
                    except OSError:
                        time.sleep(.25)
            threading.Thread(target=open_when_ready, daemon=True).start()
        server = uvicorn.Server(uvicorn.Config(create_app(Settings.from_env()), log_level='warning'))
        server.run(sockets=[sock])


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        log = ROOT / 'startup-error.log'
        log.write_text(traceback.format_exc(), encoding='utf-8')
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, '启动失败，请查看软件目录 startup-error.log。', '策略拾录', 16)
        raise
