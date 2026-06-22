"""注入：检索结果 → 记忆文本 → 改写 ProviderRequest。

注入文本结构（区分稳定画像与相关情景）：
    <ReadingSteiner_Memory>
    【用户长期印象】          ← profiles[].profile_data（恒注入）
    ...
    【相关情景记忆】          ← episodes[] 按 score top-n
    - [时间] {summary}
    </ReadingSteiner_Memory>

本模块不解析身份（接收已检索结果），不调 EverOS（分层不串味）。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .constants import (
    DEFAULT_MEMORY_PREFIX,
    DEFAULT_MEMORY_SUFFIX,
    INJECT_POSITION_APPEND,
    INJECT_TARGET_SYSTEM,
    PROFILE_FIELD_EXPLICIT,
    PROFILE_FIELD_IMPLICIT,
    PROFILE_FIELD_SUMMARY,
    PROFILE_KEY_CATEGORY,
    PROFILE_KEY_DESCRIPTION,
    PROFILE_KEY_TAGS,
    PROFILE_KEY_TRAIT,
)

if TYPE_CHECKING:
    from astrbot.api.provider import ProviderRequest


def _cfg(config, key: str, default):
    if config is None:
        return default
    getter = getattr(config, "get", None)
    return getter(key, default) if callable(getter) else default


def resolve_covenant(config, user_id) -> str:
    """取指定用户的「永恒铭契」(ETERNAL_COVENANT)——人工锁定的不变核心设定。

    配置项 eternal_covenant 是 JSON 文本：{"<user_id>": "<固定核心设定>", ...}。
    命中则返回该用户的铭契文本，作为注入首块（不可变 canon，优先于 EverOS 演进画像）。
    无配置 / user_id 空 / JSON 非法 / 结构不符 / 未命中 → 返回 ''（安全降级，绝不阻断注入）。

    纯函数（不 log、不引 astrbot），延续本模块零运行时依赖、测试免 mock 的性质；
    配置正确性由部署期真机验证兜底。
    """
    if not user_id:
        return ""
    raw = _cfg(config, "eternal_covenant", "")
    if not raw or not isinstance(raw, str):
        return ""
    try:
        table = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    if not isinstance(table, dict):
        return ""
    text = table.get(str(user_id))
    return text.strip() if isinstance(text, str) and text.strip() else ""


def build_text(
    profiles: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    config=None,
    covenant: str = "",
) -> str:
    """拼装注入文本（永恒铭契 + 画像段 + 情景段）。都为空返回 ''（调用方据此跳过注入）。

    - covenant：永恒铭契（人工锁定的不变核心设定），非空则作首块，置于演进画像之上
    - profiles[0].profile_data 渲染为「用户长期印象」（恒注入，由 EverOS LLM 演进）
    - episodes[] 渲染为「相关情景记忆」（检索侧已按 score 排序/截断）
    """
    prefix = _cfg(config, "memory_prefix", DEFAULT_MEMORY_PREFIX)
    suffix = _cfg(config, "memory_suffix", DEFAULT_MEMORY_SUFFIX)
    parts: list[str] = []
    if covenant and covenant.strip():
        parts.append("【永恒铭契】\n" + covenant.strip())
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
    """渲染单条 profile。profile_data 是自由结构 object，防御式处理。

    优先按 EverOS 实测 schema（summary/explicit_info/implicit_traits）渲染成整洁中文；
    非该结构则回退到通用 key: value 平铺；str 则原样。
    注入只保留对人设有用的字段（总体印象/类别+描述/特质+标签），
    丢弃 evidence/basis/timestamp 等溯源字段（降噪省 token，质量校验另在 profile_quality）。
    """
    data = profile.get("profile_data", profile)
    if isinstance(data, str):
        return data.strip()
    if not isinstance(data, dict):
        return str(data).strip() if data is not None else ""
    # 命中 EverOS 画像 schema → 结构化中文渲染
    schema_keys = (PROFILE_FIELD_SUMMARY, PROFILE_FIELD_EXPLICIT, PROFILE_FIELD_IMPLICIT)
    if any(k in data for k in schema_keys):
        rendered = _render_everos_profile(data)
        if rendered:
            return rendered
    return _render_generic_dict(data)


def _render_everos_profile(data: dict[str, Any]) -> str:
    """EverOS 画像 schema → 整洁中文。三段：总体印象 / 显式信息 / 隐含特质。"""
    blocks: list[str] = []
    summary = data.get(PROFILE_FIELD_SUMMARY)
    if isinstance(summary, str) and summary.strip():
        blocks.append(f"总体印象：{summary.strip()}")

    exp_lines = []
    for item in data.get(PROFILE_FIELD_EXPLICIT) or []:
        if not isinstance(item, dict):
            continue
        desc = (item.get(PROFILE_KEY_DESCRIPTION) or "").strip()
        if not desc:
            continue
        cat = (item.get(PROFILE_KEY_CATEGORY) or "").strip()
        exp_lines.append(f"- [{cat}] {desc}" if cat else f"- {desc}")
    if exp_lines:
        blocks.append("显式信息：\n" + "\n".join(exp_lines))

    imp_lines = []
    for item in data.get(PROFILE_FIELD_IMPLICIT) or []:
        if not isinstance(item, dict):
            continue
        trait = (item.get(PROFILE_KEY_TRAIT) or "").strip()
        desc = (item.get(PROFILE_KEY_DESCRIPTION) or "").strip()
        if not trait and not desc:
            continue
        tags = item.get(PROFILE_KEY_TAGS) or []
        tag_str = f"（{ '、'.join(str(t) for t in tags) }）" if tags else ""
        head = trait or desc
        body = f"：{desc}" if (trait and desc) else ""
        imp_lines.append(f"- {head}{tag_str}{body}")
    if imp_lines:
        blocks.append("隐含特质：\n" + "\n".join(imp_lines))
    return "\n".join(blocks)


def _render_generic_dict(data: dict[str, Any]) -> str:
    """通用 dict 平铺（非 EverOS schema 时的回退）。"""
    lines: list[str] = []
    for key, val in data.items():
        if val in (None, "", [], {}):
            continue
        if isinstance(val, (list, tuple)):
            val = "、".join(str(v) for v in val if v not in (None, ""))
        lines.append(f"- {key}：{val}")
    return "\n".join(lines)


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
