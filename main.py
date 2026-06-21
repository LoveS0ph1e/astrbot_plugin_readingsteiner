"""astrbot_plugin_readingsteiner —— 基于 EverOS 的 AstrBot 长期记忆插件。

main 只做钩子/命令的绑定与异常兜底，不写业务逻辑。
业务在 core/*；EverOS 故障一律 try/except 降级，绝不阻断对话。
"""

from __future__ import annotations

import asyncio
import contextlib

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, register

from .commands import handlers
from .core import archiving, injection, visibility
from .core import identity as identity_mod
from .core.constants import (
    ARCHIVE_AUTO,
    DEFAULT_BASE_URL,
    DEFAULT_PROJECT_ID,
    INJECT_TARGET_USER,
    LOG_PREFIX,
)
from .core.everos_client import EverOSClient, EverOSUnavailable


@register(
    "astrbot_plugin_readingsteiner",
    "Sethyrial",
    "基于 EverOS 自进化记忆引擎的长期记忆插件（持久画像 + 按身份硬隔离）",
    "v0.2.0",
    "https://github.com/LoveS0ph1e/astrbot_plugin_readingsteiner",
)
class ReadingSteinerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self.client: EverOSClient | None = None
        self._flush_policy: archiving.FlushPolicy | None = None
        self._bg_task: asyncio.Task | None = None
        self._everos_up: bool | None = None  # 健康状态;None=首次未探测，用于跳变告警节流

    # ────────────────── 生命周期 ──────────────────

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        """AstrBot 就绪后初始化 client 与 auto-flush 后台任务（健康探测惰性化）。"""
        try:
            self.client = EverOSClient(
                self.config.get("everos_base_url", DEFAULT_BASE_URL),
                float(self.config.get("request_timeout", 30)),
            )
            self._flush_policy = archiving.FlushPolicy(
                self.config.get("archive_strategy", ARCHIVE_AUTO),
                int(self.config.get("flush_idle_seconds", 1800)),
                int(self.config.get("flush_every_n_turns", 0)),
            )
            ok = await self._healthy()
            state = "已连接" if ok else "暂不可达（将惰性重试）"
            logger.info(f"{LOG_PREFIX} 初始化完成，EverOS {state}")
            if self._flush_policy.strategy == ARCHIVE_AUTO:
                self._bg_task = asyncio.create_task(self._auto_flush_loop())
        except Exception as e:
            logger.error(f"{LOG_PREFIX} 初始化失败: {e}", exc_info=True)

    async def terminate(self):
        """卸载/停用时关 client、取消后台任务。"""
        if self._bg_task:
            self._bg_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._bg_task
        if self.client:
            await self.client.close()
        logger.info(f"{LOG_PREFIX} 已停止，资源已释放")

    async def _healthy(self) -> bool:
        """惰性健康探测：任何异常视为不健康（容器晚起也能自愈）。

        健康状态发生跳变时各打一次日志（持续同态不刷屏）：
        可达→不可达打 WARNING（长期记忆降级），不可达→可达打 INFO（恢复）。
        """
        if self.client is None:
            return False
        try:
            ok = await self.client.health()
        except EverOSUnavailable:
            ok = False
        self._note_health(ok)
        return ok

    def _note_health(self, ok: bool) -> None:
        """记录健康跳变并节流告警；首次（None）静默，由 on_loaded 负责首条日志。"""
        if self._everos_up is None:
            self._everos_up = ok
            return
        if ok == self._everos_up:
            return
        self._everos_up = ok
        if ok:
            logger.info(f"{LOG_PREFIX} EverOS 已恢复，长期记忆功能重新启用")
        else:
            logger.warning(
                f"{LOG_PREFIX} EverOS 不可达，本轮起跳过记忆注入与归档（对话不受影响，将惰性重试）"
            )

    async def _auto_flush_loop(self):
        """auto 策略后台任务：周期性 flush 静默超时的会话。"""
        interval = max(30, int(self.config.get("flush_idle_seconds", 300)) // 2)
        while True:
            await asyncio.sleep(interval)
            try:
                if self._flush_policy is None or self.client is None:
                    continue
                for sid in self._flush_policy.idle_sessions():
                    with contextlib.suppress(EverOSUnavailable):
                        await self.client.flush(
                            sid,
                            self.config.get("app_id", "astrbot"),
                            self.config.get("project_id", DEFAULT_PROJECT_ID),
                        )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} auto-flush 循环异常: {e}")

    # ────────────────── 开关/会话白名单 ──────────────────

    def _session_enabled(self, event: AstrMessageEvent) -> bool:
        """会话白名单：留空=全部启用；否则按 unified_msg_origin 子串匹配。"""
        raw = self.config.get("enabled_sessions", "")
        if not raw:
            return True
        umo = str(event.unified_msg_origin)
        return any(s.strip() and s.strip() in umo for s in str(raw).split(","))

    # ────────────────── LLM 钩子 ──────────────────

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """LLM 请求前：检索当前用户记忆并注入。"""
        try:
            if not self.config.get("enable_injection", True):
                return
            if not self._session_enabled(event):
                return
            ident = identity_mod.resolve(event, self.config)
            if ident is None:  # 铁律 2：无身份则跳过
                return
            if not await self._healthy():  # EverOS 不可达则跳过
                return
            data = await self.client.search(
                query=req.prompt if isinstance(req.prompt, str) else "",
                user_id=ident.user_id,  # 铁律 1/3：单一真实 QQ 号
                app_id=ident.app_id,
                project_id=ident.project_id,
                method=self.config.get("search_method", "hybrid"),
                top_k=int(self.config.get("search_top_k", 5)),
                include_profile=self.config.get("include_profile", True),
            )
            profiles = data.get("profiles", []) or []
            episodes = data.get("episodes", []) or []
            if self.config.get("group_public_only", True) and ident.is_group:
                profiles, episodes = visibility.filter_public(profiles, episodes)
            text = injection.build_text(profiles, episodes, self.config)
            injection.inject(
                req,
                text,
                self.config.get("injection_target", INJECT_TARGET_USER),
                self.config.get("injection_position", "prepend"),
            )
        except Exception as e:
            logger.error(f"{LOG_PREFIX} on_llm_request 失败: {e}", exc_info=True)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """LLM 响应后：归档本轮对话。"""
        try:
            if not self.config.get("enable_archiving", True):
                return
            if not self._session_enabled(event):
                return
            ident = identity_mod.resolve(event, self.config)
            if ident is None:
                return
            if not await self._healthy():
                return
            user_text = event.message_str or ""
            assistant_text = resp.completion_text or ""
            if not user_text and not assistant_text:
                return
            msgs = archiving.build_messages(user_text, assistant_text, ident)
            await self.client.add(ident.session_id, msgs, ident.app_id, ident.project_id)
            self._flush_policy.mark_active(ident.session_id)
            if self._flush_policy.should_flush_now(ident.session_id):
                await self.client.flush(ident.session_id, ident.app_id, ident.project_id)
        except Exception as e:
            logger.error(f"{LOG_PREFIX} on_llm_response 失败: {e}", exc_info=True)

    # ────────────────── /epk 命令组 ──────────────────
    # /epk = El Psy Kongroo 缩写
    # 范式：Mnemosyne/main.py:642-741（command_group + impl 代理 + permission_type + confirm）

    @filter.command_group("epk")
    def epk_group(self):
        """EverOS 长期记忆管理命令组 /epk（El Psy Kongroo）"""
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @epk_group.command("status")  # type: ignore
    async def epk_status(self, event: AstrMessageEvent):
        """[管理员] 查看 EverOS 连接状态、当前身份与记忆计数"""
        async for r in handlers.status_impl(self, event):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @epk_group.command("search")  # type: ignore
    async def epk_search(self, event: AstrMessageEvent, query: str = ""):
        """[管理员] 按当前用户检索记忆 /epk search <内容>"""
        async for r in handlers.search_impl(self, event, query):
            yield r

    @epk_group.command("flush")  # type: ignore
    async def epk_flush(self, event: AstrMessageEvent):
        """手动归档当前会话 /epk flush"""
        async for r in handlers.flush_impl(self, event):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @epk_group.command("quality")  # type: ignore
    async def epk_quality(self, event: AstrMessageEvent):
        """[管理员] 抽查当前用户画像质量 /epk quality"""
        async for r in handlers.quality_impl(self, event):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @epk_group.command("forget")  # type: ignore
    async def epk_forget(self, event: AstrMessageEvent, confirm: str | None = None):
        """[管理员] 删除当前用户记忆 /epk forget [confirm]"""
        async for r in handlers.forget_impl(self, event, confirm):
            yield r

    @epk_group.command("help")  # type: ignore
    async def epk_help(self, event: AstrMessageEvent):
        """显示帮助 /epk help"""
        async for r in handlers.help_impl(self, event):
            yield r
