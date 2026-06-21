"""身份解析：AstrBot event → EverOS 身份元组。隔离正确性的命门。

# ════════════════ 铁律（违反即重蹈审计 §15.9 跨用户串线）════════════════
# 铁律 1：user_id 必须来自 event 的真实发送者 QQ 号，不接受外部/LLM 传参。
# 铁律 2：取不到有效 user_id 时返回 None，调用方跳过记忆——绝不回退 "default"。
# 铁律 3：检索只用单一 user_id，绝不轮询 [uid, "default"]。
# 反面教材：astrbot_plugin_everos_integration/tools/everos_tools.py:
#   - 第65行  resolved_user_id = user_id or persona_name or "default"   ← 违反铁律1/2
#   - 第227行 candidate_uids = [resolved_user_id, "default"]            ← 违反铁律3
# ═══════════════════════════════════════════════════════════════════════

身份取值全部基于 AstrBot 官方方法（astr_message_event.py 实证，01 §3.5）：
- user_id   = event.get_sender_id()        （QQ 号，astr_message_event.py:202-207）
- session_id= event.unified_msg_origin     （会话唯一标识，property:103-112）
- is_group  = event.get_group_id() != ""   （私聊返 ""，:194-196）
- bot_id    = event.get_self_id()          （assistant sender_id，:198-200）

本模块只读 event + config，不调 EverOS（分层不串味，05 §三）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .constants import (
    ASSISTANT_SENDER_ID,
    DEFAULT_APP_ID,
    DEFAULT_PROJECT_ID,
)

if TYPE_CHECKING:  # 仅类型检查时引入，运行时不依赖 AstrBot（便于脱离 AstrBot 单测）
    from astrbot.api.event import AstrMessageEvent


@dataclass(frozen=True)
class Identity:
    """从 event 确定性解析出的 EverOS 身份。"""

    user_id: str  # 发送者 QQ 号（EverOS sender_id/user_id 索引键）
    session_id: str  # = event.unified_msg_origin
    app_id: str  # 含人格隔离后缀（若在白名单）
    project_id: str
    is_group: bool
    bot_id: str  # assistant sender_id


def _cfg(config, key: str, default):
    """兼容 AstrBotConfig(dict 子类) 与普通 dict / None。"""
    if config is None:
        return default
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter(key, default)
    return default


def resolve(event: AstrMessageEvent, config=None) -> Identity | None:
    """从 event 确定性解析身份。取不到 user_id 返回 None（铁律 2）。

    全部用 AstrBot 官方方法（01 §3.5）。鸭子类型调用，便于单测传 mock event。
    """
    user_id = event.get_sender_id()
    if not user_id:  # 铁律 2：取不到不兜底，返回 None 让调用方跳过
        return None
    session_id = event.unified_msg_origin
    is_group = event.get_group_id() != ""  # 私聊 get_group_id 返 ""
    app_id = _resolve_app_id(event, config)
    project_id = _cfg(config, "project_id", DEFAULT_PROJECT_ID)
    bot_id = event.get_self_id() or ASSISTANT_SENDER_ID
    return Identity(
        user_id=str(user_id),
        session_id=str(session_id),
        app_id=app_id,
        project_id=project_id,
        is_group=is_group,
        bot_id=str(bot_id),
    )


def _parse_whitelist(raw: str) -> set[str]:
    """逗号分隔的人格白名单 → set。空串/None → 空集。"""
    if not raw:
        return set()
    return {p.strip() for p in str(raw).split(",") if p.strip()}


def _resolve_app_id(event, config) -> str:
    """按 isolation_personas 白名单决定 app_id 是否加人格后缀。

    逻辑参考 config_manager.get_app_id_for（everos_integration/core/config_manager.py:63-72）：
    白名单内人格 → f"{base}_{persona}"；否则共享 base。

    ⚠️ 人格名的获取方式『以 AstrBot 运行时为准』（04 注），本插件证据基里未确认确切 API。
       按铁律①不脑补：白名单为空（默认）时直接返回 base，根本不查人格；
       仅当用户显式配置了白名单，才防御式尝试解析人格名，解析不到则安全回退 base。
    """
    base = _cfg(config, "app_id", DEFAULT_APP_ID)
    whitelist = _parse_whitelist(_cfg(config, "isolation_personas", ""))
    if not whitelist:
        return base
    persona = _get_persona_name(event, config)
    if persona and persona in whitelist:
        return f"{base}_{persona}"
    return base


def _get_persona_name(event, config) -> str | None:
    """防御式获取当前会话人格名（扩展点）。

    证据基未确认确切 API，故只做无副作用的属性探测，全部失败则返回 None
    （调用方安全回退共享 app_id，绝不影响 user_id 隔离这条命门）。
    """
    for attr in ("persona_name", "persona_id"):
        val = getattr(event, attr, None)
        if isinstance(val, str) and val:
            return val
    return None
