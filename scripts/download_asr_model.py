"""Explicit opt-in download; not called by the app or setup scripts."""
import argparse
from pathlib import Path
from huggingface_hub import snapshot_download

parser = argparse.ArgumentParser(description="显式下载本地 faster-whisper 模型（首次需要联网和磁盘空间）")
parser.add_argument("--model", choices=["tiny", "base", "small", "medium", "large-v3"], required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
snapshot_download(repo_id=f"Systran/faster-whisper-{args.model}", local_dir=str(args.output.resolve()), token=False)
print(f"ASR_MODEL_PATH={args.output.resolve()}")
