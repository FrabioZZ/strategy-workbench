"""Windows child waits until its parent has attached the process-tree Job Object."""
from pathlib import Path
import subprocess
import sys
import time

gate = Path(sys.argv[1])
deadline = time.monotonic() + 10
while not gate.is_file():
    if time.monotonic() > deadline:
        sys.exit(2)
    time.sleep(0.01)
sys.exit(subprocess.call(sys.argv[2:]))
