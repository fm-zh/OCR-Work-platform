import sys
from pathlib import Path

# 讓 pytest 能 `from app import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))
