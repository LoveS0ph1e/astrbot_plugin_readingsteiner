"""归档：event+response → EverOS add/flush。出处：02 §3.2 / §3.3。

两件事：
1. build_messages：构造 user+assistant 两条 MessageItem。
   ⚠️ timestamp = Unix 毫秒 int（01 §2.2）；user 的 sender_id = QQ 号（索引键）。
2. FlushPolicy：auto / every_turn / manual 三策略。
   - every_turn：每轮 add 后立即 flush（实时高、LLM 成本高）。
   - manual：只 add，靠 /epk flush 手动触发。
   - auto（默认）：只 add，记录会话活动时间，由后台任务在静默超时后 flush。

本模块不改 req（分层不串味，05 §三）。time 用 monotonic 记活动，避免系统时钟回拨误判。
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
    """构造两条 MessageItem（01 §2.2）。

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
    """auto/every_turn/manual 三策略（02 §3.3）。

    auto 记录每个 session 的最后活动时刻（monotonic 秒），后台任务调 idle_sessions()
    取出静默超过 idle_seconds 的 session 去 flush。
    """

    def __init__(self, strategy: str, idle_seconds: int, *, clock=None) -> None:
        self.strategy = strategy
        self.idle_seconds = idle_seconds
        self._clock = clock or time.monotonic
        self._last_active: dict[str, float] = {}

    def mark_active(self, session_id: str) -> None:
        """记录会话活动时刻。每次 add 后调用。"""
        self._last_active[session_id] = self._clock()

    def should_flush_now(self, session_id: str) -> bool:
        """归档后是否立即 flush：every_turn→True；auto/manual→False。"""
        return self.strategy == ARCHIVE_EVERY_TURN

    def idle_sessions(self) -> list[str]:
        """auto 后台任务用：返回静默超过 idle_seconds 的 session，并从跟踪表移除。

        非 auto 策略恒返回空（后台任务无事可做）。
        """
        if self.strategy != ARCHIVE_AUTO:
            return []
        now = self._clock()
        idle = [
            sid
            for sid, last in self._last_active.items()
            if now - last >= self.idle_seconds
        ]
        for sid in idle:
            self._last_active.pop(sid, None)
        return idle

    def discard(self, session_id: str) -> None:
        """显式丢弃某会话的活动记录（如手动 flush 后）。"""
        self._last_active.pop(session_id, None)
