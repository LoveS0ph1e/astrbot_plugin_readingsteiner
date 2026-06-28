"""/epk 命令组的实现（命令逻辑在此，main 只绑定）。

每个 impl 是 async generator，逐条 yield event.plain_result(...)，由 main 的命令方法代理 yield。

降级安全：EverOS 不可达时命令返回友好提示，不抛异常。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core import archiving, forget, injection, profile_quality, visibility
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


async def forget_impl(plugin, event: AstrMessageEvent, args: str = ""):
    """[管理员] /epk forget [all|clear|<描述>]：遗忘(抑制)当前用户的记忆。

    插件侧抑制：在注入/召回读路径过滤掉匹配的记忆——数据仍在 EverOS，只是不再被召回/注入。
    身份只从 event 解析(铁律)，作用于调用者本人。子命令：
    - 无参：列出当前遗忘规则 + 用法。
    - all：整用户 opt-out(此后不注入、不归档，可逆)。
    - clear / undo / reset：清空该用户全部遗忘规则。
    - 其余：作为遗忘短语加入(按内容抑制匹配条目)。
    真正从磁盘擦除需在 EverOS 侧操作(EverOS v1 无 HTTP 删除端点)。
    """
    if not plugin.config.get("enable_forget", True):
        yield event.plain_result(f"{LOG_PREFIX} Forget feature is disabled (enable_forget=false).")
        return
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} Cannot resolve identity.")
        return
    store = getattr(plugin, "_forget_store", None)
    if store is None:
        yield event.plain_result(f"{LOG_PREFIX} Forget feature is unavailable (store init failed).")
        return
    uid = ident.user_id
    sub = (args or "").strip()
    low = sub.lower()
    try:
        if not sub:
            yield event.plain_result(_format_forget_status(uid, store.get(uid)))
            return
        if low == "all":
            store.set_forget_all(uid, True)
            yield event.plain_result(
                f"{LOG_PREFIX} Opt-out set for user {uid}: this user's memories will no longer "
                "be injected or archived. Reversible with /epk forget clear."
            )
            return
        if low in ("clear", "undo", "reset"):
            existed = store.clear(uid)
            yield event.plain_result(
                f"{LOG_PREFIX} Forget rules cleared for user {uid}."
                if existed
                else f"{LOG_PREFIX} No forget rules to clear for user {uid}."
            )
            return
        if len(forget.normalize(sub)) < forget.MIN_PHRASE_LEN:
            yield event.plain_result(
                f"{LOG_PREFIX} Phrase too short (need >= {forget.MIN_PHRASE_LEN} chars after "
                "normalization); nothing changed."
            )
            return
        added = store.add_phrase(uid, sub)
        if added:
            yield event.plain_result(
                f"{LOG_PREFIX} Will suppress memories matching “{sub}” for user {uid} "
                "(filtered from recall/injection; data stays in EverOS — true on-disk "
                "erasure needs EverOS-side ops). Undo with /epk forget clear."
            )
        else:
            yield event.plain_result(
                f"{LOG_PREFIX} “{sub}” is already in the forget list; nothing changed."
            )
    except forget.ForgetStoreError as e:
        yield event.plain_result(f"{LOG_PREFIX} Forget failed: {e}")


def _format_forget_status(user_id: str, state: forget.ForgetState | None) -> str:
    """无参 /epk forget 的回显：当前 forget_all/短语清单 + 用法 + 真擦除提示。"""
    lines = [f"{LOG_PREFIX} Forget rules for user {user_id}:"]
    if state is None or (not state.forget_all and not state.phrases):
        lines.append("  (none)")
    else:
        if state.forget_all:
            lines.append("  - forget_all: ON (no injection, no archiving)")
        for p in state.phrases:
            lines.append(f"  - phrase: {p}")
    lines.append("Usage: /epk forget <text> | all | clear")
    lines.append("Note: suppression only; on-disk erasure needs EverOS-side ops.")
    return "\n".join(lines)


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
    # 记忆遗忘(抑制)：闭合 LLM 工具泄露面——recall_impl 也是 epk_recall 工具的后端，
    # 不接 forget 则 forget_all 用户仍可被模型经工具召回。
    store = getattr(plugin, "_forget_store", None)
    if plugin.config.get("enable_forget", True) and store is not None:
        fstate = store.get(ident.user_id)
        if fstate and fstate.forget_all:
            return "No stored memory available for this user."
        profiles, episodes = forget.apply_forget(profiles, episodes, fstate)
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
        "/epk forget [all|clear|<text>]  Suppress this user's memories (admin)"
    )
