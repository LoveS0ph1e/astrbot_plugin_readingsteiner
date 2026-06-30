"""EverOSClient 契约测试：用 respx mock httpx，不依赖活引擎（01 第二部分契约）。

验证点：POST 路径正确、payload 字段、响应取 data、error 包络抛异常、
user_id/agent_id XOR 守卫、health 多格式兼容。
"""

from __future__ import annotations

import httpx
import pytest
import respx

from core.everos_client import EverOSClient, EverOSUnavailable

BASE = "http://everos-test:8000"


def _envelope(data: dict) -> dict:
    return {"request_id": "rid", "data": data}


def _error(code: str | None = None, message: str = "boom") -> dict:
    err: dict = {"message": message}
    if code is not None:
        err["code"] = code
    return {"request_id": "r", "error": err}


@pytest.fixture
async def client():
    c = EverOSClient(BASE, timeout=5.0)
    yield c
    await c.close()


@respx.mock
async def test_health_ok_status(client):
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    assert await client.health() is True


@respx.mock
async def test_health_healthy_status(client):
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"status": "healthy"}))
    assert await client.health() is True


@respx.mock
async def test_health_down_returns_false(client):
    respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("refused"))
    assert await client.health() is False


@respx.mock
async def test_add_unpacks_data(client):
    route = respx.post(f"{BASE}/api/v1/memory/add").mock(
        return_value=httpx.Response(
            200, json=_envelope({"message_count": 2, "status": "accumulated"})
        )
    )
    msgs = [{"sender_id": "10086", "role": "user", "timestamp": 1, "content": "hi"}]
    data = await client.add("sess", msgs, "app", "proj")
    assert data == {"message_count": 2, "status": "accumulated"}
    sent = route.calls.last.request
    assert b'"session_id":"sess"' in sent.content.replace(b" ", b"")


@respx.mock
async def test_error_envelope_raises(client):
    respx.post(f"{BASE}/api/v1/memory/flush").mock(
        return_value=httpx.Response(200, json={"request_id": "r", "error": {"message": "boom"}})
    )
    with pytest.raises(EverOSUnavailable, match="boom"):
        await client.flush("sess")


@respx.mock
async def test_http_500_raises_unavailable(client):
    respx.post(f"{BASE}/api/v1/memory/flush").mock(return_value=httpx.Response(500))
    with pytest.raises(EverOSUnavailable):
        await client.flush("sess")


@respx.mock
async def test_search_sends_user_id_and_include_profile(client):
    route = respx.post(f"{BASE}/api/v1/memory/search").mock(
        return_value=httpx.Response(200, json=_envelope({"episodes": [], "profiles": []}))
    )
    await client.search(query="q", user_id="10086", include_profile=True)
    body = route.calls.last.request.content.replace(b" ", b"")
    assert b'"user_id":"10086"' in body
    assert b'"include_profile":true' in body
    assert b'"agent_id"' not in body  # 只传 user_id，不夹带 agent_id


async def test_search_requires_exactly_one_subject(client):
    """user_id/agent_id 必须恰好一个：都缺 / 都给 都本地抛错（不往返）。"""
    with pytest.raises(EverOSUnavailable):
        await client.search(query="q")  # 都没给
    with pytest.raises(EverOSUnavailable):
        await client.search(query="q", user_id="a", agent_id="b")  # 都给


async def test_get_requires_exactly_one_subject(client):
    with pytest.raises(EverOSUnavailable):
        await client.get(memory_type="profile")  # 都没给


@respx.mock
async def test_get_unpacks_data(client):
    respx.post(f"{BASE}/api/v1/memory/get").mock(
        return_value=httpx.Response(
            200, json=_envelope({"profiles": [], "total_count": 0, "count": 0})
        )
    )
    data = await client.get(memory_type="profile", user_id="10086")
    assert data["total_count"] == 0


# ── EverOS 1.1.0 typed error.code 分级 ──


@respx.mock
async def test_error_code_retryable_classified(client):
    """503 + EXTERNAL_SERVICE_UNAVAILABLE → code/status 解析正确、retryable=True。"""
    respx.post(f"{BASE}/api/v1/memory/search").mock(
        return_value=httpx.Response(503, json=_error("EXTERNAL_SERVICE_UNAVAILABLE", "llm down"))
    )
    with pytest.raises(EverOSUnavailable) as ei:
        await client.search(query="q", user_id="u")
    assert ei.value.code == "EXTERNAL_SERVICE_UNAVAILABLE"
    assert ei.value.status == 503
    assert ei.value.retryable is True


@respx.mock
async def test_error_code_permanent_not_found(client):
    """404 + NOT_FOUND → 永久错（不可重试）。"""
    respx.post(f"{BASE}/api/v1/memory/get").mock(
        return_value=httpx.Response(404, json=_error("NOT_FOUND", "nope"))
    )
    with pytest.raises(EverOSUnavailable) as ei:
        await client.get(memory_type="profile", user_id="u")
    assert ei.value.code == "NOT_FOUND"
    assert ei.value.status == 404
    assert ei.value.retryable is False


@respx.mock
async def test_legacy_error_envelope_no_code(client):
    """1.0.x 老包络（error 仅 message、无 code）→ code None、不可重试，仍抛且保留文案。"""
    respx.post(f"{BASE}/api/v1/memory/flush").mock(
        return_value=httpx.Response(200, json=_error(message="legacy boom"))
    )
    with pytest.raises(EverOSUnavailable) as ei:
        await client.flush("sess")
    assert ei.value.code is None
    assert ei.value.retryable is False
    assert "legacy boom" in str(ei.value)


@respx.mock
async def test_retry_on_retryable_then_success():
    """retry_retryable=1：首个 retryable 503 重试一次，第二次成功取 data。"""
    route = respx.post(f"{BASE}/api/v1/memory/search").mock(
        side_effect=[
            httpx.Response(503, json=_error("EXTERNAL_SERVICE_UNAVAILABLE")),
            httpx.Response(200, json=_envelope({"episodes": [], "profiles": []})),
        ]
    )
    c = EverOSClient(BASE, timeout=5.0, retry_retryable=1, retry_backoff=0.0)
    try:
        data = await c.search(query="q", user_id="u")
    finally:
        await c.close()
    assert data == {"episodes": [], "profiles": []}
    assert route.call_count == 2


@respx.mock
async def test_no_retry_on_permanent():
    """永久错（404 NOT_FOUND）即便配了重试也只发一次。"""
    route = respx.post(f"{BASE}/api/v1/memory/get").mock(
        return_value=httpx.Response(404, json=_error("NOT_FOUND"))
    )
    c = EverOSClient(BASE, timeout=5.0, retry_retryable=2, retry_backoff=0.0)
    try:
        with pytest.raises(EverOSUnavailable):
            await c.get(memory_type="profile", user_id="u")
    finally:
        await c.close()
    assert route.call_count == 1


@respx.mock
async def test_search_returns_episode_id_verbatim(client):
    """1.1.0 暴露的 episode id 原样透传到 data（无需管线改造，真擦除时可直接取用）。"""
    ep = {"id": "u_ep_20260528_00000001", "summary": "s", "score": 0.9}
    respx.post(f"{BASE}/api/v1/memory/search").mock(
        return_value=httpx.Response(200, json=_envelope({"episodes": [ep], "profiles": []}))
    )
    data = await client.search(query="q", user_id="u")
    assert data["episodes"][0]["id"] == "u_ep_20260528_00000001"


# ── OME trigger（Reflection） ──


@respx.mock
async def test_trigger_ome_posts_and_unpacks(client):
    route = respx.post(f"{BASE}/api/v1/ome/trigger").mock(
        return_value=httpx.Response(
            200, json=_envelope({"status": "ok", "name": "reflect_episodes"})
        )
    )
    data = await client.trigger_ome("reflect_episodes", force=True)
    assert data == {"status": "ok", "name": "reflect_episodes"}
    body = route.calls.last.request.content.replace(b" ", b"")
    assert b'"name":"reflect_episodes"' in body
    assert b'"force":true' in body


@respx.mock
async def test_trigger_ome_not_found_raises(client):
    """EverOS<1.1.0 无该策略 → NOT_FOUND（命令层据此提示需升级）。"""
    route = respx.post(f"{BASE}/api/v1/ome/trigger").mock(
        return_value=httpx.Response(404, json=_error("NOT_FOUND", "strategy not found"))
    )
    with pytest.raises(EverOSUnavailable) as ei:
        await client.trigger_ome("reflect_episodes")
    assert ei.value.code == "NOT_FOUND"
    assert route.call_count == 1


@respx.mock
async def test_trigger_ome_no_retry_even_when_retryable():
    """trigger_ome 走 _post_once：即便配了重试且遇 retryable，也只发一次（不重复触发重型合并）。"""
    route = respx.post(f"{BASE}/api/v1/ome/trigger").mock(
        return_value=httpx.Response(503, json=_error("EXTERNAL_SERVICE_UNAVAILABLE"))
    )
    c = EverOSClient(BASE, timeout=5.0, retry_retryable=2, retry_backoff=0.0)
    try:
        with pytest.raises(EverOSUnavailable) as ei:
            await c.trigger_ome("reflect_episodes")
    finally:
        await c.close()
    assert ei.value.retryable is True
    assert route.call_count == 1
