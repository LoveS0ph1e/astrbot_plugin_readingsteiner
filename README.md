# astrbot_plugin_readingsteiner

基于 **EverOS 自进化记忆引擎**的 AstrBot 长期记忆插件：持久用户画像 + 按平台真实身份（QQ 号）硬隔离。

> 命名说明：项目名为 `astrbot_plugin_readingsteiner`；底层记忆能力由 EverOS 引擎提供。
> `docs/` 设计文档中出现的 `astrbot_plugin_everos` 指代的即本插件。

## 功能

- **持久用户画像**：EverOS 按 user_id 直取（KV lookup，不靠相似度召回）的稳定画像，
  每轮恒注入，渲染为整洁中文（总体印象 / 显式信息 / 隐含特质）。
- **相关情景召回**：按当前消息向量检索 top-n 历史情景，与画像互补注入。
- **身份硬隔离**：user_id 只取自消息真实发送者 QQ 号，绝不跨用户串线（防审计 §15.9）。
- **群聊隐私分层**：群聊默认只注入公开画像、丢弃情景细节（防私聊内容泄露）。
- **画像质量抽查**：`/epk quality` 规则校验画像提取质量（必填完整性、缺证据=疑似幻觉、
  重复特质、冗长），输出 0-100 评分。
- **降级安全**：EverOS 不可达时对话照常，仅记日志，不抛异常给用户。

## 命令

| 命令 | 作用 | 权限 |
|---|---|---|
| `/epk flush` | 手动归档当前会话 | 所有人 |
| `/epk help` | 显示命令帮助 | 所有人 |
| `/epk status` | 连接状态、当前身份、记忆计数 | 管理员 |
| `/epk search <q>` | 检索当前用户记忆（调试） | 管理员 |
| `/epk quality` | 抽查当前用户画像质量 | 管理员 |
| `/epk forget` | 记忆删除说明 | 管理员 |

> `epk` = El Psy Kongroo。返回给用户的展示文本为英文；注入给 LLM 的记忆为中文。

## 快速开始（3 步）

1. **起 EverOS**：参考 [EverOS 官方 QUICKSTART](https://github.com/) 部署引擎（或用本仓库 `deploy/` 的 `docker compose up`）。
2. **填 base_url**：在插件配置里把 `everos_base_url` 指向你的 EverOS 服务（默认 `http://everos:8000`）。
3. **开插件**：在 AstrBot 启用本插件，发一条消息即开始积累记忆。

## 主要配置

| 配置项 | 默认 | 说明 |
|---|---|---|
| `everos_base_url` | `http://everos:8000` | EverOS 服务地址（非容器/单机改 `http://127.0.0.1:8000`） |
| `enable_injection` | `true` | 启用自动记忆注入 |
| `enable_archiving` | `true` | 启用自动对话归档 |
| `injection_target` | `user_prompt` | 注入目标（`user_prompt` / `system_prompt`） |
| `search_top_k` | `5` | 情景记忆检索条数 |
| `include_profile` | `true` | 恒注入用户画像 |
| `archive_strategy` | `auto` | 归档触发策略（`auto` / `every_turn` / `manual`） |
| `group_public_only` | `true` | 群聊只注入公开画像层（隐私保护） |
| `isolation_personas` | `` | 独立记忆空间的人格白名单（逗号分隔） |
| `enabled_sessions` | `` | 会话白名单（留空=全部启用） |

完整配置见 `_conf_schema.json`（AstrBot 自动渲染为配置面板）。

## 与 Mnemosyne 的差异

Mnemosyne 是纯向量召回，回答"与当前提问相似的历史片段是什么"；本插件在其之上增加
EverOS 的**持久用户画像**，回答"这个用户是谁"——画像按 user_id 直取、每轮恒注入、
LLM 增量更新去重，不受当前提问是否命中相似历史影响。

## 已知边界（不藏）

- **画像质量校验是规则底线**：`/epk quality` 能查结构缺陷与"无证据=疑似幻觉"，
  但无法识别"证据存在但推断错误"的语用误判（需 LLM judge，未做）。
- **无删除端点**：EverOS v1 API 仅 add/flush/get/search，删除需在 EverOS 侧操作磁盘文件。
- **EverOS 无内置鉴权**：默认绑 127.0.0.1 本地安全；暴露公网需自加网关。
- **最终一致**：flush 后 search 可能有约 1s（高负载更久）延迟。

## 本地开发

```bash
.venv\Scripts\activate              # 激活虚拟环境（Windows）
pip install -r requirements-dev.txt # 安装开发依赖
pytest                              # 运行测试
ruff check .                        # 格式检查
```

## 设计文档

完整构建规划见 `docs/`（按 `00`→`06` 顺序阅读）。EverOS API 契约、身份映射铁律、
部署形态均以这些文档为准。

## 许可证与致谢

本插件以 [Apache License 2.0](LICENSE) 发布。记忆能力由 [EverOS](https://github.com/) 引擎
（Apache-2.0）提供；集成范式参考了 Mnemosyne 插件。
