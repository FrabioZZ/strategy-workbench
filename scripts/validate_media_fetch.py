"""Bounded standalone media fetch experiment. No app config, models or HTTP server."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.adapters.download import (MediaDownloadError, download_in_worker,
                                   extract_shared_url, inspect_media, safe_download_error)

DEFAULT_SAMPLES = ['https://v.douyin.com/aU0BxZKBvVI/',
                   'https://www.bilibili.com/video/BV1bK411W797?p=2']
MAX_SAMPLES = 5
MAX_MANIFEST_BYTES = 65536
LABELS = ('local', 'linux-vm', 'container', 'cloud', 'ci')
CATEGORIES = {'ok', 'invalid_input', 'sample_limit', 'dependency_missing', 'batch_timeout',
              'task_timeout', 'size_limit', 'duration_limit', 'platform_restricted',
              'network_error', 'unavailable', 'invalid_media', 'unsupported_media',
              'download_error', 'worker_error', 'cleanup_error', 'interrupted'}


class Limits:
    def __init__(self, max_bytes=32 * 1024**2, max_duration=600, task_timeout=120, batch_timeout=600):
        values = {'max_bytes': (max_bytes, 64 * 1024**2), 'max_duration': (max_duration, 1200),
                  'task_timeout': (task_timeout, 300), 'batch_timeout': (batch_timeout, 900)}
        for key, (value, cap) in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= cap:
                raise ValueError('invalid_limits')
            setattr(self, key, value)
        if not isinstance(max_bytes, int):
            raise ValueError('invalid_limits')

    def as_dict(self):
        return {key: getattr(self, key) for key in ('max_bytes', 'max_duration', 'task_timeout', 'batch_timeout')}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def prepare_samples(raw):
    result = []
    for index, value in enumerate(raw, 1):
        if isinstance(value, dict) and set(value) == {'source'}:
            value = value['source']
        try:
            if not isinstance(value, str) or len(value) > 8192:
                raise ValueError()
            source = extract_shared_url(value)
            error = None
        except (ValueError, TypeError):
            source, error = None, 'invalid_input'
        result.append({'index': index, 'source': source, 'input_error': error})
    return result


def missing_dependencies():
    return [name for name in ('yt_dlp', 'av') if importlib.util.find_spec(name) is None]


def environment(label):
    versions = {}
    for name in ('yt-dlp', 'av'):
        try:
            version = importlib.metadata.version(name)
            versions[name] = version if re.fullmatch(r'[a-zA-Z0-9.+_-]{1,64}', version) else 'unknown'
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {'label': label, 'os': platform.system(), 'python': platform.python_version(),
            'dependencies': versions, 'cloud_execution_verified': False}


def classify_error(exc):
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return 'dependency_missing'
    detail = str(exc)
    for fragment, category in [('大小限制', 'size_limit'), ('超过大小', 'size_limit'),
                               ('时长超过', 'duration_limit'), ('媒体没有', 'invalid_media'),
                               ('媒体解析', 'invalid_media'), ('无法确定媒体', 'invalid_media'),
                               ('不支持直播', 'unsupported_media'), ('不支持合集', 'unsupported_media')]:
        if fragment in detail:
            return category
    safe = safe_download_error(exc)
    if '平台限制' in safe:
        return 'platform_restricted'
    if '网络' in safe:
        return 'network_error'
    if '视频不可用' in safe:
        return 'unavailable'
    return 'download_error'


def probe_file(path, limits):
    size = path.stat().st_size
    if size > limits.max_bytes:
        raise MediaDownloadError('媒体文件超过大小限制')
    if size <= 0:
        raise MediaDownloadError('媒体解析失败')
    actual = inspect_media(path, limits.max_duration)
    extension = path.suffix.lstrip('.').lower()
    return {'size_bytes': size, 'duration_seconds': actual['duration_seconds'],
            'media_type': actual['media_type'], 'has_audio': actual['has_audio'],
            'extension': extension if re.fullmatch(r'[a-z0-9]{1,10}', extension) else 'unknown'}


def worker_environment(folder):
    # No inherited credentials, proxies, Python injection, netrc or user-home config.
    # System installation roots let Playwright discover Chrome without restoring user config.
    env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'LANG', 'LC_ALL',
                                          'PROGRAMFILES', 'PROGRAMFILES(X86)') if key in os.environ}
    home, temp = folder / 'home', folder / 'tmp'
    home.mkdir(exist_ok=True)
    temp.mkdir(exist_ok=True)
    roaming, local = home, home
    if os.name == 'nt':
        # Windows known-folder lookup needs these directories in the isolated profile.
        roaming, local = home / 'AppData/Roaming', home / 'AppData/Local'
        roaming.mkdir(parents=True, exist_ok=True)
        local.mkdir(parents=True, exist_ok=True)
    env.update({'HOME': str(home), 'USERPROFILE': str(home), 'APPDATA': str(roaming),
                'LOCALAPPDATA': str(local), 'XDG_CONFIG_HOME': str(home),
                'XDG_CACHE_HOME': str(home), 'TMP': str(temp), 'TEMP': str(temp), 'TMPDIR': str(temp)})
    runtime_paths = [str(Path(sys.executable).parent)]
    node = shutil.which('node')
    if node:
        # Keep only the discovered runtime directory, never the parent's whole PATH.
        runtime_paths.append(str(Path(node).absolute().parent))
    env['PATH'] = os.pathsep.join(dict.fromkeys(runtime_paths))
    return env


class WindowsJob:
    """Kill-on-close job; children cannot escape or run before assignment."""
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64), ('flags', w.DWORD),
                        ('min_ws', c.c_size_t), ('max_ws', c.c_size_t), ('active', w.DWORD),
                        ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', c.c_uint64 * 6), ('process_memory', c.c_size_t),
                        ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
        self.api = c.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.api.SetInformationJobObject(self.handle, 9, c.byref(info), c.sizeof(info)):
            self.close()
            raise OSError('worker_isolation_unavailable')

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise OSError('worker_isolation_unavailable')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def stop_process(process, job=None):
    if job:
        job.close()
    if os.name != 'nt':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def directory_bytes(folder):
    try:
        return sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
    except FileNotFoundError:
        return 0


def bounded_process(command, folder, timeout, max_bytes, media_dir):
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    started = time.monotonic()
    job, process, gate = None, None, folder / 'worker-ready'
    try:
        if os.name == 'nt':
            job = WindowsJob()
            command = [sys.executable, '-I', str(ROOT / 'scripts/media_fetch_launcher.py'), str(gate), *command]
        process = subprocess.Popen(command, cwd=folder, env=worker_environment(folder),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, shell=False, **flags)
        if job:
            job.assign(process)
            gate.touch()
        while process.poll() is None:
            if time.monotonic() - started >= timeout:
                return 'task_timeout'
            if directory_bytes(media_dir) > max_bytes:
                return 'size_limit'
            time.sleep(min(0.05, max(0.001, timeout - (time.monotonic() - started))))
        if directory_bytes(media_dir) > max_bytes:
            return 'size_limit'
        return None if process.returncode == 0 else 'worker_error'
    finally:
        if process:
            stop_process(process, job)
        elif job:
            job.close()
        gate.unlink(missing_ok=True)


def failure(category):
    return {'status': 'failed', 'category': category, 'media': None, 'resolved_source': None}


def worker(request_file, response_file):
    # Both files are generated by the parent, not arbitrary manifest fields.
    try:
        request = json.loads(Path(request_file).read_text(encoding='utf-8'))
        limits = Limits(**request['limits'])
        folder = Path(request_file).resolve().parent / 'media'
        result = download_in_worker(request['source'], folder, limits.max_bytes, limits.max_duration)
        path = Path(result['path']).resolve(strict=True)
        if path.parent != folder.resolve() or not path.is_file():
            raise MediaDownloadError('媒体解析失败')
        media = probe_file(path, limits)
        media['file'] = 'media/' + path.name
        response = {'status': 'success', 'category': 'ok', 'media': media,
                    'resolved_source': extract_shared_url(result['metadata']['webpage_url'])}
    except Exception as exc:
        response = failure(classify_error(exc))
    Path(response_file).write_text(json.dumps(response, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return 0


def read_worker_response(path, folder, limits):
    if path.stat().st_size > 8192:
        return failure('worker_error')
    raw = json.loads(path.read_text(encoding='utf-8'))
    if raw.get('status') != 'success':
        category = raw.get('category')
        return failure(category if category in CATEGORIES - {'ok'} else 'worker_error')
    media = raw['media']
    size, duration = media['size_bytes'], media['duration_seconds']
    if type(size) is not int or not 0 < size <= limits.max_bytes:
        return failure('size_limit')
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= limits.max_duration:
        return failure('duration_limit')
    extension = media['extension']
    if not isinstance(extension, str) or not re.fullmatch('[a-z0-9]{1,10}', extension):
        return failure('worker_error')
    filename = media['file']
    if filename != 'media/source.' + extension:
        return failure('worker_error')
    file = folder / filename
    if not file.is_file() or file.resolve().parent != (folder / 'media').resolve() or file.stat().st_size != size:
        return failure('invalid_media')
    if media['media_type'] not in ('audio', 'video') or media['has_audio'] is not True:
        return failure('invalid_media')
    # Whitelist all fields crossing the worker boundary; never forward title or CDN URL.
    return {'status': 'success', 'category': 'ok', 'resolved_source': extract_shared_url(raw['resolved_source']),
            'media': {'size_bytes': size, 'duration_seconds': duration, 'media_type': media['media_type'],
                      'has_audio': True, 'extension': extension, 'file': filename}}


def cleanup_failed_media(folder):
    # Windows job termination and file-handle release are not simultaneous.
    deadline = time.monotonic() + 2
    while True:
        try:
            shutil.rmtree(folder)
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(.05, remaining))
        except OSError:
            return False


def run_sample(source, folder, limits, timeout):
    folder.mkdir()
    request, response = folder / 'request.json', folder / 'response.json'
    request.write_text(json.dumps({'source': source, 'limits': limits.as_dict()}), encoding='utf-8')
    result = failure('worker_error')
    try:
        category = bounded_process([sys.executable, '-I', str(Path(__file__).resolve()), '--worker', str(request), str(response)],
                                   folder, timeout, limits.max_bytes, folder / 'media')
        result = failure(category) if category else read_worker_response(response, folder, limits)
    except KeyboardInterrupt:
        result = failure('interrupted')
    except Exception:
        result = failure('worker_error')
    finally:
        request.unlink(missing_ok=True)
        response.unlink(missing_ok=True)
        media_folder = (folder / 'media').resolve()
        if result['status'] != 'success' and media_folder.exists():
            if media_folder.parent != folder.resolve():
                raise ValueError('unsafe_output_path')
            if not cleanup_failed_media(media_folder):
                result = failure('cleanup_error')
    return result


def run_batch(raw, output, limits, label, input_count_known=True):
    if label not in LABELS:
        raise ValueError('invalid_label')
    output = Path(output).resolve()
    if not output.name.startswith('phase1c-'):
        raise ValueError('invalid_output_path')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'schema_version': 1, 'started_at_utc': utc_now(), 'finished_at_utc': None,
              'environment': environment(label), 'limits': {**limits.as_dict(), 'max_samples': MAX_SAMPLES, 'concurrency': 1},
              'input_error': None, 'input_count_known': input_count_known, 'samples': [], 'summary': {}}
    samples = prepare_samples(raw)
    missing = missing_dependencies()
    interrupted = False
    for sample in samples:
        began = time.monotonic()
        remaining = limits.batch_timeout - (began - started)
        row = {'index': sample['index'], 'source': sample['source'], 'attempted': False, 'elapsed_seconds': 0.0}
        if sample['input_error']:
            result = failure('invalid_input')
        else:
            skip = ('sample_limit' if len(samples) > MAX_SAMPLES else 'dependency_missing' if missing else
                    'interrupted' if interrupted else 'batch_timeout' if remaining <= 0 else None)
            if skip:
                result = {**failure(skip), 'status': 'not_run'}
            else:
                row['attempted'] = True
                result = run_sample(sample['source'], output / f'sample-{sample["index"]:03d}', limits,
                                    min(limits.task_timeout, remaining))
                if result['category'] == 'task_timeout' and remaining < limits.task_timeout:
                    result['category'] = 'batch_timeout'
                interrupted = result['category'] == 'interrupted'
                if result['media']:
                    result['media']['file'] = f'sample-{sample["index"]:03d}/' + result['media']['file']
        row.update(result)
        row['elapsed_seconds'] = round(time.monotonic() - began, 3)
        report['samples'].append(row)
    if not samples:
        report['input_error'] = 'invalid_manifest'
    report['summary'] = {'total': len(samples), 'attempted': sum(x['attempted'] for x in report['samples']),
                         'succeeded': sum(x['status'] == 'success' for x in report['samples']),
                         'failed': sum(x['status'] == 'failed' for x in report['samples']),
                         'not_run': sum(x['status'] == 'not_run' for x in report['samples'])}
    report['finished_at_utc'] = utc_now()
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return report


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid_arguments')


def main(argv=None):
    if hasattr(signal, 'SIGTERM'):
        def terminate(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, terminate)
    parser = SafeParser(description='Serial media fetch validation; no credentials, models or app server.')
    parser.add_argument('source', nargs='?', help='One HTTPS video URL or complete share text')
    parser.add_argument('--manifest', type=Path, help='JSON array of strings or {"source": "..."}; at most 5')
    parser.add_argument('--output-dir', type=Path, help='NEW directory with name beginning phase1c-')
    parser.add_argument('--label', choices=LABELS, default='local', help='Operator label, never proof of cloud execution')
    parser.add_argument('--max-mib', type=int, default=32)
    parser.add_argument('--max-duration', type=float, default=600)
    parser.add_argument('--task-timeout', type=float, default=120)
    parser.add_argument('--batch-timeout', type=float, default=600)
    try:
        args = parser.parse_args(argv)
        limits = Limits(args.max_mib * 1024**2, args.max_duration, args.task_timeout, args.batch_timeout)
        if args.source is not None and args.manifest:
            raise ValueError('invalid_arguments')
        manifest_error = False
        if args.manifest:
            try:
                with args.manifest.open('rb') as stream:
                    content = stream.read(MAX_MANIFEST_BYTES + 1)
                if len(content) > MAX_MANIFEST_BYTES:
                    raise ValueError()
                raw = json.loads(content.decode('utf-8-sig'))
                if not isinstance(raw, list):
                    raise ValueError()
            except (OSError, ValueError, RecursionError):
                raw, manifest_error = [], True
        else:
            raw = [args.source] if args.source is not None else DEFAULT_SAMPLES
        output = args.output_dir or ROOT / '.runtime' / ('phase1c-fetch-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
        report = run_batch(raw, output, limits, args.label, input_count_known=not manifest_error)
        # stdout has only fixed fields/counts; output path is user-known and not echoed.
        print(json.dumps({'schema_version': 1, 'summary': report['summary'], 'input_error': report['input_error']}))
        return 2 if manifest_error or report['input_error'] else 0 if report['summary']['succeeded'] == report['summary']['total'] else 1
    except (ValueError, OSError):
        print(json.dumps({'schema_version': 1, 'error': 'invalid_arguments_or_output',
                          'hint': 'Use --help; output directory must be new and named phase1c-*.'}))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({'schema_version': 1, 'error': 'interrupted'}))
        return 130


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        sys.exit(worker(sys.argv[2], sys.argv[3]))
    sys.exit(main())
