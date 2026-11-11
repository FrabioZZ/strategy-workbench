from pathlib import Path
from app.models import Segment


class ASR:
    def __init__(self, settings):
        self.settings = settings

    def transcribe(self, path, title='', config=None):
        if not self.settings.asr_ready():
            raise ValueError("本地 ASR 未配置：请设置 ASR_MODEL_PATH 指向已下载的 faster-whisper 模型目录，或导入字幕/文本。")
        return transcribe_in_worker(path, self.settings, title, config)


def transcribe_in_worker(path: Path, settings, title='', config=None):
    # Never download a model implicitly. PyAV decodes audio without a system ffmpeg.
    import av
    from faster_whisper import WhisperModel
    with av.open(str(path)) as media:
        if not media.streams.audio:
            raise ValueError("媒体中没有音频轨道")
        if media.duration is None:
            raise ValueError("无法确定媒体时长，请转换为标准音视频文件后重试")
        if media.duration / av.time_base > settings.max_duration_seconds:
            raise ValueError("媒体时长超过120分钟，请拆分后上传")
    model = WhisperModel(settings.asr_model, device=settings.asr_device,
                         compute_type=settings.asr_compute_type, local_files_only=True)
    from app.asr.configuration import context_text, vocabulary
    options = {} if config is None else dict(initial_prompt=context_text(config, title), hotwords=' '.join(vocabulary(config)))
    chunks, _ = model.transcribe(str(path), language="zh", beam_size=5, vad_filter=True, **options)
    segments = []
    total = 0
    for chunk in chunks:
        if not chunk.text.strip():
            continue
        total += len(chunk.text)
        if total > 120000 or len(segments) >= 3000 or chunk.end > settings.max_duration_seconds:
            raise ValueError("转写超出长度或时长限制，请拆分媒体")
        segments.append(Segment(id=f"s{len(segments)+1}", start=chunk.start, end=chunk.end, text=chunk.text.strip()).model_dump())
    if not segments:
        raise ValueError("未识别到语音，请检查音轨或导入字幕")
    return segments
