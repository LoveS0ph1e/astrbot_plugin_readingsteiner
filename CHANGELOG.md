# Changelog

本项目所有重要变更记录于此。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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

[v0.3.1]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/releases/tag/v0.3.1
[v0.3.0]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/releases/tag/v0.3.0
[v0.2.0]: https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner/releases/tag/v0.2.0
