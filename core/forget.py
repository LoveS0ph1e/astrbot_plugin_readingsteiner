"""记忆遗忘(抑制)层：插件侧在注入/召回读路径上过滤掉用户指定遗忘的记忆。

EverOS v1 API 无删除端点、且与插件不共享文件系统，故真删除不可行。本层在读路径「抑制」
匹配到的记忆：数据仍在 EverOS，只是不再被注入/召回。两种粒度——① 按内容短语滤掉匹配的
explicit_info/implicit_traits/episode；② forget_all 整用户 opt-out(不注入 + 不归档)。

存储镜像 relationship.RelationshipStore：每用户一文件 <data_dir>/forget/<user_id>.md，
原子写 + .bak，首行 HTML 注释载 JSON meta(forget_all/updated_at)，正文每行一条遗忘短语。
身份三铁律：本模块不校验 user_id 来源(留给 identity_resolver)，只按受信 user_id 定位文件，
对分隔符/穿越做硬校验。归一化与匹配是纯函数，apply_forget 不调 EverOS/AstrBot。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import (
    PROFILE_FIELD_EXPLICIT,
    PROFILE_FIELD_IMPLICIT,
    PROFILE_KEY_DESCRIPTION,
    PROFILE_KEY_TAGS,
    PROFILE_KEY_TRAIT,
)

_MARKER = "<!-- readingsteiner-forget v1"
MIN_PHRASE_LEN = 2  # 归一化后最小长度；过短(单字)拒绝入库，防误伤整片画像
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class ForgetState:
    """一份用户遗忘态：整用户 opt-out 标志 + 若干已归一化遗忘短语。"""

    user_id: str
    forget_all: bool
    phrases: tuple[str, ...]
    updated_at: str  # ISO8601


class ForgetStoreError(Exception):
    """遗忘文件读写失败(不可信 user_id、IO 异常等)。"""


# ────────────────── 归一化 + 匹配(纯函数，store 与 apply_forget 共用) ──────────────────


def normalize(s: Any) -> str:
    """归一化：折叠内部连续空白为单空格 + 去首尾 + casefold(中文无副作用，英文/全角更稳)。"""
    return _WS.sub(" ", str(s)).strip().casefold()


def _phrase_matches(phrase_norm: str, *texts: Any) -> bool:
    """phrase_norm(已归一化、非空)是否为任一 text 归一化后的子串。空短语永不命中。"""
    if not phrase_norm:
        return False
    return any(phrase_norm in normalize(t) for t in texts)


def _explicit_matches(item: Any, phrases: tuple[str, ...]) -> bool:
    """explicit_info 条目命中：只匹配 description(不匹配 category，避免按整类误删)。"""
    if not isinstance(item, dict):
        return False
    desc = item.get(PROFILE_KEY_DESCRIPTION) or ""
    return any(_phrase_matches(p, desc) for p in phrases)


def _implicit_matches(item: Any, phrases: tuple[str, ...]) -> bool:
    """implicit_traits 条目命中：trait / description / 任一 tag 命中即删该条。"""
    if not isinstance(item, dict):
        return False
    trait = item.get(PROFILE_KEY_TRAIT) or ""
    desc = item.get(PROFILE_KEY_DESCRIPTION) or ""
    tags = item.get(PROFILE_KEY_TAGS) or []
    texts = [trait, desc, *[str(t) for t in tags]]
    return any(_phrase_matches(p, *texts) for p in phrases)


def _episode_matches(ep: Any, phrases: tuple[str, ...]) -> bool:
    """episode 命中：summary / subject / content 任一(字段同 injection._render_episodes)。"""
    if not isinstance(ep, dict):
        return False
    texts = [ep.get("summary") or "", ep.get("subject") or "", ep.get("content") or ""]
    return any(_phrase_matches(p, *texts) for p in phrases)


def _filter_profile(profile: Any, phrases: tuple[str, ...]) -> Any:
    """构造**新** profile dict，滤掉 profile_data 内匹配短语的 explicit/implicit 条目。

    镜像 injection._render_profile 的取数：有 profile_data 用之，否则 profile 自身即 data。
    整条 profile 不删，只删内部匹配条目；其它字段(summary 等)透传。绝不原地改入参。
    """
    if not isinstance(profile, dict):
        return profile
    has_pd = isinstance(profile.get("profile_data"), dict)
    data = profile["profile_data"] if has_pd else profile
    if not isinstance(data, dict):
        return dict(profile) if has_pd else profile
    new_data = dict(data)
    exp = data.get(PROFILE_FIELD_EXPLICIT)
    if isinstance(exp, list):
        new_data[PROFILE_FIELD_EXPLICIT] = [it for it in exp if not _explicit_matches(it, phrases)]
    imp = data.get(PROFILE_FIELD_IMPLICIT)
    if isinstance(imp, list):
        new_data[PROFILE_FIELD_IMPLICIT] = [it for it in imp if not _implicit_matches(it, phrases)]
    if has_pd:
        new_profile = dict(profile)
        new_profile["profile_data"] = new_data
        return new_profile
    return new_data


def apply_forget(
    profiles: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    state: ForgetState | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按遗忘态过滤检索结果。镜像 visibility.filter_public 的签名/定位。

    - state 为 None 或无规则 → 内容原样返回(新列表，不改入参)。
    - forget_all → ([], [])。
    - 否则滤掉匹配短语的 explicit/implicit 条目(profile 整条保留)与匹配的整条 episode。
    必须返回新对象，绝不原地改入参(单请求内 profiles[0] 被 overall_impression 与 build_text 共用)。
    """
    if state is None or (not state.forget_all and not state.phrases):
        return list(profiles), list(episodes)
    if state.forget_all:
        return [], []
    phrases = state.phrases
    new_profiles = [_filter_profile(p, phrases) for p in profiles]
    new_episodes = [ep for ep in episodes if not _episode_matches(ep, phrases)]
    return new_profiles, new_episodes


# ────────────────── 每用户遗忘文件存储(镜像 relationship.RelationshipStore) ──────────────────


def _is_safe_user_id(user_id: str) -> bool:
    """最小校验：非空、无路径分隔符/穿越片段(绝不让 user_id 拼出越界路径)。"""
    return bool(user_id) and not any(ch in user_id for ch in ("/", "\\", "..", os.sep))


class ForgetStore:
    """遗忘态 md 读写。每用户一文件：``<data_dir>/forget/<user_id>.md``。

    Args:
        data_dir: 插件数据目录(生产为 AstrBot 挂载的 /AstrBot/data/<plugin>)。
    """

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir

    def _path(self, user_id: str) -> Path:
        if not _is_safe_user_id(user_id):
            raise ForgetStoreError(f"不可信的 user_id: {user_id!r}")
        return Path(self.data_dir) / "forget" / f"{user_id}.md"

    def get(self, user_id: str) -> ForgetState | None:
        """读遗忘态；文件不存在/损坏(无 marker)→ None(安全降级)。

        与 relationship 不同：meta-only 文件(forget_all=True 无短语)仍返回 state。
        """
        try:
            raw = self._path(user_id).read_text(encoding="utf-8-sig")
        except (FileNotFoundError, OSError):
            return None
        meta, phrases = _parse(raw)
        if meta is None:
            return None
        return ForgetState(
            user_id=user_id,
            forget_all=bool(meta.get("forget_all", False)),
            phrases=tuple(phrases),
            updated_at=str(meta.get("updated_at", "")),
        )

    def add_phrase(self, user_id: str, phrase: str, *, now_iso: str | None = None) -> bool:
        """归一化后入库(去重、拒过短)。返回是否真正新增。原子写 + .bak。"""
        norm = normalize(phrase)
        if len(norm) < MIN_PHRASE_LEN:
            return False
        state = self.get(user_id)
        phrases = list(state.phrases) if state else []
        forget_all = state.forget_all if state else False
        if norm in phrases:
            return False
        phrases.append(norm)
        self._write(user_id, forget_all, phrases, now_iso=now_iso)
        return True

    def set_forget_all(self, user_id: str, value: bool, *, now_iso: str | None = None) -> None:
        """置 forget_all 标志，保留已有短语。"""
        state = self.get(user_id)
        phrases = list(state.phrases) if state else []
        self._write(user_id, bool(value), phrases, now_iso=now_iso)

    def clear(self, user_id: str) -> bool:
        """撤销：删除该用户的遗忘文件(forget_all 与全部短语一并清)。返回是否存在过。"""
        try:
            self._path(user_id).unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as e:
            raise ForgetStoreError(f"清除遗忘文件失败: {e}") from e

    def _write(
        self, user_id: str, forget_all: bool, phrases: list[str], *, now_iso: str | None
    ) -> None:
        stamp = now_iso or datetime.now(UTC).isoformat(timespec="seconds")
        meta = {"forget_all": bool(forget_all), "updated_at": stamp}
        body = "\n".join(phrases)
        content = f"{_MARKER} {json.dumps(meta, ensure_ascii=False)} -->\n\n{body}\n"
        self._atomic_write(self._path(user_id), content)

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


def _parse(raw: str) -> tuple[dict | None, list[str]]:
    """拆 (meta, phrases)。首行须是 marker 注释含 JSON；否则视为损坏返回 (None, [])。"""
    if not raw:
        return None, []
    nl = raw.find("\n")
    first = raw if nl < 0 else raw[:nl]
    if _MARKER not in first:
        return None, []
    try:
        start = first.index("{")
        end = first.rindex("}")
        meta = json.loads(first[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return None, []
    if not isinstance(meta, dict):
        return None, []
    body = "" if nl < 0 else raw[nl + 1 :]
    phrases = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return meta, phrases
