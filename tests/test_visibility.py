"""visibility 隐私分层测试。

群聊公开层过滤 filter_public —— 保留 profiles、丢弃 episodes。
覆盖四种场景（都有 / 只有画像 / 只有情景 / 都空）+ 不变量（内容完整、不改入参）。
"""

from core.visibility import filter_public

_P1 = {"summary": "喜欢科学", "category": "TASTE"}
_P2 = {"summary": "在校学生", "category": "IDENTITY"}
_E1 = {"summary": "周末去爬了香山", "date": "2026-06-21"}
_E2 = {"summary": "私聊吐槽了同事", "date": "2026-06-20"}


def test_both_present_keeps_profiles_drops_episodes():
    profiles, episodes = filter_public([_P1, _P2], [_E1, _E2])
    assert profiles == [_P1, _P2]  # 画像全保留
    assert episodes == []  # 情景全丢弃（封堵私聊内容群聊泄露）


def test_only_profiles():
    profiles, episodes = filter_public([_P1], [])
    assert profiles == [_P1]
    assert episodes == []


def test_only_episodes_all_dropped():
    profiles, episodes = filter_public([], [_E1])
    assert profiles == []
    assert episodes == []


def test_both_empty():
    profiles, episodes = filter_public([], [])
    assert profiles == []
    assert episodes == []


def test_profile_content_preserved():
    """画像字段不被裁剪/篡改，原样透传。"""
    profiles, _ = filter_public([_P1, _P2], [_E1])
    assert profiles[0] == {"summary": "喜欢科学", "category": "TASTE"}
    assert profiles[1] == {"summary": "在校学生", "category": "IDENTITY"}


def test_does_not_mutate_input_episodes():
    """旁路过滤不得改入参列表（调用方 main.py 仍持有原引用）。"""
    eps = [_E1, _E2]
    filter_public([_P1], eps)
    assert eps == [_E1, _E2]  # 原列表未被清空
