"""归档：event+response → EverOS add/flush。

两件事：
1. build_messages：构造 user+assistant 两条 MessageItem。
   ⚠️ timestamp = Unix 毫秒 int；user 的 sender_id = QQ 号（索引键）。
2. FlushPolicy：auto / every_turn / manual 三策略。
   - every_turn：每轮 add 后立即 flush（实时高、LLM 成本高）。
   - manual：只 add，靠 /epk flush 手动触发。
   - auto（默认）：双触发，谁先到谁 flush——
       · 轮数触发：累积 every_n_turns 轮即 flush（长聊及时固化，0=禁用）；
       · 静默兜底：后台任务在静默超 idle_seconds 后 flush（停聊收尾）。
     底层 EverOS 边界检测决定是否真正提取（未到语义边界则只 accumulate，成本低）。

本模块不改 req（分层不串味）。time 用 monotonic 记活动，避免系统时钟回拨误判。
"""

from __future__ import annotations

import time

from .constants import (
    ARCHIVE_AUTO,
    ARCHIVE_EVERY_TURN,
    ASSISTANT_SENDER_ID,
)
from .identity import Identity


def build_messages(
    user_text: str,
    assistant_text: str,
    identity: Identity,
    now_ms: int | None = None,
) -> list[dict]:
    """构造两条 MessageItem。

    now_ms 可注入以便单测；默认取当前 Unix 毫秒。assistant 比 user 晚 1ms 保序。
    """
    base = now_ms if now_ms is not None else int(time.time() * 1000)
    return [
        {
            "sender_id": identity.user_id,
            "role": "user",
            "timestamp": base,
            "content": user_text,
        },
        {
            "sender_id": identity.bot_id or ASSISTANT_SENDER_ID,
            "role": "assistant",
            "timestamp": base + 1,
            "content": assistant_text,
        },
    ]


class FlushPolicy:
    """auto/every_turn/manual 三策略。

    auto 为双触发：mark_active 累加每会话轮数计数并记录最后活动时刻（monotonic 秒）；
    should_flush_now 在轮数达 every_n_turns 时立即触发（并清零计数）；
    idle_sessions 供后台任务取静默超 idle_seconds 的会话做兜底 flush。
    """

    def __init__(
        self,
        strategy: str,
        idle_seconds: int,
        every_n_turns: int = 0,
        *,
        clock=None,
    ) -> None:
        self.strategy = strategy
        self.idle_seconds = idle_seconds
        self.every_n_turns = max(0, every_n_turns)  # 0=禁用轮数触发
        self._clock = clock or time.monotonic
        self._last_active: dict[str, float] = {}
        self._turns: dict[str, int] = {}

    def mark_active(self, session_id: str) -> None:
        """记录会话活动时刻并累加轮数。每次 add 后调用。"""
        self._last_active[session_id] = self._clock()
        self._turns[session_id] = self._turns.get(session_id, 0) + 1

    def should_flush_now(self, session_id: str) -> bool:
        """归档后是否立即 flush。

        every_turn→恒 True；auto→轮数达阈值时 True（并清零计数）；manual→False。
        """
        if self.strategy == ARCHIVE_EVERY_TURN:
            return True
        if (
            self.strategy == ARCHIVE_AUTO
            and self.every_n_turns > 0
            and self._turns.get(session_id, 0) >= self.every_n_turns
        ):
            self.discard(session_id)  # 清零轮数与活动记录，避免后台重复 flush
            return True
        return False

    def idle_sessions(self) -> list[str]:
        """auto 后台任务用：返回静默超过 idle_seconds 的 session，并从跟踪表移除。

        非 auto 策略恒返回空（后台任务无事可做）。
        """
        if self.strategy != ARCHIVE_AUTO:
            return []
        now = self._clock()
        idle = [sid for sid, last in self._last_active.items() if now - last >= self.idle_seconds]
        for sid in idle:
            self.discard(sid)
        return idle

    def discard(self, session_id: str) -> None:
        """显式丢弃某会话的活动记录与轮数计数（flush 后调用）。"""
        self._last_active.pop(session_id, None)
        self._turns.pop(session_id, None)
