"""注入逻辑测试（injection.py）：文本拼装 + req 改写，纯函数无网络。"""

from __future__ import annotations

from core.injection import build_text, inject, resolve_covenant


class FakeReq:
    def __init__(self, system_prompt="", prompt=""):
        self.system_prompt = system_prompt
        self.prompt = prompt


def test_build_text_empty_when_no_memory():
    """画像和情景都空 → 返回空串（调用方据此跳过注入）。"""
    assert build_text([], [], None) == ""


def test_build_text_profile_dict():
    profiles = [{"profile_data": {"作息": "熬夜", "音乐": ["Aimer", "Artcore"]}}]
    text = build_text(profiles, [], None)
    assert "【用户长期印象】" in text
    assert "熬夜" in text
    assert "Aimer、Artcore" in text  # list 用顿号连接
    assert text.startswith("<ReadingSteiner_Memory>")
    assert text.endswith("</ReadingSteiner_Memory>")


def test_build_text_profile_str():
    text = build_text([{"profile_data": "用户是黑咖啡党"}], [], None)
    assert "用户是黑咖啡党" in text


def test_build_text_everos_schema_clean_chinese():
    """EverOS 画像 schema → 整洁中文：三段标签 + 丢弃 evidence/timestamp。"""
    profiles = [
        {
            "profile_data": {
                "summary": "用户最近迷上爬山",
                "explicit_info": [
                    {"category": "兴趣", "description": "迷上爬山", "evidence": "用户说X"}
                ],
                "implicit_traits": [
                    {
                        "trait": "行动力强",
                        "description": "迅速行动",
                        "tags": ["Work-Focused"],
                        "evidence": "依据Y",
                        "basis": "推断Z",
                    }
                ],
                "profile_timestamp_ms": 1782062158584,
            }
        }
    ]
    text = build_text(profiles, [], None)
    assert "总体印象：用户最近迷上爬山" in text
    assert "显式信息：" in text
    assert "- [兴趣] 迷上爬山" in text
    assert "隐含特质：" in text
    assert "- 行动力强（Work-Focused）：迅速行动" in text
    # 溯源/时间字段不进注入（降噪省 token）
    assert "用户说X" not in text
    assert "依据Y" not in text
    assert "推断Z" not in text
    assert "1782062158584" not in text
    # 不出现 dict-repr 噪声
    assert "{'" not in text


def test_build_text_episodes_with_time():
    eps = [{"timestamp": 1716885133000, "summary": "循环 Aimer 新专辑"}]
    text = build_text([], eps, None)
    assert "【相关情景记忆】" in text
    assert "循环 Aimer 新专辑" in text
    assert "2024-05-28" in text  # 毫秒时间戳被格式化


def test_inject_system_prepend():
    req = FakeReq(system_prompt="BASE")
    inject(req, "MEM", "system_prompt", "prepend")
    assert req.system_prompt == "MEMBASE"


def test_inject_system_append():
    req = FakeReq(system_prompt="BASE")
    inject(req, "MEM", "system_prompt", "append")
    assert req.system_prompt == "BASEMEM"


def test_inject_user_prepend():
    req = FakeReq(prompt="问题")
    inject(req, "MEM", "user_prompt", "prepend")
    assert req.prompt == "MEM\n问题"


def test_inject_empty_text_noop():
    req = FakeReq(system_prompt="BASE")
    inject(req, "", "system_prompt", "prepend")
    assert req.system_prompt == "BASE"  # 空文本不污染


# ── 永恒铭契 ETERNAL_COVENANT ──


class FakeConfig:
    """最小 config 替身：仅支持 .get(key, default)。"""

    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


_COVENANT_JSON = '{"1001": "  示例不变契约文本  ", "1002": "另一份契约"}'


def test_resolve_covenant_hit():
    """命中：返回该 user_id 的铭契文本（首尾空白被 strip）。"""
    cfg = FakeConfig({"eternal_covenant": _COVENANT_JSON})
    assert resolve_covenant(cfg, "1001") == "示例不变契约文本"


def test_resolve_covenant_miss_user():
    """表里没有该 user_id → ''。"""
    cfg = FakeConfig({"eternal_covenant": _COVENANT_JSON})
    assert resolve_covenant(cfg, "999") == ""


def test_resolve_covenant_empty_config():
    """未配置 / config 为 None / user_id 为空 → 一律 ''。"""
    assert resolve_covenant(FakeConfig({"eternal_covenant": ""}), "1001") == ""
    assert resolve_covenant(None, "1001") == ""
    assert resolve_covenant(FakeConfig({"eternal_covenant": _COVENANT_JSON}), "") == ""


def test_resolve_covenant_invalid_json():
    """JSON 非法 / 顶层非 dict → 安全降级为 ''（不抛异常）。"""
    assert resolve_covenant(FakeConfig({"eternal_covenant": "{不是合法JSON"}), "111") == ""
    assert resolve_covenant(FakeConfig({"eternal_covenant": '["列表不是dict"]'}), "111") == ""


def test_build_text_covenant_first_block_with_profile():
    """铭契非空：作首块【永恒铭契】，置于【用户长期印象】之前，且与 EverOS summary 并存。"""
    profiles = [{"profile_data": {"summary": "用户最近迷上爬山"}}]
    text = build_text(profiles, [], None, covenant="不变的核心契约")
    assert "【永恒铭契】\n不变的核心契约" in text
    assert "【用户长期印象】" in text
    # 铭契是新增块、非替换 summary —— EverOS 演进 summary 仍渲染
    assert "用户最近迷上爬山" in text
    # 顺序：铭契在画像之前
    assert text.index("【永恒铭契】") < text.index("【用户长期印象】")


def test_build_text_no_covenant_no_block():
    """covenant 缺省/空 → 不出现【永恒铭契】块（不影响现有 3 参调用）。"""
    profiles = [{"profile_data": {"summary": "用户最近迷上爬山"}}]
    assert "【永恒铭契】" not in build_text(profiles, [], None)
    assert "【永恒铭契】" not in build_text(profiles, [], None, covenant="")
