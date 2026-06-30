"""/epk reflect 命令逻辑测试（reflect_impl）：触发 OME reflect_episodes + 版本/健康降级。

reflect_impl 是 async generator，逐条 yield event.plain_result(...)。
照 test_forget_command.py 的鸭子类型 Fake 范式；不解析身份（服务端维护操作，跨用户）。
"""

from __future__ import annotations

from astrbot_plugin_readingsteiner.commands.handlers import reflect_impl
from astrbot_plugin_readingsteiner.core.constants import (
    ERR_NOT_FOUND,
    OME_STRATEGY_REFLECT_EPISODES,
)
from astrbot_plugin_readingsteiner.core.everos_client import EverOSUnavailable


class FakeEvent:
    def __init__(self, umo="qq:X:1"):
        self.unified_msg_origin = umo

    def plain_result(self, text):
        return text  # 测试里直接拿回文本


class FakeClient:
    def __init__(self, result=None, exc=None):
        self._result = result if result is not None else {}
        self._exc = exc
        self.calls: list[tuple[str, bool]] = []

    async def trigger_ome(self, name, *, timeout=120.0, force=False):
        self.calls.append((name, force))
        if self._exc is not None:
            raise self._exc
        return self._result


class FakePlugin:
    def __init__(self, client, healthy=True):
        self.client = client
        self._healthy_val = healthy
        self.config = {}

    async def _healthy(self):
        return self._healthy_val


async def _collect(agen):
    return [r async for r in agen]


async def test_reflect_triggers_and_reports_ok():
    client = FakeClient(result={"status": "ok", "name": "reflect_episodes"})
    out = await _collect(reflect_impl(FakePlugin(client), FakeEvent()))
    assert client.calls == [(OME_STRATEGY_REFLECT_EPISODES, True)]
    assert "ok" in "\n".join(out).lower()


async def test_reflect_timeout_reports_still_running():
    client = FakeClient(result={"status": "timeout", "name": "reflect_episodes"})
    out = await _collect(reflect_impl(FakePlugin(client), FakeEvent()))
    joined = "\n".join(out).lower()
    assert "running" in joined or "timeout" in joined


async def test_reflect_not_found_hints_version():
    client = FakeClient(exc=EverOSUnavailable("nope", code=ERR_NOT_FOUND, status=404))
    out = await _collect(reflect_impl(FakePlugin(client), FakeEvent()))
    joined = "\n".join(out)
    assert "1.1.0" in joined  # 友好提示需升级
    assert client.calls == [(OME_STRATEGY_REFLECT_EPISODES, True)]  # 触发过，错误来自服务端


async def test_reflect_bare_404_hints_version():
    """1.0.x 整条 /ome/trigger 路由缺失 → 裸 404（code=None）也应提示需升级（实测 1.0.1 行为）。"""
    client = FakeClient(exc=EverOSUnavailable("POST /api/v1/ome/trigger HTTP 404", status=404))
    out = await _collect(reflect_impl(FakePlugin(client), FakeEvent()))
    assert "1.1.0" in "\n".join(out)


async def test_reflect_other_error_reports_failure():
    client = FakeClient(exc=EverOSUnavailable("boom", code="INTERNAL_ERROR", status=500))
    out = await _collect(reflect_impl(FakePlugin(client), FakeEvent()))
    assert "failed" in "\n".join(out).lower()


async def test_reflect_skips_when_unhealthy():
    client = FakeClient(result={"status": "ok"})
    out = await _collect(reflect_impl(FakePlugin(client, healthy=False), FakeEvent()))
    assert client.calls == []  # EverOS 不可达则未触发
    assert "not connected" in "\n".join(out).lower()
