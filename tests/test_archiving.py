"""归档逻辑测试（archiving.py）：消息构造 + flush 策略，纯逻辑无网络。"""

from __future__ import annotations

from core.archiving import FlushPolicy, build_messages
from core.identity import Identity


def _ident():
    return Identity("10086", "umo", "astrbot", "default", False, "bot01")


def test_build_messages_shape():
    m = build_messages("用户原话", "机器人回复", _ident(), now_ms=1700000000000)
    assert len(m) == 2
    assert m[0] == {
        "sender_id": "10086",
        "role": "user",
        "timestamp": 1700000000000,
        "content": "用户原话",
    }
    assert m[1]["sender_id"] == "bot01"
    assert m[1]["role"] == "assistant"
    assert m[1]["timestamp"] == 1700000000001  # assistant 晚 1ms 保序


def test_user_sender_id_is_qq():
    """user 消息 sender_id 必须是 QQ 号（EverOS 索引键）。"""
    m = build_messages("a", "b", _ident())
    assert m[0]["sender_id"] == "10086"


def test_every_turn_flushes_now():
    assert FlushPolicy("every_turn", 300).should_flush_now("s") is True


def test_auto_does_not_flush_now():
    assert FlushPolicy("auto", 300).should_flush_now("s") is False


def test_auto_idle_after_timeout():
    clk = {"t": 0.0}
    fp = FlushPolicy("auto", 300, clock=lambda: clk["t"])
    fp.mark_active("s1")
    clk["t"] = 299
    assert fp.idle_sessions() == []  # 未到阈值
    clk["t"] = 300
    assert fp.idle_sessions() == ["s1"]  # 到阈值
    assert fp.idle_sessions() == []  # 取出后已移除


def test_manual_never_idle():
    fp = FlushPolicy("manual", 1, clock=lambda: 9999)
    fp.mark_active("s1")
    assert fp.idle_sessions() == []  # 非 auto 恒空
