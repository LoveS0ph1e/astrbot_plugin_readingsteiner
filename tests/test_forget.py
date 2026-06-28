"""记忆遗忘(抑制)测试：ForgetStore 文件 IO + apply_forget 纯函数 + 归一化匹配。

照 test_relationship.py（tmp_path 文件 IO）+ test_visibility.py（纯函数过滤、不改入参不变量）。
不依赖 AstrBot。
"""

from __future__ import annotations

import pytest

from core.forget import (
    ForgetState,
    ForgetStore,
    ForgetStoreError,
    apply_forget,
    normalize,
)

_TS = "2026-06-28T12:00:00+00:00"


# ────────────────── ForgetStore（文件 IO） ──────────────────


def test_add_phrase_roundtrip(tmp_path):
    store = ForgetStore(str(tmp_path))
    assert store.add_phrase("1001", "爬山", now_iso=_TS) is True
    state = store.get("1001")
    assert state is not None
    assert state.user_id == "1001"
    assert state.forget_all is False
    assert state.phrases == ("爬山",)
    assert state.updated_at == _TS


def test_add_phrase_dedup(tmp_path):
    store = ForgetStore(str(tmp_path))
    assert store.add_phrase("1001", "爬山") is True
    assert store.add_phrase("1001", "爬山") is False  # 重复不再入库
    assert store.get("1001").phrases == ("爬山",)


def test_add_phrase_normalizes(tmp_path):
    store = ForgetStore(str(tmp_path))
    assert store.add_phrase("1001", "  Aimer  ") is True
    assert store.add_phrase("1001", "aimer") is False  # casefold + 去空白后视为重复
    assert store.get("1001").phrases == ("aimer",)


def test_add_phrase_rejects_too_short(tmp_path):
    store = ForgetStore(str(tmp_path))
    assert store.add_phrase("1001", "猫") is False  # 单字 < MIN_PHRASE_LEN
    assert store.get("1001") is None  # 没入库 → 没建文件


def test_add_phrase_folds_whitespace(tmp_path):
    store = ForgetStore(str(tmp_path))
    assert store.add_phrase("1001", "周末 爬山") is True
    assert store.add_phrase("1001", "周末  爬山") is False  # 连续空白折叠后相同
    assert store.get("1001").phrases == ("周末 爬山",)


def test_set_forget_all_preserves_phrases(tmp_path):
    store = ForgetStore(str(tmp_path))
    store.add_phrase("1001", "爬山")
    store.set_forget_all("1001", True, now_iso=_TS)
    state = store.get("1001")
    assert state.forget_all is True
    assert state.phrases == ("爬山",)


def test_forget_all_persists_with_no_phrases(tmp_path):
    store = ForgetStore(str(tmp_path))
    store.set_forget_all("1001", True)
    state = store.get("1001")
    assert state is not None  # meta-only 文件仍返回 state（与 relationship 不同）
    assert state.forget_all is True
    assert state.phrases == ()


def test_clear_removes_file(tmp_path):
    store = ForgetStore(str(tmp_path))
    store.set_forget_all("1001", True)
    store.add_phrase("1001", "爬山")
    assert store.clear("1001") is True
    assert store.get("1001") is None
    assert store.clear("1001") is False  # 幂等：再清返回 False


def test_get_missing_returns_none(tmp_path):
    assert ForgetStore(str(tmp_path)).get("nope") is None


def test_corrupt_file_returns_none(tmp_path):
    store = ForgetStore(str(tmp_path))
    p = tmp_path / "forget" / "1001.md"
    p.parent.mkdir(parents=True)
    p.write_text("没有 marker 的乱文件", encoding="utf-8")
    assert store.get("1001") is None


def test_unsafe_user_id_rejected(tmp_path):
    store = ForgetStore(str(tmp_path))
    for bad in ("", "../etc", "a/b", "a\\b"):
        with pytest.raises(ForgetStoreError):
            store.add_phrase(bad, "爬山")


def test_atomic_write_backs_up(tmp_path):
    store = ForgetStore(str(tmp_path))
    store.add_phrase("1001", "爬山")
    store.add_phrase("1001", "游泳")  # 二次写触发 .bak
    assert (tmp_path / "forget" / "1001.md.bak").exists()


# ────────────────── normalize（纯函数） ──────────────────


def test_normalize_strips_folds_casefolds():
    assert normalize("  Aimer  ") == "aimer"
    assert normalize("周末  爬山") == "周末 爬山"
    assert normalize("") == ""


# ────────────────── apply_forget（纯函数过滤） ──────────────────


def _profile(explicit=None, implicit=None, **extra):
    data = {"explicit_info": explicit or [], "implicit_traits": implicit or []}
    data.update(extra)
    return {"profile_data": data}


def _state(phrases=(), forget_all=False):
    return ForgetState(
        user_id="1001", forget_all=forget_all, phrases=tuple(phrases), updated_at=_TS
    )


def test_apply_none_state_passthrough():
    profs = [_profile([{"category": "兴趣", "description": "喜欢爬山"}])]
    eps = [{"summary": "周末去爬山"}]
    out_p, out_e = apply_forget(profs, eps, None)
    assert out_p == profs
    assert out_e == eps


def test_apply_empty_state_passthrough():
    profs = [_profile([{"category": "兴趣", "description": "喜欢爬山"}])]
    out_p, _ = apply_forget(profs, [], _state())
    assert out_p == profs


def test_apply_forget_all_returns_empty():
    profs = [_profile([{"category": "兴趣", "description": "喜欢爬山"}])]
    out_p, out_e = apply_forget(profs, [{"summary": "x"}], _state(forget_all=True))
    assert out_p == []
    assert out_e == []


def test_apply_filters_explicit_by_description():
    profs = [
        _profile(
            explicit=[
                {"category": "兴趣", "description": "喜欢爬山"},
                {"category": "音乐", "description": "喜欢 Aimer"},
            ],
            implicit=[{"trait": "细致", "description": "做事认真"}],
        )
    ]
    out_p, _ = apply_forget(profs, [], _state(phrases=("爬山",)))
    exp = out_p[0]["profile_data"]["explicit_info"]
    assert len(exp) == 1
    assert exp[0]["description"] == "喜欢 Aimer"
    assert len(out_p[0]["profile_data"]["implicit_traits"]) == 1  # implicit 不受影响


def test_apply_does_not_match_category():
    # 短语 == category("兴趣")，但不在任何 description 中 → 不删（防按整类误删）
    profs = [_profile([{"category": "兴趣", "description": "喜欢爬山"}])]
    out_p, _ = apply_forget(profs, [], _state(phrases=("兴趣",)))
    assert len(out_p[0]["profile_data"]["explicit_info"]) == 1


@pytest.mark.parametrize("phrase", ["神经", "海马体", "脑科学"])
def test_apply_filters_implicit_by_trait_desc_tags(phrase):
    profs = [
        _profile(implicit=[{"trait": "神经", "description": "钻研海马体", "tags": ["脑科学"]}])
    ]
    out_p, _ = apply_forget(profs, [], _state(phrases=(phrase,)))
    assert out_p[0]["profile_data"]["implicit_traits"] == []


@pytest.mark.parametrize("field", ["summary", "subject", "content"])
def test_apply_filters_episode_by_any_field(field):
    eps = [{field: "周末去爬山", "score": 0.9}]
    _, out_e = apply_forget([], eps, _state(phrases=("爬山",)))
    assert out_e == []


def test_apply_substring_match():
    profs = [_profile([{"category": "宠物", "description": "养了一只叫煤球的猫"}])]
    out_p, _ = apply_forget(profs, [], _state(phrases=("煤球",)))
    assert out_p[0]["profile_data"]["explicit_info"] == []


def test_apply_casefold_match():
    profs = [_profile([{"category": "音乐", "description": "最近常听 Aimer"}])]
    out_p, _ = apply_forget(profs, [], _state(phrases=("aimer",)))
    assert out_p[0]["profile_data"]["explicit_info"] == []


def test_apply_multiple_phrases_or():
    profs = [
        _profile(
            [
                {"category": "兴趣", "description": "喜欢爬山"},
                {"category": "音乐", "description": "喜欢 Aimer"},
            ]
        )
    ]
    out_p, _ = apply_forget(profs, [], _state(phrases=("爬山", "aimer")))
    assert out_p[0]["profile_data"]["explicit_info"] == []


def test_apply_returns_new_objects():
    inner = {
        "explicit_info": [{"category": "兴趣", "description": "喜欢爬山"}],
        "implicit_traits": [],
    }
    prof = {"profile_data": inner}
    out_p, _ = apply_forget([prof], [], _state(phrases=("游泳",)))  # 不命中也应是新对象
    assert out_p[0] is not prof
    assert out_p[0]["profile_data"] is not inner


def test_apply_does_not_mutate_input():
    inner_exp = [{"category": "兴趣", "description": "喜欢爬山"}]
    prof = {"profile_data": {"explicit_info": inner_exp, "implicit_traits": []}}
    eps = [{"summary": "周末去爬山"}]
    apply_forget([prof], eps, _state(phrases=("爬山",)))
    assert len(inner_exp) == 1  # 原 explicit 列表未被改
    assert len(prof["profile_data"]["explicit_info"]) == 1
    assert eps == [{"summary": "周末去爬山"}]  # 原 episodes 列表未被改


def test_apply_keeps_profile_and_other_fields():
    prof = _profile([{"category": "兴趣", "description": "喜欢爬山"}], summary="总结句")
    out_p, _ = apply_forget([prof], [], _state(phrases=("爬山",)))
    assert len(out_p) == 1  # profile 整条不删
    assert out_p[0]["profile_data"]["summary"] == "总结句"  # 其它字段透传
    assert out_p[0]["profile_data"]["explicit_info"] == []


def test_apply_handles_missing_profile_data():
    out_p, _ = apply_forget([{"foo": "bar"}], [], _state(phrases=("爬山",)))
    assert out_p == [{"foo": "bar"}]
    out_p2, _ = apply_forget([{"profile_data": "字符串"}], [], _state(phrases=("爬山",)))
    assert out_p2 == [{"profile_data": "字符串"}]
