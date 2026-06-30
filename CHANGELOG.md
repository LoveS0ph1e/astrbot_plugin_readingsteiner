# Changelog

本项目所有重要变更记录于此。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> 版本系列代号 **Crepuscule**（源自莫扎特《魔笛》）；姊妹项目 Eyes of Priestess（管理 WebUI）的版本系列为 **Sarastro**。

## [Unreleased]

## [v0.5.0] - 2026-06-30

### Added
- **情景合并（Reflection）触发**：新增管理员命令 `/epk reflect`，触发 EverOS 的 `reflect_episodes`
  策略——把同簇碎片化情景由引擎 LLM 合并成连贯叙事、消解过粒度，原件软归档（可恢复）。需
  EverOS ≥ 1.1.0；旧版无该策略时友好提示需升级。属服务端维护操作（跨用户按簇运行），有损合并、
  建议低频 / 试点先行。
- **归档可观测**：新增 `log_archive_success`（默认开），每次成功 `add` / `flush` 打一条 INFO
  （含条数 / 状态），便于肉眼确认记忆已落库（此前成功为静默）。

### Changed
- **EverOS 客户端错误分级 + 有限重试**：解析 EverOS 1.1.0 的 typed `error.code` 包络，区分
  「可重试」（503 `EXTERNAL_SERVICE_UNAVAILABLE` / 传输层超时）与「永久」错误；前者按
  `everos_retry_retryable`（默认 1）做退避重试，后者立即降级。EverOS 报错不再打 ERROR 栈，改打
  分级 WARNING（带 code / 状态）。完全向后兼容 EverOS 1.0.x（无 code 时按 5xx 兜底判定）。

## [v0.4.0] - 2026-06-28

### Added
- **记忆遗忘（抑制）**：新增管理员命令 `/epk forget`，在注入/召回读路径上抑制匹配到的记忆——
  数据仍在 EverOS，只是不再被注入/召回，可逆。两种粒度：按内容短语 `/epk forget <描述>`
  （滤掉匹配的画像条目/情景）与整用户 `/epk forget all`（opt-out：不注入、不归档）；
  `/epk forget clear` 撤销，无参列出当前规则。受 `enable_forget`（默认开）控制。身份只取自
  消息发送者、作用于调用者本人；每用户规则存于 `forget/<user_id>.md`。

### Changed
- `/epk forget` 从「打印『API 无删除端点』的诚实桩」升级为真正的读路径抑制（见上）。
  注：EverOS v1 API 仍无删除端点、插件也不共享其文件系统，故这是「遗忘(抑制)」而非磁盘
  擦除；真正从磁盘删除仍需在 EverOS 侧操作。

### Fixed
- **群聊跨用户记忆串线（按发送者隔离会话）**：群聊中所有成员此前共用同一引擎会话键，导致
  多人对话被合并、按发送者抽取时把他人 / 助手的内容混入某用户画像（认错人、张冠李戴、把助手
  人设当成用户）。现群聊会话键按发送者拆分（在 `unified_msg_origin` 后追加 `#<user_id>`），每个
  成员独立会话，从源头杜绝跨用户混合记忆单元。私聊不受影响（其会话标识本就含 user_id）。
- **相关情景记忆注入半句截断**：注入的【相关情景记忆】此前优先取引擎的情景 `summary`，而该字段
  在未独立产出时为 `content` 的字符级硬截，常在句中斩断。现改用完整 `content` 按句末标点收束
  （中英双语：中文句末标点 + 后接空白 / 引号的英文 `.!?`），完整句注入、绝不留半截；`content`
  缺失才回退 `summary` / `subject`。

## [v0.3.1] - 2026-06-22

### Added
- **永恒铭契（ETERNAL_COVENANT）**：新增配置项 `eternal_covenant`，可为指定用户锁定一段
  人工定调的不变核心设定，作为独立的【永恒铭契】块注入，置于 EverOS 演进画像之上。
  解决 EverOS 每次 flush 用 LLM 重写整个 profile（含 summary）会把人工写定的核心设定
  冲淡的问题——铭契由插件配置锁定，永不被 flush 覆盖；而 summary/显式/隐式信息不受影响、
  继续交由 LLM 演进。含私密内容时群聊默认不注入（受 `group_public_only` 约束）。

### Fixed
- **记忆功能「假死」（热重载竞态）**：`on_astrbot_loaded` 在插件热重载竞态下可能不触发，
  而 `client`/`flush_policy` 旧版仅在该钩子中构造，导致其永为 `None`，注入与归档两个钩子
  双双静默早退——机器人对话正常但完全失忆，且无报错、无自愈。现将二者移入 `__init__`
  同步构造，确立「实例存在即记忆能力就绪」不变量，该失败模式被结构性消除。

### Changed
- `request_timeout` 默认值 30→90 秒：flush 触发的提取较慢，避免误判为失败。

### Docs
- 补充项目中文名「记忆探知之魔眼 (ReadingSteiner)」。

## [v0.3.0] - 2026-06-22

### Added
- **LLM 记忆工具（function-calling）**：新增两个工具，让模型在对话中主动读写记忆，
  与被动的自动注入/归档形成互补。
  - `epk_recall(query)`：检索当前用户的持久画像与历史情景。
  - `epk_remember(content)`：把一条关于当前用户的事实写入长期记忆。
  - 身份只从消息事件解析（`get_sender_id`），模型只能传 `query`/`content`，
    **绝不能指定 `user_id`**——从源头杜绝跨用户记忆串线。
  - 由新配置项 `enable_llm_tools` 控制（默认关闭，避免与自动注入重复消耗）。

### Fixed
- **新用户首条消息被静默吞掉**：工具实现此前在空结果/降级路径（无记忆、服务不可用、
  功能关闭）返回 `None`。AstrBot 将工具返回 `None` 视为「已直接回复用户」，会触发
  WARN 并可能静默结束本轮，导致新用户的第一条消息得不到任何回复。现在两个工具实现
  **在所有路径都返回非空状态字符串**，模型据此正常应答。

### Tests
- 新增 `tests/test_tools.py`（8 例）：覆盖身份隔离铁律（模型传入的 `user_id` 被忽略）、
  空记忆路径、以及全部降级路径。
- 修正 `tests/conftest.py` 的 `sys.path` 引导，使 handlers 的跨包相对导入按生产语义解析。

## [v0.2.0] - 2026-06

### Added
- 基于 EverOS 自进化记忆引擎的长期记忆能力：持久用户画像 + 相关情景召回。
- 按平台真实身份（消息发送者 ID）硬隔离记忆，多用户互不串线。
- `/epk` 命令组：记忆查询、画像查看、质量评估等运维指令。
- 自动注入（on_llm_request）与自动归档（on_llm_response）钩子。
- 群聊默认仅注入公开层信息（`group_public_only`），保护用户隐私。

[Unreleased]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/compare/v0.4.0...HEAD
[v0.4.0]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/releases/tag/v0.4.0
[v0.3.1]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/releases/tag/v0.3.1
[v0.3.0]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/releases/tag/v0.3.0
[v0.2.0]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/releases/tag/v0.2.0
