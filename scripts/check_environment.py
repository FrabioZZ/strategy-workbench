"""Read-only environment check. Does not call a model or download anything."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Settings

result = {"python": sys.version.split()[0], "configuration": Settings.from_env().public()}
for name in ("faster_whisper", "av", "ctranslate2", "yt_dlp", "fastapi"):
    try:
        module = __import__(name)
        result[name] = getattr(module, "__version__", "import OK")
    except Exception:
        result[name] = "import failed"
print(json.dumps(result, ensure_ascii=False, indent=2))
