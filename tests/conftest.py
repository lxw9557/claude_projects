"""pytest 配置 — 将项目根目录加入 sys.path，确保测试可导入项目模块。"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))
