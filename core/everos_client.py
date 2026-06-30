"""EverOS REST API v1 异步客户端。

纯 HTTP 封装，输入输出皆 dict/原生类型，不依赖任何 AstrBot 类型
（便于脱离 AstrBot 单测，也便于其它项目复用）。

EverOS API 契约要点：
- 所有业务端点在 /api/v1/memory/ 下，全部 POST（即使语义像读）
- 200 响应统一包络 {request_id, data:{...}}；错误 {request_id, error:{...}}
  → 解析一律先取 data；有 error 抛 EverOSUnavailable
- /health、/metrics 在 /api/v1 之外
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .constants import (
    DEFAULT_APP_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_TIMEOUT,
    RETRY_BACKOFF_SECONDS,
    RETRYABLE_ERROR_CODES,
    SEARCH_METHOD_HYBRID,
)


class EverOSUnavailable(Exception):
    """EverOS 不可达 / 请求失败 / 返回 error 包络。

    上层钩子捕获后降级（跳过记忆，不阻断对话）。

    Attributes:
        code: EverOS 1.1.0 typed `error.code`（如 NOT_FOUND / EXTERNAL_SERVICE_UNAVAILABLE）；
              1.0.x 老包络或传输层错误（超时/连不上）时为 None。
        status: HTTP 状态码（有响应时）；传输层错误为 None。
        retryable: 是否值得重试（外部服务瞬时不可用 / 传输层超时；据 code 或 5xx 判定）。
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


def _is_retryable(code: str | None, status: int | None) -> bool:
    """retryable 判定：有 typed code 按 RETRYABLE_ERROR_CODES 精确判；无 code 回退 5xx 启发式。"""
    if code is not None:
        return code in RETRYABLE_ERROR_CODES
    return status is not None and status >= 500


class EverOSClient:
    """EverOS HTTP v1 客户端。

    Args:
        base_url: 服务地址。同 docker 网络用 http://everos:8000；单机用 127.0.0.1:8000。
        timeout: 请求超时秒数。超时按『无记忆』降级。
        retry_retryable: 对 retryable 错误（外部服务瞬时不可用/传输层超时）的重试次数；0=不重试。
        retry_backoff: 重试退避基数（秒），实际退避 = backoff * 第几次。
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        retry_retryable: int = 0,
        retry_backoff: float = RETRY_BACKOFF_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)
        # 仅对 retryable 错误重试有限次；其它错误立即抛出由上层降级。
        self._retry_retryable = max(0, int(retry_retryable))
        self._retry_backoff = max(0.0, float(retry_backoff))

    async def close(self) -> None:
        """关闭底层 httpx client，供 terminate 调用。"""
        await self._client.aclose()

    async def _post(
        self, path: str, payload: dict[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        """统一 POST，含 typed 错误解析与「仅 retryable」有限重试。

        retryable（外部服务瞬时不可用 / 传输层超时）按 retry_retryable 次退避重试；其它错误
        （404/参数错/永久错）立即抛出。重型/幂等敏感调用应走 _post_once 绕过重试。
        """
        attempts = self._retry_retryable + 1
        for i in range(attempts):
            try:
                return await self._post_once(path, payload, timeout=timeout)
            except EverOSUnavailable as e:
                if not e.retryable or i >= attempts - 1:
                    raise
                if self._retry_backoff:
                    await asyncio.sleep(self._retry_backoff * (i + 1))
        raise AssertionError("unreachable")  # pragma: no cover

    async def _post_once(
        self, path: str, payload: dict[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        """单次 POST：发请求 → 解析 typed 包络 → 取 data（不重试）。

        EverOS 1.1.0 错误为 {request_id, error:{code, message, ...}}，且常随非 2xx 状态返回；
        故不在解析前 raise_for_status，先读 body 拿 error.code（区分可重试/永久），再据包络/状态
        抛 EverOSUnavailable（带 code/status/retryable）。1.0.x 老包络（error 仅 message / 无 code）
        与无 body 的 HTTP 错误一律安全降级。timeout 非 None 时覆盖本次 HTTP 读超时。
        """
        try:
            kwargs: dict[str, Any] = {"json": payload}
            if timeout is not None:
                kwargs["timeout"] = timeout
            resp = await self._client.post(f"{self.base_url}{path}", **kwargs)
        except httpx.TimeoutException as e:
            raise EverOSUnavailable(f"POST {path} 超时: {e}", retryable=True) from e
        except httpx.HTTPError as e:
            raise EverOSUnavailable(f"POST {path} 失败: {e}", retryable=True) from e
        try:
            body = resp.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            if isinstance(err, dict):
                code = err.get("code")
                msg = err.get("message", "unknown")
            else:
                code, msg = None, str(err)
            label = f"[{code}] " if code else ""
            raise EverOSUnavailable(
                f"EverOS error @ {path}: {label}{msg}",
                code=code,
                status=resp.status_code,
                retryable=_is_retryable(code, resp.status_code),
            )
        if resp.status_code >= 400:
            raise EverOSUnavailable(
                f"POST {path} HTTP {resp.status_code}",
                status=resp.status_code,
                retryable=resp.status_code >= 500,
            )
        return body.get("data", {}) if isinstance(body, dict) else {}

    async def health(self) -> bool:
        """GET /health → True 当 data.status in ('ok','healthy')。

        /health 在 /api/v1 之外。任何异常视为不健康（返回 False）。
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
        """POST /api/v1/memory/add（归档写入）。

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
        """POST /api/v1/memory/flush（强制提取）。

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
        """POST /api/v1/memory/search（检索，注入用）。

        ⚠️ user_id / agent_id 必须恰好设一个（否则 EverOS 422）。本地先校验，
           避免无谓往返，也避免误传两个被服务端拒。
        ⚠️ include_profile=True 才返回 profiles[]（默认 false）——本插件核心。
        返回 data: {episodes[], profiles[], agent_cases[], agent_skills[], unprocessed_messages[]}。
        """
        if (user_id is None) == (agent_id is None):
            raise EverOSUnavailable("search 需恰好提供 user_id 或 agent_id 之一")
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
        """POST /api/v1/memory/get（分页列举，管理命令/统计用）。

        ⚠️ memory_type 仅 episode/profile/agent_case/agent_skill（不是 user_profile）。
        ⚠️ user_id / agent_id 恰好一个。
        返回 data: {<plural>[], total_count, count}。
        """
        if (user_id is None) == (agent_id is None):
            raise EverOSUnavailable("get 需恰好提供 user_id 或 agent_id 之一")
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

    async def trigger_ome(
        self,
        name: str,
        *,
        timeout: float = 120.0,
        force: bool = False,
    ) -> dict[str, Any]:
        """POST /api/v1/ome/trigger：手动触发一个已注册 OME 策略并等其完成。

        name 如 'reflect_episodes'（情景合并，需 EverOS≥1.1.0）。
        返回 data {status:'ok'|'timeout', name}。
        ⚠️ 走 _post_once（不重试，避免重复触发重型合并）；HTTP 读超时取服务端等待 timeout 之上留
           余量，避免本地先于服务端超时而误判。EverOS<1.1.0 无该策略 → NOT_FOUND 包络 →
           抛 EverOSUnavailable(code='NOT_FOUND')，由命令层友好提示。
        """
        return await self._post_once(
            "/api/v1/ome/trigger",
            {"name": name, "timeout": timeout, "force": force},
            timeout=timeout + 30.0,
        )
