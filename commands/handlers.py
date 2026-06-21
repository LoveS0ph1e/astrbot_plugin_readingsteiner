"""/epk 命令组的实现（02 §二：命令逻辑在此，main 只绑定）。

每个 impl 是 async generator，逐条 yield event.plain_result(...)，由 main 的命令方法代理 yield。
范式参考 Mnemosyne/main.py:649-741（command_group + impl 代理 + permission_type + confirm）。

降级安全：EverOS 不可达时命令返回友好提示，不抛异常（05 §二）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core import identity as identity_mod
from ..core import profile_quality
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
            f"{LOG_PREFIX} EverOS: 未连接 ({base_url})\n"
            "请确认 EverOS 容器已 up、base_url 配置正确。"
        )
        return
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} EverOS: 已连接 ({base_url})\n当前无法解析身份。")
        return
    lines = [
        f"{LOG_PREFIX} EverOS: 已连接 ({base_url})",
        f"会话: {'群聊' if ident.is_group else '私聊'} / user_id={ident.user_id}",
        f"scope: app_id={ident.app_id} project_id={ident.project_id}",
    ]
    try:
        for mtype, label in ((MEMORY_TYPE_PROFILE, "画像"), (MEMORY_TYPE_EPISODE, "情景")):
            data = await plugin.client.get(
                memory_type=mtype,
                user_id=ident.user_id,
                app_id=ident.app_id,
                project_id=ident.project_id,
                page=1,
                page_size=1,
            )
            lines.append(f"{label}: {data.get('total_count', 0)} 条")
    except EverOSUnavailable as e:
        lines.append(f"（记忆计数获取失败: {e}）")
    yield event.plain_result("\n".join(lines))


async def search_impl(plugin, event: AstrMessageEvent, query: str):
    """/epk search <query>：按当前用户检索并展示命中（调试/自查用）。"""
    if not query:
        yield event.plain_result("用法：/epk search <要查询的内容>")
        return
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} 无法解析身份，跳过检索。")
        return
    if not await plugin._healthy():
        yield event.plain_result(f"{LOG_PREFIX} EverOS 未连接。")
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
        yield event.plain_result(f"{LOG_PREFIX} 检索失败: {e}")
        return
    profiles = data.get("profiles", []) or []
    episodes = data.get("episodes", []) or []
    lines = [f"{LOG_PREFIX} 检索结果（user_id={ident.user_id}）："]
    lines.append(f"画像 {len(profiles)} 条 / 情景 {len(episodes)} 条")
    for i, ep in enumerate(episodes[:5], 1):
        summary = ep.get("summary") or ep.get("subject") or "(无摘要)"
        score = ep.get("score")
        lines.append(f"{i}. [{score}] {str(summary)[:80]}")
    yield event.plain_result("\n".join(lines))


async def flush_impl(plugin, event: AstrMessageEvent):
    """/epk flush：手动 flush 当前会话（manual 策略下的主触发）。"""
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} 无法解析身份。")
        return
    if not await plugin._healthy():
        yield event.plain_result(f"{LOG_PREFIX} EverOS 未连接。")
        return
    try:
        data = await plugin.client.flush(ident.session_id, ident.app_id, ident.project_id)
        if plugin._flush_policy:
            plugin._flush_policy.discard(ident.session_id)
        yield event.plain_result(f"{LOG_PREFIX} flush 完成，status={data.get('status', '?')}")
    except EverOSUnavailable as e:
        yield event.plain_result(f"{LOG_PREFIX} flush 失败: {e}")


async def forget_impl(plugin, event: AstrMessageEvent, confirm: str | None = None):
    """[管理员] /epk forget [confirm]：删除当前用户记忆。

    ⚠️ 诚实边界（05 §三#5）：EverOS v1 API 仅 add/flush/get/search 四个端点，
    无删除端点（已核对 docs/openapi.json）。故本命令无法经 API 删除记忆，
    只能如实告知正确做法：EverOS 记忆是磁盘上的 markdown，删除需在 EverOS 侧操作。
    """
    yield event.plain_result(
        f"{LOG_PREFIX} EverOS v1 API 无删除端点，插件无法代为删除记忆。\n"
        "EverOS 的记忆以 markdown 存于数据目录（默认 ~/.everos 或容器 /data/everos），"
        "如需删除请在 EverOS 侧删除对应 user 目录的 md 文件后，重建索引（.index/ 可重建）。\n"
        "详见 EverOS 官方 storage_layout 文档。"
    )


async def quality_impl(plugin, event: AstrMessageEvent):
    """/epk quality：抽查当前用户画像的提取质量（规则校验，无 LLM）。"""
    ident = identity_mod.resolve(event, plugin.config)
    if ident is None:
        yield event.plain_result(f"{LOG_PREFIX} 无法解析身份。")
        return
    if not await plugin._healthy():
        yield event.plain_result(f"{LOG_PREFIX} EverOS 未连接。")
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
        yield event.plain_result(f"{LOG_PREFIX} 画像获取失败: {e}")
        return
    profiles = data.get("profiles", []) or []
    if not profiles:
        yield event.plain_result(
            f"{LOG_PREFIX} 当前用户（user_id={ident.user_id}）尚无画像，多聊几轮后再查。"
        )
        return
    report = profile_quality.check_profile(profiles[0])
    yield event.plain_result(
        f"{LOG_PREFIX} 画像质量抽查（user_id={ident.user_id}）：\n"
        + profile_quality.format_report(report)
    )


async def help_impl(plugin, event: AstrMessageEvent):
    """/epk help：列出本插件真实存在的命令（与代码强一致，05 §三#5）。"""
    yield event.plain_result(
        f"{LOG_PREFIX} ReadingSteiner 记忆插件命令：\n"
        "/epk flush         手动归档当前会话（所有人）\n"
        "/epk help          显示本帮助（所有人）\n"
        "—— 以下需管理员权限 ——\n"
        "/epk status        查看连接状态、当前身份与记忆计数\n"
        "/epk search <内容>  按当前用户检索记忆（调试用）\n"
        "/epk quality       抽查当前用户画像的提取质量\n"
        "/epk forget        记忆删除说明（API 不支持，见提示）"
    )
