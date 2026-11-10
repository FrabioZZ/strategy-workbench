"""Validate the distribution in a new directory; uses only bundled executables."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import wave


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = args.directory.resolve(strict=True)
    python = root / 'runtime/python/python.exe'
    pythonw = root / 'runtime/python/pythonw.exe'
    flags = subprocess.CREATE_NO_WINDOW
    result = {'directory': str(root)}
    subprocess.run([str(python), '-I', '-c',
                    'import fastapi,uvicorn,pydantic,av,faster_whisper,backtrader,yt_dlp; print("dependencies_ok")'],
                   cwd=root, check=True, creationflags=flags)
    process = subprocess.Popen([str(pythonw), str(root / 'scripts/portable_launch.py'), '--no-browser'],
                               cwd=root, creationflags=flags)
    try:
        for _ in range(240):
            if process.poll() is not None:
                raise RuntimeError('Portable launcher exited early: ' + str(process.returncode))
            state_path = root / 'user-data/instance.json'
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding='utf-8'))
                if state['pid'] == process.pid:
                    try:
                        with urllib.request.urlopen(state['url'] + '/api/status', timeout=2) as response:
                            status = json.load(response)
                            break
                    except OSError:
                        pass
            time.sleep(.25)
        else:
            raise RuntimeError('Portable API did not become ready')
        result['status'] = status
        assert status['asr_configured'] and not status['ai_configured']
        def get(path):
            with urllib.request.urlopen(state['url'] + path, timeout=15) as response:
                return json.load(response)
        datasets = get('/api/trading/datasets')
        result['history'] = [{'symbols': len(d['symbols']), 'rows': d['row_count'], 'start': d['start_date'], 'end': d['end_date']} for d in datasets]
        assert any(d['symbols'] == 300 and d['rows'] == 203572 for d in result['history'])
        result['indicators'] = len(get('/api/trading/indicators')['indicators'])
        assert result['indicators'] >= 30
        assert get('/api/documents') == []
        # Test media probing in the same packaged worker used for uploaded files.
        media = root / 'user-data/media/portable-probe.wav'
        media.parent.mkdir(exist_ok=True)
        with wave.open(str(media), 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 16000)
        request = root / 'user-data/probe-request.json'
        output = root / 'user-data/probe-result.json'
        request.write_text(json.dumps({'operation': 'probe', 'path': str(media), 'data_dir': str(root / 'user-data'),
                                       'limit': 200 * 1024 * 1024, 'duration': 7200}), encoding='utf-8')
        subprocess.run([str(pythonw), '-m', 'app.media_worker', str(request), str(output)], cwd=root, check=True, timeout=30, creationflags=flags)
        result['media_worker'] = json.loads(output.read_text(encoding='utf-8'))
        assert result['media_worker']['ok']
        subprocess.run([str(python), '-I', '-c',
            "from faster_whisper import WhisperModel; WhisperModel('resources/models/faster-whisper-small', device='cpu', compute_type='int8', local_files_only=True); print('model_loaded')"],
            cwd=root, check=True, timeout=60, creationflags=flags)
        result['asr_model_loaded'] = True
        node_script = "const {chromium}=require('playwright-core'); (async()=>{let b=await chromium.launch({executablePath:process.cwd()+'/runtime/browser/chrome-headless-shell.exe',headless:true}); console.log(b.version()); await b.close();})().catch(e=>{console.error(e);process.exit(1)});"
        browser = subprocess.run([str(root / 'runtime/node/node.exe'), '-e', node_script], cwd=root, check=True,
                                 timeout=30, capture_output=True, text=True, creationflags=flags)
        result['browser_version'] = browser.stdout.strip()
        result['passed'] = True
    finally:
        subprocess.run([str(root / 'StopWorkbench.exe')], cwd=root, timeout=20, creationflags=flags)
        try:
            process.wait(timeout=10)
            result['stop_exe_terminated_server'] = True
        except subprocess.TimeoutExpired:
            process.terminate()
            result['stop_exe_terminated_server'] = False
    report = root.parent / 'portable-verification.json'
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert result.get('passed') and result.get('stop_exe_terminated_server'), result
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
