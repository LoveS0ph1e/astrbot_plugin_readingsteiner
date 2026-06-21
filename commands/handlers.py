"""/epk 命令组的实现（命令逻辑在此，main 只绑定）。

每个 impl 是 async generator，逐条 yield event.plain_result(...)，由 main 的命令方法代理 yield。

降级安全：EverOS 不可达时命令返回友好提示，不抛异常。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core import archiving, injection, profile_quality, visibility
from ..core import identity as identity_mod
from ..core.constants import LOG_PREFIX, MEMORY_TYPE_EPISODE, MEMORY_TYPE_PROFILE
from ..core.everos_client import EverOSUnavailable

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


async def status_impl(plugin, event: AstrMessageEvent):
    """/epk status：EverOS 健康、当前 scope、本会话 user_id、记忆计数。"""
    base_url = plugin.config.get("everos_base_url", "?")
    healthy = await plugin._healthy()
    if not healthy:
        yield event.plain_result(
            f"{LOG_PREFIX} EverOS: disconnected ({base_url})\n"
            "Check that the EverOS container is up and base_url is correct."
        )
        return
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(
            f"{LOG_PREFIX} EverOS: connected ({base_url})\nCannot resolve identity."
        )
        return
    lines = [
        f"{LOG_PREFIX} EverOS: connected ({base_url})",
        f"session: {'group' if ident.is_group else 'private'} / user_id={ident.user_id}",
        f"scope: app_id={ident.app_id} project_id={ident.project_id}",
    ]
    try:
        for mtype, label in ((MEMORY_TYPE_PROFILE, "profile"), (MEMORY_TYPE_EPISODE, "episode")):
            data = await plugin.client.get(
                memory_type=mtype,
                user_id=ident.user_id,
                app_id=ident.app_id,
                project_id=ident.project_id,
                page=1,
                page_size=1,
            )
            lines.append(f"{label}: {data.get('total_count', 0)}")
    except EverOSUnavailable as e:
        lines.append(f"(failed to get memory counts: {e})")
    yield event.plain_result("\n".join(lines))


async def search_impl(plugin, event: AstrMessageEvent, query: str):
    """/epk search <query>：按当前用户检索并展示命中（调试/自查用）。"""
    if not query:
        yield event.plain_result("Usage: /epk search <query>")
        return
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} Cannot resolve identity, skipping search.")
        return
    if not await plugin._healthy():
        yield event.plain_result(f"{LOG_PREFIX} EverOS not connected.")
        return
    try:
        data = await plugin.client.search(
            query=query,
            user_id=ident.user_id,
            app_id=ident.app_id,
            project_id=ident.project_id,
            method=plugin.config.get("search_method", "hybrid"),
            top_k=int(plugin.config.get("search_top_k", 5)),
            include_profile=plugin.config.get("include_profile", True),
        )
    except EverOSUnavailable as e:
        yield event.plain_result(f"{LOG_PREFIX} Search failed: {e}")
        return
    profiles = data.get("profiles", []) or []
    episodes = data.get("episodes", []) or []
    lines = [f"{LOG_PREFIX} Search results (user_id={ident.user_id}):"]
    lines.append(f"profiles: {len(profiles)} / episodes: {len(episodes)}")
    for i, ep in enumerate(episodes[:5], 1):
        summary = ep.get("summary") or ep.get("subject") or "(no summary)"
        score = ep.get("score")
        lines.append(f"{i}. [{score}] {str(summary)[:80]}")
    yield event.plain_result("\n".join(lines))


async def flush_impl(plugin, event: AstrMessageEvent):
    """/epk flush：手动 flush 当前会话（manual 策略下的主触发）。"""
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} Cannot resolve identity.")
        return
    if not await plugin._healthy():
        yield event.plain_result(f"{LOG_PREFIX} EverOS not connected.")
        return
    try:
        data = await plugin.client.flush(ident.session_id, ident.app_id, ident.project_id)
        if plugin._flush_policy:
            plugin._flush_policy.discard(ident.session_id)
        yield event.plain_result(f"{LOG_PREFIX} flush done, status={data.get('status', '?')}")
    except EverOSUnavailable as e:
        yield event.plain_result(f"{LOG_PREFIX} flush failed: {e}")


async def forget_impl(plugin, event: AstrMessageEvent, confirm: str | None = None):
    """[管理员] /epk forget [confirm]：删除当前用户记忆。

    ⚠️ 诚实边界：EverOS v1 API 仅 add/flush/get/search 四个端点，无删除端点。
    故本命令无法经 API 删除记忆，只能如实告知正确做法：EverOS 记忆是磁盘上的
    markdown，删除需在 EverOS 侧操作。
    """
    yield event.plain_result(
        f"{LOG_PREFIX} EverOS v1 API has no delete endpoint; the plugin cannot delete memories.\n"
        "EverOS stores memories as markdown in its data dir "
        "(default ~/.everos or container /data/everos). To delete, remove the md files under "
        "the user's dir on the EverOS side, then rebuild the index (.index/ is rebuildable).\n"
        "See the EverOS official storage_layout docs."
    )


async def quality_impl(plugin, event: AstrMessageEvent):
    """/epk quality：抽查当前用户画像的提取质量（规则校验，无 LLM）。"""
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} Cannot resolve identity.")
        return
    if not await plugin._healthy():
        yield event.plain_result(f"{LOG_PREFIX} EverOS not connected.")
        return
    try:
        data = await plugin.client.get(
            memory_type=MEMORY_TYPE_PROFILE,
            user_id=ident.user_id,
            app_id=ident.app_id,
            project_id=ident.project_id,
            page=1,
            page_size=1,
        )
    except EverOSUnavailable as e:
        yield event.plain_result(f"{LOG_PREFIX} Failed to get profile: {e}")
        return
    profiles = data.get("profiles", []) or []
    if not profiles:
        yield event.plain_result(
            f"{LOG_PREFIX} No profile yet for this user (user_id={ident.user_id}). "
            "Chat a few more rounds and try again."
        )
        return
    report = profile_quality.check_profile(profiles[0])
    yield event.plain_result(
        f"{LOG_PREFIX} Profile quality check (user_id={ident.user_id}):\n"
        + profile_quality.format_report(report)
    )


async def recall_impl(plugin, event: AstrMessageEvent, query: str) -> str:
    """LLM 工具 epk_recall 的逻辑：检索当前用户记忆，返回文本给模型。

    身份只从 event 解析（铁律 1/3），模型传入的任何 user_id 都不被采纳。
    ⚠️ 始终返回非空 str：AstrBot 的 llm_tool 把 None 当作"已直接回复用户"，
       会触发 WARN 并可能静默吞掉本轮回复。无记忆/不可用时返回明确说明，
       让模型据此正常应答（对新用户，"无记忆"正是应当告知模型的信号）。
    """
    if not plugin.config.get("enable_llm_tools", False):
        return "Memory tool is disabled."
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        return "Cannot resolve the user's identity; no memory available."
    if not await plugin._healthy():
        return "Memory service is currently unavailable."
    try:
        data = await plugin.client.search(
            query=query,
            user_id=ident.user_id,  # 铁律：单一真实身份，绝不取模型传参
            app_id=ident.app_id,
            project_id=ident.project_id,
            method=plugin.config.get("search_method", "hybrid"),
            top_k=int(plugin.config.get("search_top_k", 5)),
            include_profile=plugin.config.get("include_profile", True),
        )
    except EverOSUnavailable:
        return "Memory service is currently unavailable."
    profiles = data.get("profiles", []) or []
    episodes = data.get("episodes", []) or []
    if plugin.config.get("group_public_only", True) and ident.is_group:
        profiles, episodes = visibility.filter_public(profiles, episodes)
    text = injection.build_text(profiles, episodes, plugin.config)
    return text or "No stored memory found for this user yet."


async def remember_impl(plugin, event: AstrMessageEvent, content: str) -> str:
    """LLM 工具 epk_remember 的逻辑：把一条事实主动写入当前用户记忆。

    身份只从 event 解析；写入走与自动归档相同的 add 通道（sender_id=真实 QQ 号）。
    ⚠️ 始终返回非空 str（理由同 recall_impl）：失败/禁用也给模型明确反馈。
    """
    if not plugin.config.get("enable_llm_tools", False):
        return "Memory tool is disabled."
    if not content or not content.strip():
        return "Nothing to remember (empty content)."
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        return "Cannot resolve the user's identity; nothing was saved."
    if not await plugin._healthy():
        return "Memory service is currently unavailable; nothing was saved."
    try:
        msgs = archiving.build_messages(content.strip(), "", ident)
        await plugin.client.add(ident.session_id, msgs, ident.app_id, ident.project_id)
        if plugin._flush_policy:
            plugin._flush_policy.mark_active(ident.session_id)
    except EverOSUnavailable:
        return "Memory service is currently unavailable; nothing was saved."
    return "Noted. I'll remember that."


async def help_impl(plugin, event: AstrMessageEvent):
    """/epk help：列出本插件真实存在的命令（与代码强一致）。"""
    yield event.plain_result(
        f"{LOG_PREFIX} ReadingSteiner memory plugin commands:\n"
        "/epk flush         Archive the current session now (everyone)\n"
        "/epk help          Show this help (everyone)\n"
        "—— admin only below ——\n"
        "/epk status        Connection status, current identity, memory counts\n"
        "/epk search <q>    Search memories for the current user (debug)\n"
        "/epk quality       Spot-check the current user's profile quality\n"
        "/epk forget        Memory deletion notice (API unsupported, see message)"
    )
