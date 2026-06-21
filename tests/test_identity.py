"""身份解析回归测试：守住三条铁律（identity.py），防跨用户串线。

不依赖 AstrBot：用鸭子类型的 FakeEvent 喂 resolve。
"""

from __future__ import annotations

from core.identity import resolve


class FakeEvent:
    """最小 mock event：只实现 resolve 用到的方法/属性。"""

    def __init__(self, sender_id="", group_id="", self_id="bot", umo="qq:X:1", **extra):
        self._sender_id = sender_id
        self._group_id = group_id
        self._self_id = self_id
        self.unified_msg_origin = umo
        for k, v in extra.items():
            setattr(self, k, v)

    def get_sender_id(self):
        return self._sender_id

    def get_group_id(self):
        return self._group_id

    def get_self_id(self):
        return self._self_id


def test_user_id_from_real_sender():
    """铁律1：user_id 必须来自真实发送者。"""
    ident = resolve(FakeEvent(sender_id="10086"), {"app_id": "a", "project_id": "p"})
    assert ident is not None
    assert ident.user_id == "10086"
    assert ident.app_id == "a"
    assert ident.project_id == "p"


def test_no_sender_returns_none():
    """铁律2：取不到 user_id 返回 None，绝不回退 default。"""
    assert resolve(FakeEvent(sender_id=""), None) is None


def test_no_default_fallback_ever():
    """铁律2 强化：空发送者下结果不得包含 'default' 作为 user_id。"""
    assert resolve(FakeEvent(sender_id=""), {"app_id": "default"}) is None


def test_private_vs_group():
    """私聊 is_group=False；群聊 is_group=True。"""
    assert resolve(FakeEvent(sender_id="1"), None).is_group is False
    assert resolve(FakeEvent(sender_id="1", group_id="999"), None).is_group is True


def test_two_users_never_collide():
    """两个不同发送者解析出的 user_id 必须不同（串线回归核心）。"""
    a = resolve(FakeEvent(sender_id="111", group_id="G"), None)
    b = resolve(FakeEvent(sender_id="222", group_id="G"), None)
    assert a.user_id == "111"
    assert b.user_id == "222"
    assert a.user_id != b.user_id


def test_persona_isolation_app_id():
    """白名单内人格 → app_id 加后缀；白名单外 → 共享 base。"""
    cfg_in = {"app_id": "bot", "isolation_personas": "凤凰院凶真", "project_id": "default"}
    e = FakeEvent(sender_id="1", persona_name="凤凰院凶真")
    assert resolve(e, cfg_in).app_id == "bot_凤凰院凶真"
    e2 = FakeEvent(sender_id="1", persona_name="路人")
    assert resolve(e2, cfg_in).app_id == "bot"


def test_no_whitelist_skips_persona():
    """白名单为空（默认）→ 永远共享 base，不查人格。"""
    e = FakeEvent(sender_id="1", persona_name="任意")
    assert resolve(e, {"app_id": "bot"}).app_id == "bot"
