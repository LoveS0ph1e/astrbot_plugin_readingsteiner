"""/epk forget 命令逻辑测试（forget_impl）：子命令派发 + 身份隔离铁律。

forget_impl 是 async generator，逐条 yield event.plain_result(...)。
照 test_tools.py 的鸭子类型 Fake 范式；用真 ForgetStore(tmp_path) 注入。
"""

from __future__ import annotations

from astrbot_plugin_readingsteiner.commands.handlers import forget_impl
from astrbot_plugin_readingsteiner.core.forget import ForgetStore


class FakeEvent:
    def __init__(self, sender_id="10086", group_id="", self_id="bot", umo="qq:X:1"):
        self._sender_id = sender_id
        self._group_id = group_id
        self._self_id = self_id
        self.unified_msg_origin = umo

    def get_sender_id(self):
        return self._sender_id

    def get_group_id(self):
        return self._group_id

    def get_self_id(self):
        return self._self_id

    def plain_result(self, text):
        return text  # 测试里直接拿回文本


class FakePlugin:
    def __init__(self, store, config=None):
        self.config = config if config is not None else {"enable_forget": True}
        self._forget_store = store


async def _collect(agen):
    return [r async for r in agen]


async def test_forget_cmd_no_args_lists_rules(tmp_path):
    store = ForgetStore(str(tmp_path))
    store.add_phrase("10086", "爬山")
    out = await _collect(forget_impl(FakePlugin(store), FakeEvent(sender_id="10086"), ""))
    assert len(out) == 1 and isinstance(out[0], str)
    assert "爬山" in out[0]
    assert store.get("10086").phrases == ("爬山",)  # 无参不改 store


async def test_forget_cmd_all_sets_optout(tmp_path):
    store = ForgetStore(str(tmp_path))
    out = await _collect(forget_impl(FakePlugin(store), FakeEvent(sender_id="10086"), "all"))
    assert out and isinstance(out[0], str)
    assert store.get("10086").forget_all is True


async def test_forget_cmd_clear(tmp_path):
    store = ForgetStore(str(tmp_path))
    store.set_forget_all("10086", True)
    await _collect(forget_impl(FakePlugin(store), FakeEvent(sender_id="10086"), "clear"))
    assert store.get("10086") is None


async def test_forget_cmd_phrase_added(tmp_path):
    store = ForgetStore(str(tmp_path))
    await _collect(forget_impl(FakePlugin(store), FakeEvent(sender_id="10086"), "爬山"))
    assert store.get("10086").phrases == ("爬山",)


async def test_forget_cmd_phrase_too_short(tmp_path):
    store = ForgetStore(str(tmp_path))
    out = await _collect(forget_impl(FakePlugin(store), FakeEvent(sender_id="10086"), "猫"))
    assert out and "short" in out[0].lower()
    assert store.get("10086") is None  # 没入库


async def test_forget_cmd_disabled_by_config(tmp_path):
    store = ForgetStore(str(tmp_path))
    plugin = FakePlugin(store, config={"enable_forget": False})
    out = await _collect(forget_impl(plugin, FakeEvent(sender_id="10086"), "爬山"))
    assert out and "disabled" in out[0].lower()
    assert store.get("10086") is None  # 配置关闭则不写


async def test_forget_cmd_unavailable_when_store_none():
    plugin = FakePlugin(None)
    out = await _collect(forget_impl(plugin, FakeEvent(), "爬山"))
    assert out and isinstance(out[0], str)  # 友好提示，不抛


async def test_forget_cmd_uses_event_identity(tmp_path):
    """铁律：作用的 user_id == event.get_sender_id()，与 args 无关。"""
    store = ForgetStore(str(tmp_path))
    await _collect(forget_impl(FakePlugin(store), FakeEvent(sender_id="55555"), "爬山"))
    assert store.get("55555").phrases == ("爬山",)
    assert store.get("10086") is None  # 没写到别的 user
