"""pytest 引导：让测试可导入插件模块。

两条 sys.path：
- 项目根：使 `from core.xxx` / `from commands.xxx` 可导入（core 内部用单点相对导入，自洽）。
- 项目根的父目录：使 `from astrbot_plugin_readingsteiner.commands.handlers import ...` 可导入，
  让 handlers 的 `..core` 跨包相对导入按生产语义解析（生产中插件作为同名包加载）。

测试不依赖 AstrBot（core/* 用 TYPE_CHECKING 守卫 astrbot import），故可脱离 AstrBot 运行。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)
