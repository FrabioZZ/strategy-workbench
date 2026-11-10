import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    data_dir: Path = ROOT / "data"
    max_upload_mb: int = 200
    max_duration_seconds: int = 7200
    task_timeout_seconds: int = 3600
    asr_model: str = ""
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    ai_provider: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    ai_timeout_seconds: int = 180

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        bundled_models = (ROOT / "resources" / "models" / "faster-whisper-small",
                          ROOT / "data" / "models" / "faster-whisper-small")
        default_model = next((str(p) for p in bundled_models if (p / "model.bin").is_file()), "")
        return cls(data_dir=Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve(),
                   max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "200")),
                   asr_model=os.getenv("ASR_MODEL_PATH", default_model),
                   asr_device=os.getenv("ASR_DEVICE", "cpu"),
                   asr_compute_type=os.getenv("ASR_COMPUTE_TYPE", "int8"),
                   ai_provider=os.getenv("AI_PROVIDER", ""), ai_base_url=os.getenv("AI_BASE_URL", ""),
                   ai_model=os.getenv("AI_MODEL", ""), ai_api_key=os.getenv("AI_API_KEY", ""))

    def asr_ready(self):
        return bool(self.asr_model and (Path(self.asr_model) / "model.bin").is_file())

    def ai_ready(self):
        return bool(self.ai_provider in ("openai", "ollama", "deepseek", "qwen", "kimi", "glm", "custom") and self.ai_base_url and self.ai_model
                    and (self.ai_provider == "ollama" or self.ai_api_key))

    def public(self):
        return {"asr_configured": self.asr_ready(), "ai_configured": self.ai_ready(),
                "ai_provider": self.ai_provider or None, "ai_model": self.ai_model or None,
                "max_upload_mb": self.max_upload_mb, "max_duration_minutes": self.max_duration_seconds // 60,
                "ai_note": "配置已填写，连接尚未验证" if self.ai_ready() else "未配置 AI，可先导入和校对文本",
                "asr_note": "本地模型已找到，运行时验证可用性" if self.asr_ready() else "未配置本地 ASR 模型；仍可下载或上传媒体，配置模型后再转写，也可使用字幕或文本"}
