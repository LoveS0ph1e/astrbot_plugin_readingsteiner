"""pytest 引导：把项目根加入 sys.path，使 `from core.xxx` / `from commands.xxx` 可导入。

测试不依赖 AstrBot（core/* 用 TYPE_CHECKING 守卫 astrbot import），故可脱离 AstrBot 运行。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
