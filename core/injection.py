"""注入：检索结果 → 记忆文本 → 改写 ProviderRequest。

注入文本结构（02 §3.1，区分稳定画像与相关情景）：
    <ReadingSteiner_Memory>
    【用户长期印象】          ← profiles[].profile_data（恒注入）
    ...
    【相关情景记忆】          ← episodes[] 按 score top-n
    - [时间] {summary}
    </ReadingSteiner_Memory>

inject 范式出处：Mnemosyne memory_operations.py:1023-1058（prepend/append × system/user）。
本模块不解析身份（接收已检索结果），不调 EverOS（分层不串味，05 §三）。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .constants import (
    DEFAULT_MEMORY_PREFIX,
    DEFAULT_MEMORY_SUFFIX,
    INJECT_POSITION_APPEND,
    INJECT_TARGET_SYSTEM,
)

if TYPE_CHECKING:
    from astrbot.api.provider import ProviderRequest


def _cfg(config, key: str, default):
    if config is None:
        return default
    getter = getattr(config, "get", None)
    return getter(key, default) if callable(getter) else default


def build_text(
    profiles: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    config=None,
) -> str:
    """拼装注入文本（画像段 + 情景段）。都为空返回 ''（调用方据此跳过注入）。

    - profiles[0].profile_data 渲染为「用户长期印象」（恒注入）
    - episodes[] 渲染为「相关情景记忆」（检索侧已按 score 排序/截断）
    """
    prefix = _cfg(config, "memory_prefix", DEFAULT_MEMORY_PREFIX)
    suffix = _cfg(config, "memory_suffix", DEFAULT_MEMORY_SUFFIX)
    parts: list[str] = []
    if profiles:
        rendered = _render_profile(profiles[0])
        if rendered:
            parts.append("【用户长期印象】\n" + rendered)
    if episodes:
        rendered = _render_episodes(episodes)
        if rendered:
            parts.append("【相关情景记忆】\n" + rendered)
    if not parts:
        return ""
    return f"{prefix}\n" + "\n\n".join(parts) + f"\n{suffix}"


def inject(
    req: ProviderRequest,
    text: str,
    target: str = INJECT_TARGET_SYSTEM,
    position: str = "prepend",
) -> None:
    """改写 req。target: system_prompt|user_prompt；position: prepend|append。

    空 text 直接返回（不污染 req）。范式：Mnemosyne memory_operations.py:1023-1058。
    """
    if not text:
        return
    append = position == INJECT_POSITION_APPEND
    if target == INJECT_TARGET_SYSTEM:
        cur = req.system_prompt if isinstance(req.system_prompt, str) else ""
        # system 段拼接不额外加换行符头尾，由 text 自身的 prefix/suffix 兜边界
        req.system_prompt = (cur + text) if append else (text + cur)
    else:  # user_prompt
        cur = req.prompt if isinstance(req.prompt, str) else ""
        req.prompt = (cur + "\n" + text) if append else (text + "\n" + cur)


def _render_profile(profile: dict[str, Any]) -> str:
    """渲染单条 profile。profile_data 是自由结构 object（01 §2.4），防御式处理。

    优先取 profile_data；它可能是 str、dict 或缺失。dict 则按 key: value 平铺。
    """
    data = profile.get("profile_data", profile)
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        lines: list[str] = []
        for key, val in data.items():
            if val in (None, "", [], {}):
                continue
            if isinstance(val, (list, tuple)):
                val = "、".join(str(v) for v in val if v not in (None, ""))
            lines.append(f"- {key}：{val}")
        return "\n".join(lines)
    return str(data).strip() if data is not None else ""


def _render_episodes(episodes: list[dict[str, Any]]) -> str:
    """每条取 timestamp + summary（或 subject）。无 summary 的跳过。"""
    lines: list[str] = []
    for ep in episodes:
        text = ep.get("summary") or ep.get("subject") or ep.get("content")
        if not text:
            continue
        ts = _fmt_time(ep.get("timestamp"))
        lines.append(f"- [{ts}] {str(text).strip()}" if ts else f"- {str(text).strip()}")
    return "\n".join(lines)


def _fmt_time(ts: Any) -> str:
    """时间戳渲染。支持 Unix 毫秒 int / 秒 int / ISO 字符串；不可解析返回 ''。"""
    if ts is None:
        return ""
    if isinstance(ts, (int, float)):
        # 毫秒级（13 位）转秒
        seconds = ts / 1000 if ts > 1e11 else ts
        try:
            return datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            return ""
    return str(ts)
