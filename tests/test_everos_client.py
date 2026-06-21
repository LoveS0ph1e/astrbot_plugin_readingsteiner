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
    respx.get(f"{BASE}/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy"})
    )
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
