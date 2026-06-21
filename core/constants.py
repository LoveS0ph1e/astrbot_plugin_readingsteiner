"""常量定义：默认值、标签、枚举。集中管理便于审计（05-审计与迭代规约.md §一）。

单一事实源：所有可变默认值的『代码侧 fallback』集中于此；与 _conf_schema.json 的 default 保持一致。
"""

# ── 连接默认值 ──
# 默认指向同 docker 网络的服务名（06-Docker部署）；非容器/单机改 127.0.0.1:8000。
DEFAULT_BASE_URL = "http://everos:8000"
DEFAULT_TIMEOUT = 30.0
DEFAULT_TOP_K = 5

# ── EverOS memory_type 枚举（仅这四种，对照 docs/api.md:448-457 / 01 §2.5）──
# ⚠️ 不含 user_profile —— 那是现有集成插件的 bug，本插件用 profile（05 §一）。
MEMORY_TYPE_EPISODE = "episode"
MEMORY_TYPE_PROFILE = "profile"
MEMORY_TYPE_AGENT_CASE = "agent_case"
MEMORY_TYPE_AGENT_SKILL = "agent_skill"
MEMORY_TYPES = (
    MEMORY_TYPE_EPISODE,
    MEMORY_TYPE_PROFILE,
    MEMORY_TYPE_AGENT_CASE,
    MEMORY_TYPE_AGENT_SKILL,
)

# ── EverOS profile_data 结构字段（实测 schema，01 §1.1：summary/explicit_info/implicit_traits）──
# injection 渲染与 profile_quality 校验共用，避免硬编码字符串散落（05 §一 单一事实源）。
PROFILE_FIELD_SUMMARY = "summary"
PROFILE_FIELD_EXPLICIT = "explicit_info"
PROFILE_FIELD_IMPLICIT = "implicit_traits"
PROFILE_FIELD_TIMESTAMP = "profile_timestamp_ms"
# explicit_info[] / implicit_traits[] 内部字段
PROFILE_KEY_CATEGORY = "category"
PROFILE_KEY_DESCRIPTION = "description"
PROFILE_KEY_EVIDENCE = "evidence"
PROFILE_KEY_TRAIT = "trait"
PROFILE_KEY_BASIS = "basis"
PROFILE_KEY_TAGS = "tags"

# ── 检索方法（对照 01 §2.4）──
SEARCH_METHOD_HYBRID = "hybrid"
SEARCH_METHODS = ("keyword", "vector", "hybrid", "agentic")

# ── 注入标签默认值（插件专属，勿与 Mnemosyne 的 <Mnemosyne> 撞，05 §一）──
DEFAULT_MEMORY_PREFIX = "<ReadingSteiner_Memory>"
DEFAULT_MEMORY_SUFFIX = "</ReadingSteiner_Memory>"

# 注入目标 / 位置
INJECT_TARGET_SYSTEM = "system_prompt"
INJECT_TARGET_USER = "user_prompt"
INJECT_POSITION_PREPEND = "prepend"
INJECT_POSITION_APPEND = "append"

# ── 归档策略（02 §3.3）──
ARCHIVE_AUTO = "auto"
ARCHIVE_EVERY_TURN = "every_turn"
ARCHIVE_MANUAL = "manual"

# assistant 消息的 sender_id 兜底（user 消息用真实 QQ 号；assistant 优先用 self_id）
ASSISTANT_SENDER_ID = "assistant"

# scope 默认
DEFAULT_APP_ID = "astrbot"
DEFAULT_PROJECT_ID = "default"

# 日志前缀（统一便于 grep，05 §一）
LOG_PREFIX = "[everos]"
