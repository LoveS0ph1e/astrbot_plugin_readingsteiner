"""EverOS REST API v1 异步客户端。

纯 HTTP 封装，输入输出皆 dict/原生类型，不依赖任何 AstrBot 类型
（便于脱离 AstrBot 单测，也便于其它项目复用，见 05-审计与迭代规约.md §二）。

契约出处：01-实证依据.md 第二部分。要点：
- 所有业务端点在 /api/v1/memory/ 下，全部 POST（即使语义像读，01 §2.1 头）
- 200 响应统一包络 {request_id, data:{...}}；错误 {request_id, error:{...}}（01 §2.1）
  → 解析一律先取 data；有 error 抛 EverOSUnavailable
- /health、/metrics 在 /api/v1 之外（01 §2.7）
"""
from __future__ import annotations

from typing import Any

import httpx

from .constants import (
    DEFAULT_APP_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_TIMEOUT,
    SEARCH_METHOD_HYBRID,
)


class EverOSUnavailable(Exception):
    """EverOS 不可达 / 请求失败 / 返回 error 包络。

    上层钩子捕获后降级（跳过记忆，不阻断对话，02 §六）。
    """


class EverOSClient:
    """EverOS HTTP v1 客户端。

    Args:
        base_url: 服务地址。同 docker 网络用 http://everos:8000；单机用 127.0.0.1:8000。
        timeout: 请求超时秒数。超时按『无记忆』降级。
    """

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """关闭底层 httpx client，供 terminate 调用。"""
        await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """统一 POST：发请求 → raise_for_status → 取 data。

        网络/HTTP 错误统一抛 EverOSUnavailable；error 包络也抛（01 §2.1）。
        """
        try:
            resp = await self._client.post(f"{self.base_url}{path}", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise EverOSUnavailable(f"POST {path} 失败: {e}") from e
        body = resp.json()
        if isinstance(body, dict) and "error" in body:
            err = body["error"]
            msg = err.get("message", "unknown") if isinstance(err, dict) else str(err)
            raise EverOSUnavailable(f"EverOS error @ {path}: {msg}")
        return body.get("data", {}) if isinstance(body, dict) else {}

    async def health(self) -> bool:
        """GET /health → True 当 data.status in ('ok','healthy')。

        /health 在 /api/v1 之外（01 §2.7）。任何异常视为不健康（返回 False）。
        """
        try:
            resp = await self._client.get(f"{self.base_url}/health")
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError):
            return False
        # 兼容 {"status":"ok"}（文档）与包络 {"data":{"status":...}}
        status = body.get("status")
        if status is None and isinstance(body.get("data"), dict):
            status = body["data"].get("status")
        return status in ("ok", "healthy")

    async def add(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        app_id: str = DEFAULT_APP_ID,
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> dict[str, Any]:
        """POST /api/v1/memory/add（归档写入，契约 01 §2.2）。

        messages 每条: {sender_id, role, timestamp(ms,int), content, [sender_name]}。
        ⚠️ role=user 的 sender_id 即记忆索引键（必须是 QQ 号）。
        返回 data: {message_count, status: 'accumulated'|'extracted'}。
        """
        payload = {
            "session_id": session_id,
            "app_id": app_id,
            "project_id": project_id,
            "messages": messages,
        }
        return await self._post("/api/v1/memory/add", payload)

    async def flush(
        self,
        session_id: str,
        app_id: str = DEFAULT_APP_ID,
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> dict[str, Any]:
        """POST /api/v1/memory/flush（强制提取，契约 01 §2.3）。

        返回 data: {status: 'extracted'|'no_extraction'}。markdown 落盘同步，索引异步。
        """
        payload = {
            "session_id": session_id,
            "app_id": app_id,
            "project_id": project_id,
        }
        return await self._post("/api/v1/memory/flush", payload)

    async def search(
        self,
        *,
        query: str,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str = DEFAULT_APP_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        method: str = SEARCH_METHOD_HYBRID,
        top_k: int = -1,
        radius: float | None = None,
        include_profile: bool = False,
        enable_llm_rerank: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/memory/search（检索，注入用，契约 01 §2.4）。

        ⚠️ user_id / agent_id 必须恰好设一个（否则 EverOS 422）。本地先校验，
           避免无谓往返，也避免误传两个被服务端拒。
        ⚠️ include_profile=True 才返回 profiles[]（默认 false）——本插件核心。
        返回 data: {episodes[], profiles[], agent_cases[], agent_skills[], unprocessed_messages[]}。
        """
        if (user_id is None) == (agent_id is None):
            raise EverOSUnavailable(
                "search 需恰好提供 user_id 或 agent_id 之一（01 §2.4）"
            )
        payload: dict[str, Any] = {
            "query": query,
            "app_id": app_id,
            "project_id": project_id,
            "method": method,
            "top_k": top_k,
            "include_profile": include_profile,
            "enable_llm_rerank": enable_llm_rerank,
        }
        if user_id is not None:
            payload["user_id"] = user_id
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if radius is not None:
            payload["radius"] = radius
        if filters is not None:
            payload["filters"] = filters
        return await self._post("/api/v1/memory/search", payload)

    async def get(
        self,
        *,
        memory_type: str,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str = DEFAULT_APP_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "timestamp",
        sort_order: str = "desc",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/memory/get（分页列举，管理命令/统计用，契约 01 §2.5）。

        ⚠️ memory_type 仅 episode/profile/agent_case/agent_skill（不是 user_profile）。
        ⚠️ user_id / agent_id 恰好一个。
        返回 data: {<plural>[], total_count, count}。
        """
        if (user_id is None) == (agent_id is None):
            raise EverOSUnavailable(
                "get 需恰好提供 user_id 或 agent_id 之一（01 §2.5）"
            )
        payload: dict[str, Any] = {
            "memory_type": memory_type,
            "app_id": app_id,
            "project_id": project_id,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if user_id is not None:
            payload["user_id"] = user_id
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if filters is not None:
            payload["filters"] = filters
        return await self._post("/api/v1/memory/get", payload)
