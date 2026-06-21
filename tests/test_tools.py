"""LLM 工具测试（recall_impl / remember_impl）：核心是身份隔离铁律。

最关键断言：模型即便试图传 user_id，也绝不被采纳——身份只从 event 解析。
不依赖 AstrBot：用鸭子类型的 FakePlugin / FakeClient / FakeEvent。
"""

from __future__ import annotations

from astrbot_plugin_readingsteiner.commands.handlers import recall_impl, remember_impl


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


class FakeClient:
    """记录最后一次调用参数，供断言。"""

    def __init__(self, search_ret=None):
        self.search_ret = search_ret or {"profiles": [], "episodes": []}
        self.search_kwargs = None
        self.add_args = None

    async def search(self, **kwargs):
        self.search_kwargs = kwargs
        return self.search_ret

    async def add(self, session_id, messages, app_id, project_id):
        self.add_args = {
            "session_id": session_id,
            "messages": messages,
            "app_id": app_id,
            "project_id": project_id,
        }
        return {"status": "accumulated"}


class FakeFlushPolicy:
    def __init__(self):
        self.marked = []

    def mark_active(self, sid):
        self.marked.append(sid)


class FakePlugin:
    def __init__(self, config=None, client=None, healthy=True):
        self.config = config if config is not None else {"enable_llm_tools": True}
        self.client = client or FakeClient()
        self._flush_policy = FakeFlushPolicy()
        self._healthy_ret = healthy

    async def _healthy(self):
        return self._healthy_ret


async def test_recall_disabled_returns_message():
    plugin = FakePlugin(config={"enable_llm_tools": False})
    ret = await recall_impl(plugin, FakeEvent(), "anything")
    assert isinstance(ret, str) and ret  # 非空字符串，绝不返回 None


async def test_recall_uses_event_identity_not_model_input():
    """铁律：recall 的 user_id 必须是 event 发送者，与任何模型输入无关。"""
    ret = {"profiles": [{"profile_data": {"summary": "x"}}], "episodes": []}
    client = FakeClient(search_ret=ret)
    plugin = FakePlugin(config={"enable_llm_tools": True}, client=client)
    await recall_impl(plugin, FakeEvent(sender_id="10086"), "what do I like")
    assert client.search_kwargs["user_id"] == "10086"  # 来自 event，不可被模型覆盖


async def test_recall_unhealthy_returns_message():
    plugin = FakePlugin(config={"enable_llm_tools": True}, healthy=False)
    ret = await recall_impl(plugin, FakeEvent(), "q")
    assert isinstance(ret, str) and ret  # 不健康也返回非空说明，不返回 None


async def test_recall_empty_memory_returns_message():
    """空库新用户：必须返回非空说明，否则 AstrBot 会静默吞掉本轮回复。"""
    plugin = FakePlugin(config={"enable_llm_tools": True})  # 默认 FakeClient 返回空
    ret = await recall_impl(plugin, FakeEvent(sender_id="99999"), "who am I")
    assert isinstance(ret, str) and ret


async def test_remember_writes_with_event_identity():
    """铁律：remember 写入的 sender_id 是 event 发送者真实 ID。"""
    client = FakeClient()
    plugin = FakePlugin(config={"enable_llm_tools": True}, client=client)
    ret = await remember_impl(plugin, FakeEvent(sender_id="20086"), "我喜欢爬山")
    assert ret is not None
    assert client.add_args is not None
    # add 的 user 消息 sender_id 必须是真实发送者
    user_msg = client.add_args["messages"][0]
    assert user_msg["sender_id"] == "20086"
    assert "爬山" in user_msg["content"]


async def test_remember_disabled_returns_message():
    plugin = FakePlugin(config={"enable_llm_tools": False})
    ret = await remember_impl(plugin, FakeEvent(), "x")
    assert isinstance(ret, str) and ret


async def test_remember_empty_content_returns_message():
    plugin = FakePlugin(config={"enable_llm_tools": True})
    ret = await remember_impl(plugin, FakeEvent(), "   ")
    assert isinstance(ret, str) and ret
    assert plugin.client.add_args is None  # 空内容不写


async def test_remember_unhealthy_returns_message():
    plugin = FakePlugin(config={"enable_llm_tools": True}, healthy=False)
    ret = await remember_impl(plugin, FakeEvent(), "x")
    assert isinstance(ret, str) and ret
    assert plugin.client.add_args is None  # 不健康不写
