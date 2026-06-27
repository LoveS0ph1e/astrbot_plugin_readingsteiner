"""关系层存储测试（relationship.py）：md 读写 + 变更检测，纯文件 IO 无网络。"""

from __future__ import annotations

import pytest

from core.relationship import (
    RelationshipStore,
    RelationshipStoreError,
    profile_source_hash,
)

_TS = "2026-06-28T12:00:00+00:00"


def _profile(explicit, implicit):
    return {"explicit_info": explicit, "implicit_traits": implicit}


def test_put_get_roundtrip(tmp_path):
    store = RelationshipStore(str(tmp_path))
    store.put("1001", "嘴硬心软、记性极好的人", "hash_abc", now_iso=_TS)
    rel = store.get("1001")
    assert rel is not None
    assert rel.user_id == "1001"
    assert rel.overall_impression == "嘴硬心软、记性极好的人"
    assert rel.source_hash == "hash_abc"
    assert rel.updated_at == _TS


def test_get_missing_returns_none(tmp_path):
    assert RelationshipStore(str(tmp_path)).get("nope") is None


def test_put_overwrites_and_backs_up(tmp_path):
    store = RelationshipStore(str(tmp_path))
    store.put("1001", "旧印象", "h1", now_iso=_TS)
    store.put("1001", "新印象", "h2", now_iso="2026-06-28T13:00:00+00:00")
    rel = store.get("1001")
    assert rel.overall_impression == "新印象"
    assert rel.source_hash == "h2"
    bak = tmp_path / "relationships" / "1001.md.bak"
    assert bak.exists()
    assert "旧印象" in bak.read_text(encoding="utf-8")


def test_source_hash_stable_and_sensitive():
    p1 = _profile([{"category": "a", "description": "x"}], [{"trait": "t"}])
    p2 = _profile([{"category": "a", "description": "x"}], [{"trait": "t"}])
    p3 = _profile([{"category": "a", "description": "y"}], [{"trait": "t"}])
    assert profile_source_hash(p1) == profile_source_hash(p2)
    assert profile_source_hash(p1) != profile_source_hash(p3)


def test_source_hash_ignores_summary_and_timestamp():
    base = _profile([{"category": "a", "description": "x"}], [])
    noisy = dict(base, summary="任意 summary", profile_timestamp_ms=999)
    assert profile_source_hash(base) == profile_source_hash(noisy)


def test_is_stale(tmp_path):
    store = RelationshipStore(str(tmp_path))
    prof = _profile([{"category": "a", "description": "x"}], [])
    assert store.is_stale("1001", prof) is True  # 无文件 → 需合成
    store.put("1001", "印象", profile_source_hash(prof), now_iso=_TS)
    assert store.is_stale("1001", prof) is False  # hash 一致 → 不需重算
    prof2 = _profile([{"category": "a", "description": "y"}], [])
    assert store.is_stale("1001", prof2) is True  # 画像变了 → 需重算


def test_unsafe_user_id_rejected(tmp_path):
    store = RelationshipStore(str(tmp_path))
    for bad in ("", "../etc", "a/b", "a\\b"):
        with pytest.raises(RelationshipStoreError):
            store.put(bad, "x", "h")


def test_corrupt_file_returns_none(tmp_path):
    store = RelationshipStore(str(tmp_path))
    p = tmp_path / "relationships" / "1001.md"
    p.parent.mkdir(parents=True)
    p.write_text("没有 marker 的乱文件", encoding="utf-8")
    assert store.get("1001") is None
