"""注入逻辑测试（injection.py）：文本拼装 + req 改写，纯函数无网络。"""

from __future__ import annotations

from core.injection import (
    _clip_to_sentence,
    _episode_text,
    build_text,
    inject,
    resolve_covenant,
)


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


def test_build_text_summary_dedup_when_equals_explicit_first():
    """summary 去重：everalgo `_build_summary` 把 summary 回填为 explicit_info[0].description；
    与首条显式特征逐字雷同时不再渲染【总体印象】(免重复+免首印象偏置)，
    但该条仍在【显式信息】中保留(内容无损)。"""
    dup = "周末常去城郊爬山，下山后会找家咖啡馆坐很久"
    profiles = [
        {
            "profile_data": {
                "summary": dup,  # == explicit_info[0].description（everalgo 回填行为）
                "explicit_info": [
                    {"category": "户外爱好", "description": dup, "evidence": "X"},
                    {"category": "职业", "description": "在一家设计工作室上班", "evidence": "Y"},
                ],
                "implicit_traits": [],
            }
        }
    ]
    text = build_text(profiles, [], None)
    assert "总体印象：" not in text  # summary 块被判重跳过
    assert "显式信息：" in text
    assert f"- [户外爱好] {dup}" in text  # 内容无损，仍在显式信息中
    assert "- [职业] 在一家设计工作室上班" in text


def test_build_text_summary_kept_when_distinct():
    """自愈：summary 若是真正独立的总结(与任何显式/隐含特征都不雷同)，照常渲染。
    为 EverOS/everalgo 将来产出真 summary、或插件侧合成注入预留。"""
    profiles = [
        {
            "profile_data": {
                "summary": "整体是个热爱户外、做事麻利的上班族",  # 独立总结
                "explicit_info": [
                    {"category": "户外爱好", "description": "喜欢爬山"},
                ],
                "implicit_traits": [
                    {"trait": "行动力强", "description": "想到就做"},
                ],
            }
        }
    ]
    text = build_text(profiles, [], None)
    assert "总体印象：整体是个热爱户外、做事麻利的上班族" in text


def test_build_text_overall_impression_overrides_everos_summary():
    """整体印象覆盖：提供 overall_impression(插件合成的 k_makise 视角印象)→ 作为【总体印象】，
    且彻底取代 EverOS 的伪 summary(即便后者与 explicit 雷同也不再出现)。"""
    dup = "周末常去城郊爬山"
    profiles = [
        {
            "profile_data": {
                "summary": dup,  # everalgo 伪 summary
                "explicit_info": [{"category": "户外爱好", "description": dup}],
                "implicit_traits": [{"trait": "行动力强", "description": "想到就做"}],
            }
        }
    ]
    synth = "这是个嘴上嫌麻烦、却把每件小事都默默记在心上的人"
    text = build_text(profiles, [], None, overall_impression=synth)
    assert f"总体印象：{synth}" in text
    assert "显式信息：" in text  # 显式/隐含照常渲染
    assert "- [户外爱好] " + dup in text
    assert text.count("总体印象：") == 1  # 只此一处总体印象，伪 summary 不再出现


def test_build_text_episodes_with_time():
    eps = [{"timestamp": 1716885133000, "summary": "循环 Aimer 新专辑"}]
    text = build_text([], eps, None)
    assert "【相关情景记忆】" in text
    assert "循环 Aimer 新专辑" in text
    assert "2024-05-28" in text  # 毫秒时间戳被格式化


def test_episode_prefers_full_content_over_truncated_summary():
    """EverOS 的 episode summary 实为 content[:200] 句中硬截；注入应改用完整 content（按句收束），
    绝不注入半句。这是「相关情景记忆暴力截断」的回归。"""
    content = "用户去看了 Aimer 的演唱会。返场时全场合唱，气氛热烈到落泪。散场后仍在回味。"
    # summary 模拟引擎 content[:N] 的句中硬截（结尾无句末标点）
    summary = "用户去看了 Aimer 的演唱会。返场时全场合唱，气氛热烈到落"
    ep = {"timestamp": 1716885133000, "content": content, "summary": summary}
    text = build_text([], [ep], None)
    line = next(ln for ln in text.splitlines() if ln.startswith("- ["))
    assert line.rstrip().endswith("。")  # 完整句收尾
    assert "散场后仍在回味" in line  # 用了完整 content
    assert not line.rstrip().endswith("气氛热烈到落")  # 不是 summary 的半句


def test_episode_long_content_clipped_at_sentence():
    """长 content 在句末标点处收束，绝不句中截断。"""
    out = _episode_text({"content": "甲乙丙丁戊。" * 50}, max_chars=20)
    assert len(out) <= 20
    assert out.endswith("。")
    assert out == "甲乙丙丁戊。" * 3  # 取整句、不留半截（3 句 18 字 ≤ 20）


def test_episode_fallback_content_then_summary_then_subject():
    """content 优先；缺则 summary（按句收束）；再缺则 subject；皆空 → ''。"""
    full = {"content": "有完整内容。", "summary": "S", "subject": "T"}
    assert _episode_text(full) == "有完整内容。"
    assert _episode_text({"summary": "只有摘要。", "subject": "T"}) == "只有摘要。"
    assert _episode_text({"subject": "只有标题"}) == "只有标题"
    assert _episode_text({}) == ""


def test_clip_to_sentence_boundaries():
    assert _clip_to_sentence("短句无需截。", 200) == "短句无需截。"  # ≤上限原样
    assert _clip_to_sentence("一。二。三。", 4) == "一。二。"  # 句末标点处收束
    assert _clip_to_sentence("一，二，三，四", 4) == "一，二，"  # 无句末→退到子句边界
    assert _clip_to_sentence("无任何标点的长串文本", 4) == "无任何标"  # 无任何边界→原窗口
    # 英文：. 后接空白才算句末（避免误切小数/缩写）
    assert _clip_to_sentence("First sentence. Second one. Third.", 20) == "First sentence."
    # 小数点(3.5)不被当句末 → 退到子句逗号边界
    assert _clip_to_sentence("收益约 3.5 倍，相当可观，后续仍看好。", 12) == "收益约 3.5 倍，"


def test_episode_english_content_clipped_at_sentence():
    """英文 episode content 按英文句末 . 收束，不退化成逗号半句（双语回归）。"""
    content = "The user woke up. The assistant evaluated the meal, noting it was fine. Done."
    out = _episode_text({"content": content}, max_chars=40)
    assert out == "The user woke up."  # 切在英文句号、完整句


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
