"""Reproducible whitelist-only standalone source bundle, safe to copy to a Linux VM."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FILES = (
    'requirements-media-fetch.txt',
    'app/__init__.py', 'app/adapters/__init__.py', 'app/adapters/download.py',
    'app/adapters/download_network.py',
    'app/adapters/download_browser.py', 'app/adapters/douyin_browser.cjs',
    'package.json', 'package-lock.json',
    'scripts/validate_media_fetch.py', 'scripts/media_fetch_launcher.py',
    'tests/test_media_fetch_validation.py',
    'deploy/media-fetch/Dockerfile', 'deploy/media-fetch/.dockerignore',
    'deploy/media-fetch/samples.json', 'deploy/media-fetch/build_bundle.py',
    'docs/phase-1c-runbook.md',
)


def build(output):
    output = Path(output).resolve()
    if not output.name.startswith('phase1c-'):
        raise ValueError('Output must be a new phase1c-* directory')
    output.mkdir(parents=True, exist_ok=False)
    contents = {}
    for name in FILES:
        path = ROOT / name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Bundle source must be a regular project file')
        contents[name] = path.read_bytes()
    # Build context root is the bundle root; deny all files except this explicit list.
    contents['.dockerignore'] = contents['deploy/media-fetch/.dockerignore']
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(contents.items())}
    contents['bundle-manifest.json'] = (json.dumps({'schema_version': 1, 'sha256': manifest}, indent=2) + '\n').encode()
    bundle = output / 'media-fetch-validation.zip'
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, data)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (output / 'SHA256SUMS').write_text(f'{digest}  {bundle.name}\n', encoding='utf-8')
    (output / 'bundle-manifest.json').write_bytes(contents['bundle-manifest.json'])
    print(json.dumps({'bundle': bundle.name, 'sha256': digest, 'files': len(contents)}))
    return bundle


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    build(parser.parse_args().output_dir)
