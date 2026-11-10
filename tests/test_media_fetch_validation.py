"""Fetch validation contract: real local media/processes, no live platform calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/validate_media_fetch.py'
BILI = 'https://www.bilibili.com/video/BV1bK411W797?p=2'


@pytest.fixture
def fetch():
    assert SCRIPT.is_file(), 'The standalone validation CLI is not implemented'
    spec = importlib.util.spec_from_file_location('media_fetch_validation', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def batch_clock(fetch, monkeypatch):
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    clock = Clock()
    # Replace this module's clock, not the shared time module used by pytest/processes.
    monkeypatch.setattr(fetch, 'time', clock)
    return clock


def wav(path, seconds=1):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\x00\x00' * int(8000 * seconds))
    return path


def test_share_text_is_normalized_and_never_copied(fetch):
    entries = fetch.prepare_samples(['口令 secret 分享 ' + BILI + '&token=secret。'])
    assert entries == [{'index': 1, 'source': BILI, 'input_error': None}]
    assert 'secret' not in json.dumps(entries)


@pytest.mark.parametrize('source', ['', 'https://user:secret@www.bilibili.com/video/BV1bK411W797',
                                     BILI + ' https://v.douyin.com/aU0BxZKBvVI/', 7, {'source': BILI, 'secret': 'hidden'}])
def test_invalid_input_is_counted_without_echoing(fetch, source):
    assert fetch.prepare_samples([source]) == [{'index': 1, 'source': None, 'input_error': 'invalid_input'}]


def test_oversized_manifest_rejects_whole_batch_without_truncation(fetch, tmp_path):
    samples = [BILI] * 6 + ['secret']
    report = fetch.run_batch(samples, tmp_path / 'phase1c-over', fetch.Limits(), 'cloud')
    assert report['summary'] == {'total': 7, 'attempted': 0, 'succeeded': 0, 'failed': 1, 'not_run': 6}
    assert len(report['samples']) == 7
    assert report['samples'][-1]['category'] == 'invalid_input'
    assert report['samples'][0]['category'] == 'sample_limit'
    assert report['environment']['cloud_execution_verified'] is False
    assert report['environment']['os'] in {'Windows', 'Linux', 'Darwin'}


@pytest.mark.parametrize('kwargs', [{'max_bytes': 64 * 1024**2 + 1}, {'max_duration': 1201},
    {'task_timeout': 301}, {'batch_timeout': 901}, {'max_duration': 0}, {'task_timeout': float('nan')}])
def test_limits_cannot_exceed_hard_caps_or_be_nonfinite(fetch, kwargs):
    with pytest.raises(ValueError):
        fetch.Limits(**kwargs)


def test_actual_audio_is_probed_and_html_is_not_media(fetch, tmp_path):
    path = wav(tmp_path / 'source.wav')
    result = fetch.probe_file(path, fetch.Limits())
    assert result == {'size_bytes': 16044, 'duration_seconds': 1.0, 'media_type': 'audio', 'has_audio': True, 'extension': 'wav'}
    html = tmp_path / 'source.html'
    html.write_text('<html>HTTP 200 OK</html>')
    with pytest.raises(Exception) as error:
        fetch.probe_file(html, fetch.Limits())
    assert fetch.classify_error(error.value) == 'invalid_media'


@pytest.mark.parametrize('limit,category', [({'max_bytes': 100}, 'size_limit'), ({'max_duration': 0.5}, 'duration_limit')])
def test_real_media_must_obey_limits(fetch, tmp_path, limit, category):
    path = wav(tmp_path / 'source.wav')
    with pytest.raises(Exception) as error:
        fetch.probe_file(path, fetch.Limits(**limit))
    assert fetch.classify_error(error.value) == category


@pytest.mark.parametrize('exc,category', [
    (RuntimeError('cookie secret https://cdn.example/file?token=private'), 'platform_restricted'),
    (TimeoutError('secret'), 'network_error'), (RuntimeError('404 secret'), 'unavailable'),
    (RuntimeError('secret'), 'download_error'), (ModuleNotFoundError('private'), 'dependency_missing')])
def test_error_categories_do_not_echo_exception(fetch, exc, category):
    assert fetch.classify_error(exc) == category


def test_missing_dependencies_count_every_valid_item(fetch, tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, 'missing_dependencies', lambda: ['av'])
    report = fetch.run_batch([BILI, 'secret', BILI], tmp_path / 'phase1c-missing', fetch.Limits(), 'local')
    assert report['summary'] == {'total': 3, 'attempted': 0, 'succeeded': 0, 'failed': 1, 'not_run': 2}
    assert report['samples'][0]['category'] == 'dependency_missing'
    assert 'secret' not in json.dumps(report)


def test_batch_deadline_counts_remaining_samples(fetch, tmp_path, monkeypatch, batch_clock):
    def run(source, folder, limits, timeout):
        assert timeout == pytest.approx(0.03)
        batch_clock.advance(0.05)
        return {'status': 'failed', 'category': 'task_timeout', 'media': None, 'resolved_source': None}
    monkeypatch.setattr(fetch, 'missing_dependencies', lambda: [])
    monkeypatch.setattr(fetch, 'run_sample', run)
    report = fetch.run_batch([BILI, BILI, BILI], tmp_path / 'phase1c-deadline',
                             fetch.Limits(batch_timeout=0.03), 'local')
    assert report['summary'] == {'total': 3, 'attempted': 1, 'succeeded': 0, 'failed': 1, 'not_run': 2}
    assert [row['attempted'] for row in report['samples']] == [True, False, False]
    assert [row['status'] for row in report['samples']] == ['failed', 'not_run', 'not_run']
    assert [row['category'] for row in report['samples']] == ['batch_timeout'] * 3
    assert [row['elapsed_seconds'] for row in report['samples']] == [0.05, 0.0, 0.0]


def test_batch_deadline_keeps_completed_sample(fetch, tmp_path, monkeypatch, batch_clock):
    def run(source, folder, limits, timeout):
        assert timeout == pytest.approx(0.03)
        batch_clock.advance(0.03)
        return {'status': 'success', 'category': 'ok', 'resolved_source': BILI,
                'media': {'size_bytes': 16044, 'duration_seconds': 1, 'media_type': 'audio',
                          'has_audio': True, 'extension': 'wav', 'file': 'media/source.wav'}}
    monkeypatch.setattr(fetch, 'missing_dependencies', lambda: [])
    monkeypatch.setattr(fetch, 'run_sample', run)
    report = fetch.run_batch([BILI, BILI, BILI], tmp_path / 'phase1c-completed',
                             fetch.Limits(batch_timeout=0.03), 'local')
    assert report['summary'] == {'total': 3, 'attempted': 1, 'succeeded': 1, 'failed': 0, 'not_run': 2}
    assert [row['attempted'] for row in report['samples']] == [True, False, False]
    assert [row['status'] for row in report['samples']] == ['success', 'not_run', 'not_run']
    assert [row['category'] for row in report['samples']] == ['ok', 'batch_timeout', 'batch_timeout']
    assert report['samples'][0]['media']['file'] == 'sample-001/media/source.wav'


@pytest.mark.parametrize('setup_seconds', [0.03, 0.05], ids=['at-deadline', 'past-deadline'])
def test_batch_deadline_before_first_sample(fetch, tmp_path, monkeypatch, batch_clock, setup_seconds):
    environment = fetch.environment

    def collect_environment(label):
        result = environment(label)
        batch_clock.advance(setup_seconds)
        return result

    def unexpected_run(*args):
        pytest.fail('No worker may start after the batch budget is exhausted')

    monkeypatch.setattr(fetch, 'environment', collect_environment)
    monkeypatch.setattr(fetch, 'missing_dependencies', lambda: [])
    monkeypatch.setattr(fetch, 'run_sample', unexpected_run)
    report = fetch.run_batch([BILI, BILI, BILI], tmp_path / 'phase1c-expired',
                             fetch.Limits(batch_timeout=0.03), 'local')
    assert report['summary'] == {'total': 3, 'attempted': 0, 'succeeded': 0, 'failed': 0, 'not_run': 3}
    assert [row['attempted'] for row in report['samples']] == [False] * 3
    assert [row['status'] for row in report['samples']] == ['not_run'] * 3
    assert [row['category'] for row in report['samples']] == ['batch_timeout'] * 3
    assert report['elapsed_seconds'] == setup_seconds


def test_timeout_kills_worker_tree(fetch, tmp_path):
    child_marker = tmp_path / 'child-lived'
    parent_marker = tmp_path / 'parent-lived'
    child = f"import time,pathlib;time.sleep(2);pathlib.Path({str(child_marker)!r}).write_text('bad')"
    code = f"import subprocess,sys,time,pathlib;subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(2);pathlib.Path({str(parent_marker)!r}).write_text('bad')"
    result = fetch.bounded_process([sys.executable, '-c', code], tmp_path, timeout=0.6,
                                   max_bytes=1024, media_dir=tmp_path / 'media')
    assert result == 'task_timeout'
    time.sleep(2)
    assert not child_marker.exists() and not parent_marker.exists()


def test_cli_invalid_manifest_returns_nonzero_safe_report(fetch, tmp_path):
    manifest = tmp_path / 'input.json'
    manifest.write_text(json.dumps([{'source': 'secret', 'token': 'never-log'}]))
    out = tmp_path / 'phase1c-cli'
    result = subprocess.run([sys.executable, str(SCRIPT), '--manifest', str(manifest), '--output-dir', str(out)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    report = json.loads((out / 'report.json').read_text())
    assert report['summary']['total'] == 1
    assert report['summary']['failed'] == 1
    assert 'secret' not in result.stdout + result.stderr + json.dumps(report)
    assert 'never-log' not in result.stdout + result.stderr + json.dumps(report)


def test_clean_worker_environment_drops_credentials_and_proxy(fetch, tmp_path, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'https://secret.invalid')
    monkeypatch.setenv('OPENAI_API_KEY', 'secret')
    env = fetch.worker_environment(tmp_path)
    assert 'HTTPS_PROXY' not in env and 'OPENAI_API_KEY' not in env
    assert env['HOME'] == str(tmp_path / 'home')


def test_clean_worker_can_start_installed_node_without_inheriting_extra_environment(fetch, tmp_path, monkeypatch):
    node = fetch.shutil.which('node')
    if node is None:
        pytest.skip('This integration check requires installed Node.js')
    unrelated = tmp_path / 'unrelated-runtime'
    unrelated.mkdir()
    monkeypatch.setenv('PATH', str(unrelated) + os.pathsep + os.environ.get('PATH', ''))
    for name in ('NODE_PATH', 'NODE_OPTIONS', 'PYTHONPATH', 'HTTPS_PROXY', 'OPENAI_API_KEY'):
        monkeypatch.setenv(name, 'must-not-reach-worker')
    env = fetch.worker_environment(tmp_path)
    code = """import json,os,shutil,subprocess
node=shutil.which('node')
print(json.dumps({'node':node,'version':subprocess.check_output([node,'--version'],text=True).strip() if node else None,
'leaks':[key for key in ('NODE_PATH','NODE_OPTIONS','PYTHONPATH','HTTPS_PROXY','OPENAI_API_KEY') if key in os.environ]}))
"""
    run = subprocess.run([sys.executable, '-I', '-c', code], env=env, cwd=tmp_path,
                         capture_output=True, text=True, timeout=10, check=True)
    actual = json.loads(run.stdout)
    assert actual['node'] is not None, 'sanitized worker lost the installed Node runtime'
    assert Path(actual['node']).resolve() == Path(node).resolve()
    assert actual['version'].startswith('v') and actual['leaks'] == []
    assert str(unrelated) not in env['PATH']


@pytest.mark.skipif(os.name != 'nt', reason='Windows system Chrome discovery')
def test_clean_worker_can_launch_system_chrome(fetch, tmp_path):
    node = fetch.shutil.which('node')
    installed = any((Path(os.environ[key]) / 'Google/Chrome/Application/chrome.exe').is_file()
                    for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)') if key in os.environ)
    if not node or not installed or not (ROOT / 'node_modules/playwright-core/package.json').is_file():
        pytest.skip('This integration check requires system Chrome and project browser dependencies')
    code = """(async()=>{
const browser=await require('playwright-core').chromium.launch({channel:'chrome',headless:true});
try { console.log(JSON.stringify({version:browser.version()})); }
finally { await browser.close(); }
})().catch(()=>{console.log('chrome_launch_failed');process.exitCode=1;});"""
    env = fetch.worker_environment(tmp_path)
    run = subprocess.run([node, '-e', code], env=env, cwd=ROOT,
                         capture_output=True, text=True, timeout=25)
    assert run.returncode == 0, run.stdout
    assert json.loads(run.stdout)['version']
    assert env['LOCALAPPDATA'] == str(tmp_path / 'home/AppData/Local')
    assert env['APPDATA'] == str(tmp_path / 'home/AppData/Roaming')


def test_worker_probes_actual_file_and_filters_platform_fields(fetch, tmp_path, monkeypatch):
    def download(url, folder, limit, duration):
        folder.mkdir()
        path = wav(folder / 'source.wav')
        return {'path': str(path), 'metadata': {'webpage_url': BILI + '&token=private',
                'title': 'secret title', 'url': 'https://cdn.invalid/?signature=secret'}}
    monkeypatch.setattr(fetch, 'download_in_worker', download)
    request, response = tmp_path / 'request.json', tmp_path / 'response.json'
    request.write_text(json.dumps({'source': BILI, 'limits': fetch.Limits().as_dict()}))
    assert fetch.worker(request, response) == 0
    raw = json.loads(response.read_text())
    assert raw['status'] == 'success' and raw['resolved_source'] == BILI
    assert raw['media']['size_bytes'] == 16044 and raw['media']['duration_seconds'] == 1
    assert all(word not in response.read_text() for word in ('private', 'secret', 'signature', 'title'))
    raw['private'] = 'secret'
    raw['media']['private'] = 'secret'
    response.write_text(json.dumps(raw))
    result = fetch.read_worker_response(response, tmp_path, fetch.Limits())
    assert 'secret' not in json.dumps(result)


def test_batch_success_failed_and_invalid_are_all_accounted(fetch, tmp_path, monkeypatch):
    count = 0
    def run(source, folder, limits, timeout):
        nonlocal count
        count += 1
        if count == 2:
            return fetch.failure('platform_restricted')
        return {'status': 'success', 'category': 'ok', 'resolved_source': BILI,
                'media': {'size_bytes': 16044, 'duration_seconds': 1, 'media_type': 'audio',
                          'has_audio': True, 'extension': 'wav', 'file': 'media/source.wav'}}
    monkeypatch.setattr(fetch, 'run_sample', run)
    report = fetch.run_batch([BILI, BILI, 'bad'], tmp_path / 'phase1c-counts', fetch.Limits(), 'local')
    assert report['summary'] == {'total': 3, 'attempted': 2, 'succeeded': 1, 'failed': 2, 'not_run': 0}
    assert report['samples'][0]['media']['file'] == 'sample-001/media/source.wav'


def test_size_monitor_stops_process_and_cleans_partial_download(fetch, tmp_path):
    media = tmp_path / 'media'
    media.mkdir()
    code = f"import pathlib,time;pathlib.Path({str(media / 'partial')!r}).write_bytes(b'x'*4096);time.sleep(10)"
    assert fetch.bounded_process([sys.executable, '-c', code], tmp_path, 3, 1024, media) == 'size_limit'


@pytest.mark.skipif(os.name != 'nt', reason='Windows open-file deletion semantics')
def test_timeout_waits_briefly_for_worker_file_handle_release(fetch, tmp_path, monkeypatch):
    import threading
    release = None
    def timed_out(command, folder, timeout, max_bytes, media_dir):
        nonlocal release
        media_dir.mkdir()
        handle = (media_dir / 'source.mp4.part').open('wb')
        handle.write(b'partial')
        handle.flush()
        release = threading.Timer(.2, handle.close)
        release.start()
        return 'task_timeout'
    monkeypatch.setattr(fetch, 'bounded_process', timed_out)
    folder = tmp_path / 'sample'
    try:
        result = fetch.run_sample(BILI, folder, fetch.Limits(), 1)
        assert result['category'] == 'task_timeout'
        assert not (folder / 'media').exists()
    finally:
        if release:
            release.join()


def test_persistent_cleanup_error_still_writes_a_failure_report(fetch, tmp_path, monkeypatch):
    def timed_out(command, folder, timeout, max_bytes, media_dir):
        media_dir.mkdir()
        (media_dir / 'source.mp4.part').write_bytes(b'partial')
        return 'task_timeout'
    def locked(path):
        raise PermissionError('private system detail')
    monkeypatch.setattr(fetch, 'bounded_process', timed_out)
    monkeypatch.setattr(fetch.shutil, 'rmtree', locked)
    output = tmp_path / 'phase1c-cleanup-failure'
    report = fetch.run_batch([BILI], output, fetch.Limits(), 'local')
    assert report['samples'][0]['category'] == 'cleanup_error'
    assert report['summary']['failed'] == 1
    assert (output / 'report.json').is_file()
    assert 'private system detail' not in json.dumps(report)


@pytest.mark.parametrize('content', ['{bad secret', '{}', '[]', '"secret"', ' ' * 65537])
def test_cli_bad_manifest_does_not_disguise_missing_inputs(fetch, tmp_path, content):
    manifest = tmp_path / 'input.json'
    manifest.write_text(content)
    output = tmp_path / 'phase1c-malformed'
    result = subprocess.run([sys.executable, str(SCRIPT), '--manifest', str(manifest), '--output-dir', str(output)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    report = json.loads((output / 'report.json').read_text())
    assert report['input_error'] == 'invalid_manifest'
    assert report['input_count_known'] is (content == '[]')
    assert report['summary']['total'] == 0 and report['summary']['attempted'] == 0
    assert 'secret' not in json.dumps(report) + result.stdout + result.stderr


def test_import_does_not_load_app_config_models_or_dotenv(fetch):
    code = f"import runpy,sys;runpy.run_path({str(SCRIPT)!r},run_name='validation_import');assert not set(sys.modules)&{{'app.config','dotenv','faster_whisper','app.adapters.asr','app.main'}}"
    subprocess.run([sys.executable, '-I', '-c', code], check=True, timeout=10)


def test_standalone_bundle_whitelist_and_reproducibility(tmp_path):
    import zipfile
    import hashlib
    builder = ROOT / 'deploy/media-fetch/build_bundle.py'
    bundles = []
    for number in (1, 2):
        output = tmp_path / f'phase1c-package-{number}'
        subprocess.run([sys.executable, str(builder), '--output-dir', str(output)], check=True,
                       capture_output=True, timeout=10)
        bundles.append(output / 'media-fetch-validation.zip')
    assert bundles[0].read_bytes() == bundles[1].read_bytes()
    with zipfile.ZipFile(bundles[0]) as archive:
        names = archive.namelist()
        assert len(names) == 19
        assert 'app/adapters/download_browser.py' in names
        assert 'app/adapters/douyin_browser.cjs' in names
        assert 'package-lock.json' in names
        assert all(not any(part in name.split('/') for part in ('data', '.env', '.runtime', 'output', '.venv')) for name in names)
        manifest = json.loads(archive.read('bundle-manifest.json'))
        for name, digest in manifest['sha256'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        extracted = tmp_path / 'extracted'
        archive.extractall(extracted)
    # The relocated package must import/run without the rest of the product.
    help_run = subprocess.run([sys.executable, '-I', str(extracted / 'scripts/validate_media_fetch.py'), '--help'],
                              cwd=extracted, capture_output=True, timeout=10)
    assert help_run.returncode == 0, help_run.stderr.decode(errors='replace')
    run = subprocess.run([sys.executable, '-I', str(extracted / 'scripts/validate_media_fetch.py'),
                          'invalid', '--output-dir', str(tmp_path / 'phase1c-extracted')],
                         cwd=extracted, capture_output=True, timeout=10)
    assert run.returncode == 1


def test_report_distinguishes_known_count_from_unreadable_manifest(fetch, tmp_path):
    report = fetch.run_batch(['invalid'], tmp_path / 'phase1c-known', fetch.Limits(), 'local')
    assert report['input_count_known'] is True
