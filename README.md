# astrbot_plugin_everos

基于 **EverOS 自进化记忆引擎**的 AstrBot 长期记忆插件：持久用户画像 + 按平台真实身份（QQ 号）硬隔离。

> 当前仓库为**初始工程脚手架**。内部架构（`core/`、`commands/`、`tests/` 等模块）尚未实现，
> 实现请遵循 `docs/` 下的构建规划文档，从 `03-构建任务清单.md` 的任务 0 开始。

## 项目状态

- ✅ 工程初始化：虚拟环境、依赖清单、工具链配置、`.gitignore`
- ⬜ 插件骨架（`main.py` / `metadata.yaml` / `_conf_schema.json`）
- ⬜ 核心模块（`core/`）
- ⬜ 管理命令（`commands/`）
- ⬜ 单元测试（`tests/`）
- ⬜ Docker 编排（`deploy/`）

## 环境要求

- Python 3.12+（与 EverOS `>=3.12` 对齐）
- 依赖见 `requirements.txt`（运行）/ `requirements-dev.txt`（开发）

## 本地开发

```bash
# 激活虚拟环境（Windows）
.venv\Scripts\activate

# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试 / 格式检查
pytest
ruff check .
```

## 设计文档

完整构建规划见 `docs/`（按 `00`→`06` 顺序阅读）。所有 EverOS API 契约、身份映射铁律、
部署形态均以这些文档为准，不得脑补未确认的接口。

## 致谢

记忆能力由 [EverOS](https://github.com/) 引擎提供；集成范式参考了 Mnemosyne 插件。
