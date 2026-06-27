"""关系层存储：每用户 relationship.md —— 插件自有、不受 EverOS flush 牵连的固定/合成层。

首个落点：存放「k_makise 视角的整体印象」(由 EverOS 画像的 explicit/implicit 合成，
见 synthesis；本模块只负责存取与变更检测，不调 LLM/EverOS，分层不串味)。按 source_hash
做变更检测——画像的 explicit+implicit 变了才需重算，避免每轮 LLM 合成(防烧钱)。
后续可在同一文件扩展羁绊层级/称呼/弧状态(差异化 D2)。

设计取舍：
- **插件自有格式**(非 EverOS 解析)，故零额外依赖、人/WebUI 可读：首行 HTML 注释承载
  JSON 元数据(source_hash/updated_at)，其后正文即整体印象文本。
- 原子写 temp+os.replace + 写前 .bak(同 covenant_store)；utf-8 写不回 BOM，读用
  utf-8-sig 容错。
- 身份三铁律：本模块不校验 user_id(留给 identity_resolver)，调用方先过 resolve；
  这里只按受信 user_id 定位文件，绝不接受拼路径片段——故 _path 对分隔符/穿越做硬校验。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_MARKER = "<!-- readingsteiner-relationship v1"


@dataclass(frozen=True)
class Relationship:
    """一份用户关系态（当前仅整体印象；后续可扩羁绊层级等）。"""

    user_id: str
    overall_impression: str
    source_hash: str  # 合成所依据的画像内容 hash（变更检测）
    updated_at: str  # ISO8601


class RelationshipStoreError(Exception):
    """关系文件读写失败（不可信 user_id、IO 异常等）。"""


def profile_source_hash(profile_data: dict) -> str:
    """对画像的 explicit_info + implicit_traits 取稳定 hash（变更检测用）。

    刻意**只**纳入这两块：summary 是 everalgo 从 explicit[0] 派生的副本(会随之变)，
    profile_timestamp_ms 每次合成都变——都不该触发重算。sort_keys 保证等价 dict 同 hash。
    """
    payload = json.dumps(
        {
            "explicit_info": profile_data.get("explicit_info") or [],
            "implicit_traits": profile_data.get("implicit_traits") or [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_safe_user_id(user_id: str) -> bool:
    """最小校验：非空、无路径分隔符/穿越片段（绝不让 user_id 拼出越界路径）。"""
    return bool(user_id) and not any(ch in user_id for ch in ("/", "\\", "..", os.sep))


class RelationshipStore:
    """关系层 md 读写。每用户一文件：``<data_dir>/relationships/<user_id>.md``。

    Args:
        data_dir: 插件数据目录（生产为 AstrBot 挂载的 /AstrBot/data/<plugin>）。
    """

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir

    def _path(self, user_id: str) -> Path:
        if not _is_safe_user_id(user_id):
            raise RelationshipStoreError(f"不可信的 user_id: {user_id!r}")
        return Path(self.data_dir) / "relationships" / f"{user_id}.md"

    def get(self, user_id: str) -> Relationship | None:
        """读一份关系态；文件不存在/损坏 → None（安全降级，绝不抛断对话）。"""
        try:
            raw = self._path(user_id).read_text(encoding="utf-8-sig")
        except (FileNotFoundError, OSError):
            return None
        meta, body = _parse(raw)
        if meta is None:
            return None
        impression = body.strip()
        if not impression:
            return None
        return Relationship(
            user_id=user_id,
            overall_impression=impression,
            source_hash=str(meta.get("source_hash", "")),
            updated_at=str(meta.get("updated_at", "")),
        )

    def put(
        self,
        user_id: str,
        overall_impression: str,
        source_hash: str,
        *,
        now_iso: str | None = None,
    ) -> None:
        """写入/覆盖一份关系态。原子写 + .bak。now_iso 可注入以便单测。"""
        stamp = now_iso or datetime.now(UTC).isoformat(timespec="seconds")
        meta = {"source_hash": source_hash, "updated_at": stamp}
        content = (
            f"{_MARKER} {json.dumps(meta, ensure_ascii=False)} -->\n\n"
            f"{overall_impression.strip()}\n"
        )
        self._atomic_write(self._path(user_id), content)

    def is_stale(self, user_id: str, profile_data: dict) -> bool:
        """当前画像是否需要(重新)合成：无文件、或 source_hash 与画像现状不符。"""
        rel = self.get(user_id)
        return rel is None or rel.source_hash != profile_source_hash(profile_data)

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",  # 不回写 BOM
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp.name, path)


def _parse(raw: str) -> tuple[dict | None, str]:
    """拆 (meta, body)。首行须是 marker 注释含 JSON；否则视为损坏返回 (None, '')。"""
    if not raw:
        return None, ""
    nl = raw.find("\n")
    first = raw if nl < 0 else raw[:nl]
    if _MARKER not in first:
        return None, ""
    try:
        start = first.index("{")
        end = first.rindex("}")
        meta = json.loads(first[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return None, ""
    if not isinstance(meta, dict):
        return None, ""
    body = "" if nl < 0 else raw[nl + 1 :]
    return meta, body
