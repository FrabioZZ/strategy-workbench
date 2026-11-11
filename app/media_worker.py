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
            from app.asr.configuration import ASRConfiguration
            settings = Settings(**request['settings'])
            settings.data_dir = Path(settings.data_dir)
            config = ASRConfiguration(settings).current()
            selected = request.get('asr_selection', {'provider':'local'})
            if any(config.get(k) != v for k,v in selected.items()):
                raise ValueError('ASR 配置已变化，请核对设置后使用缓存重试。')
            if config['provider'] == 'qwen':
                from app.adapters.qwen_asr import QwenASR
                result = QwenASR(config, Path(request['cache']), duration=settings.max_duration_seconds).transcribe(Path(request['path']), request.get('title',''))
            else:
                segments = ASR(settings).transcribe(Path(request['path']), request.get('title',''), config)
                result = {'segments':segments, 'metadata':{'provider':'local','model':Path(settings.asr_model).name}, 'raw':{'segments':segments}}
        response = {"ok": True, "result": result}
    except Exception as exc:
        if request['operation'] == 'download':
            from app.adapters.download import safe_download_error
            message = safe_download_error(exc)
        elif request['operation'] == 'probe':
            message = '无法确认媒体类型或时长，请保存缓存文件用本地播放器打开，或转换后重新上传。'
        else:
            message = str(exc) if isinstance(exc, ValueError) and str(exc).startswith(('Qwen','云','ASR','请先','上次','媒体中','无法确认','音轨')) else '语音转写失败：请检查独立ASR配置、媒体音轨、时长与运行环境；缓存已保留，可重试或改用字幕。'
        response = {"ok": False, "error": message}
    output.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
