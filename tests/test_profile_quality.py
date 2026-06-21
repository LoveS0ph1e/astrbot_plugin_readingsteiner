"""画像质量校验测试（profile_quality.py）：纯函数规则校验，无网络。"""

from __future__ import annotations

from core.profile_quality import (
    SEVERITY_ERROR,
    SEVERITY_WARN,
    check_profile,
    format_report,
)


def _codes(report):
    return {i.code for i in report.issues}


def test_healthy_profile_full_score():
    prof = {
        "profile_data": {
            "summary": "用户喜欢户外运动",
            "explicit_info": [{"category": "兴趣", "description": "爬山", "evidence": "说过X"}],
            "implicit_traits": [{"trait": "行动力强", "description": "迅速", "evidence": "依据Y"}],
        }
    }
    report = check_profile(prof)
    assert report.score == 100
    assert report.ok is True
    assert report.issues == []


def test_missing_summary_is_error():
    prof = {"profile_data": {"summary": "  ", "implicit_traits": [{"trait": "x", "evidence": "e"}]}}
    report = check_profile(prof)
    assert "missing_summary" in _codes(report)
    assert report.ok is False  # error 级阻断
    assert any(i.severity == SEVERITY_ERROR for i in report.issues)


def test_no_traits_at_all_is_error():
    report = check_profile({"profile_data": {"summary": "只有总结"}})
    assert "no_traits" in _codes(report)
    assert report.ok is False


def test_missing_evidence_is_warn_not_blocking():
    """缺证据=疑似臆测，warn 级，不阻断验收。"""
    prof = {
        "profile_data": {
            "summary": "s",
            "implicit_traits": [{"trait": "健忘", "description": "d"}],  # 无 evidence
        }
    }
    report = check_profile(prof)
    assert "trait_no_evidence" in _codes(report)
    assert report.ok is True  # warn 不阻断
    assert report.score < 100  # 但扣分


def test_explicit_missing_description_is_error():
    prof = {
        "profile_data": {
            "summary": "s",
            "explicit_info": [{"category": "兴趣", "evidence": "e"}],  # 无 description
        }
    }
    report = check_profile(prof)
    assert "explicit_no_desc" in _codes(report)
    assert report.ok is False


def test_duplicate_trait_is_warn():
    prof = {
        "profile_data": {
            "summary": "s",
            "implicit_traits": [
                {"trait": "健忘", "description": "a", "evidence": "e1"},
                {"trait": "健忘", "description": "b", "evidence": "e2"},
            ],
        }
    }
    report = check_profile(prof)
    assert "duplicate_trait" in _codes(report)


def test_over_long_summary_is_warn():
    prof = {
        "profile_data": {
            "summary": "长" * 250,
            "implicit_traits": [{"trait": "x", "evidence": "e"}],
        }
    }
    report = check_profile(prof)
    assert "summary_too_long" in _codes(report)


def test_bad_shape_zero_score():
    report = check_profile({"profile_data": "不是dict"})
    assert report.score == 0
    assert "bad_shape" in _codes(report)


def test_score_monotonic_with_issues():
    """问题越多分越低。"""
    clean = check_profile(
        {
            "profile_data": {
                "summary": "s",
                "implicit_traits": [{"trait": "t", "evidence": "e"}],
            }
        }
    )
    dirty = check_profile(
        {"profile_data": {"summary": "", "implicit_traits": [{"trait": "t"}]}}
    )
    assert clean.score > dirty.score


def test_format_report_renders_chinese():
    report = check_profile({"profile_data": {"summary": "", "implicit_traits": []}})
    out = format_report(report)
    assert "画像质量评分" in out
    assert "不通过" in out  # 含 error
    assert any(sev in out for sev in ("❌", "⚠️"))


def test_warn_count_in_stats():
    prof = {
        "profile_data": {
            "summary": "s",
            "implicit_traits": [{"trait": "x", "description": "d"}],  # 缺 evidence → warn
        }
    }
    report = check_profile(prof)
    assert report.stats["warn_count"] >= 1
    assert report.stats["error_count"] == 0
    assert any(i.severity == SEVERITY_WARN for i in report.issues)

