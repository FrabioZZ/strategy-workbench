"""Isolated media worker; launched with shell=False and bounded runtime."""
import json
import sys
from pathlib import Path
from app.config import Settings


def main():
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    output = Path(sys.argv[2])
    try:
        if request["operation"] == "download":
            from app.adapters.download import download_in_worker
            result = download_in_worker(request["url"], Path(request["folder"]), request["limit"], request["duration"])
        elif request['operation'] == 'probe':
            from app.adapters.download import inspect_media
            path = Path(request['path']).resolve(strict=True)
            if not path.is_relative_to(Path(request['data_dir']).resolve()) or not path.is_file():
                raise ValueError('Invalid local media path')
            size = path.stat().st_size
            if not 0 < size <= request['limit']:
                raise ValueError('Local media size limit')
            result = {**inspect_media(path, request['duration'], require_audio=False),
                      'size_bytes': size, 'extension': path.suffix.lstrip('.'), 'probe_status': 'ready'}
        else:
            from app.adapters.asr import ASR
            result = ASR(Settings(**request["settings"])).transcribe(Path(request["path"]))
        response = {"ok": True, "result": result}
    except Exception as exc:
        if request['operation'] == 'download':
            from app.adapters.download import safe_download_error
            message = safe_download_error(exc)
        elif request['operation'] == 'probe':
            message = '无法确认媒体类型或时长，请保存缓存文件用本地播放器打开，或转换后重新上传。'
        else:
            message = '本地转写失败：请检查模型文件、媒体音轨、时长与CPU/GPU运行环境；缓存已保留，可重试或改用字幕。'
        response = {"ok": False, "error": message}
    output.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
