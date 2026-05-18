"""pytest conftest：让测试能 import 上一级的项目模块。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
