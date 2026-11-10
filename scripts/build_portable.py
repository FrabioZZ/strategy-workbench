"""Build a relocatable Windows distribution from the tested local dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output' / 'StrategyWorkbench-0.6.0-windows-x64'
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.cache', '.git', 'user-data')


def copy(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=IGNORE)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true', help='Refresh app code only after checks')
    parser.add_argument('--zip', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.refresh:
        base = Path(sys.base_prefix)
        python = OUT / 'runtime/python'
        for name in ['python.exe', 'pythonw.exe', 'python3.dll', 'python312.dll',
                     'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt', 'DLLs']:
            if (base / name).exists():
                copy(base / name, python / name)
        shutil.copytree(base / 'Lib', python / 'Lib', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc', 'test', 'tests', 'idlelib', 'ensurepip'))
        copy(ROOT / '.venv/Lib/site-packages', python / 'Lib/site-packages')
        for name in ['msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'concrt140.dll', 'vcomp140.dll']:
            dll = Path('C:/Windows/System32') / name
            if dll.exists():
                copy(dll, python / name)
        copy(Path(shutil.which('node')), OUT / 'runtime/node/node.exe')
        copy(ROOT / 'node_modules', OUT / 'node_modules')
        browsers = list((ROOT / 'output/browser-runtime').rglob('chrome-headless-shell.exe'))
        if len(browsers) != 1:
            raise RuntimeError('Download bundled headless Chromium first; expected one executable')
        copy(browsers[0].parent, OUT / 'runtime/browser')
        copy(ROOT / 'data/models/faster-whisper-small', OUT / 'resources/models/faster-whisper-small')
        copy(ROOT / 'data/history/hs300-20240101-20261101', OUT / 'resources/history/hs300-20240101-20261101')
    for name in ['app', 'frontend', 'licenses']:
        copy(ROOT / name, OUT / name)
    for name in ['portable_launch.py', 'PortableLauncher.cs']:
        copy(ROOT / 'scripts' / name, OUT / 'scripts' / name)
    for name in ['requirements-lock.txt', 'package.json', 'package-lock.json', 'README.md']:
        copy(ROOT / name, OUT / name)
    csc = Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')
    subprocess.run([str(csc), '/nologo', '/target:winexe', '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll',
                    '/out:' + str(OUT / 'StrategyWorkbench.exe'), str(ROOT / 'scripts/PortableLauncher.cs')], check=True)
    subprocess.run([str(csc), '/nologo', '/target:winexe', '/define:STOP', '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll',
                    '/out:' + str(OUT / 'StopWorkbench.exe'), str(ROOT / 'scripts/PortableLauncher.cs')], check=True)
    (OUT / '使用说明.txt').write_text(
        '策略拾录 0.6.0 Windows 便携版\n\n'
        '1. 完整解压到可写目录，双击 StrategyWorkbench.exe。首次导入内置历史行情需要片刻。\n'
        '2. 软件自动打开浏览器；语音模型、Python、下载浏览器及缓存均已内置，无需安装配置。\n'
        '3. 只需在 AI 设置中选择模型供应商并填写自己的 API Key。Key 使用 Windows 本机加密。\n'
        '4. 用户资料及缓存保存在本软件目录 user-data，可整体备份；不要删除它。\n'
        '5. 关闭浏览器后本地服务仍运行；双击 StopWorkbench.exe 可完全退出。请在转写/回测任务结束后退出。\n'
        '6. 回测和模拟盘不连接券商、不产生真实订单；日线无法复现盘中打板/盘口规则。\n'
        '7. 公共视频或免费行情仍受平台网络、验证码及可用性影响；失败会保留缓存并支持重试。\n'
        '8. 第三方组件及模型许可见 runtime/python/LICENSE.txt、resources/models 和 licenses。\n', encoding='utf-8')
    manifest = {'version': '0.6.0', 'platform': 'windows-x64', 'python': sys.version.split()[0],
                'includes_user_data': False, 'includes_api_keys': False,
                'asr': 'faster-whisper-small', 'build_files': {}}
    for folder in ['app', 'frontend', 'scripts']:
        for path in (OUT / folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                manifest['build_files'][path.relative_to(OUT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(OUT), 'source_files': len(manifest['build_files'])}), flush=True)
    if args.zip:
        archive = OUT.with_name(OUT.name + '.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
            for path in OUT.rglob('*'):
                relative = path.relative_to(OUT)
                if path.is_file() and not any(p in ('user-data', '__pycache__') for p in relative.parts) and path.suffix != '.log':
                    z.write(path, Path(OUT.name) / relative)
        checksum = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
        archive.with_suffix('.zip.sha256').write_text(checksum + '  ' + archive.name + '\n', encoding='ascii')
        print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': checksum}), flush=True)


if __name__ == '__main__':
    main()
