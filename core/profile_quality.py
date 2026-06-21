"""画像提取质量校验（任务：画像抽查/验收）。

EverOS 的 profile_data 由 LLM 生成，可能有结构缺陷或语用误判（如把"测试记忆"
误读为"用户健忘"）。本模块以**确定性规则**对单份 profile_data 做体检，输出
可量化的质量报告（score + issues），供 /epk quality 抽查或离线验收脚本调用。

不调 LLM、不调 EverOS（纯函数，分层不串味）；输入是 client.get(profile)
返回的 profiles[0]，校验其 profile_data。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import (
    PROFILE_FIELD_EXPLICIT,
    PROFILE_FIELD_IMPLICIT,
    PROFILE_FIELD_SUMMARY,
    PROFILE_KEY_DESCRIPTION,
    PROFILE_KEY_EVIDENCE,
    PROFILE_KEY_TRAIT,
)

# 严重度
SEVERITY_ERROR = "error"  # 结构性缺陷（必填缺失），扣分重
SEVERITY_WARN = "warn"  # 质量隐患（缺证据/冗余/过长），扣分轻

# 阈值（集中便于调参）
DESC_MAX_LEN = 120  # 单条 description 建议上限（字符）
SUMMARY_MAX_LEN = 200  # summary 建议上限
ERROR_PENALTY = 25  # 每个 error 扣分
WARN_PENALTY = 8  # 每个 warn 扣分


@dataclass
class Issue:
    """一条质量问题。"""

    severity: str
    code: str  # 机器可读标识，如 missing_summary
    message: str  # 人类可读说明（中文）


@dataclass
class QualityReport:
    """单份画像的质量体检结果。"""

    score: int  # 0~100，100 为无问题
    issues: list[Issue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)  # explicit/implicit 条数等

    @property
    def ok(self) -> bool:
        """无 error 级问题即视为通过验收（warn 不阻断）。"""
        return all(i.severity != SEVERITY_ERROR for i in self.issues)


def check_profile(profile: dict[str, Any]) -> QualityReport:
    """对单份 profile（client.get(profile) 的 profiles[0]）做质量体检。

    校验维度：
      1. 必填完整性：summary 非空；explicit_info / implicit_traits 至少一类非空。
      2. 结构有效性：每条 explicit_info 有 description；每条 implicit_trait 有 trait。
      3. 潜在幻觉：trait/explicit_info 缺 evidence（无溯源依据，可能是 LLM 臆测）。
      4. 冗余：implicit_traits 出现重复 trait 名。
      5. 冗长：summary / description 超长。
    """
    data = profile.get("profile_data", profile)
    issues: list[Issue] = []
    if not isinstance(data, dict):
        return QualityReport(
            score=0,
            issues=[Issue(SEVERITY_ERROR, "bad_shape", "profile_data is not a structured object")],
        )

    explicit = [x for x in (data.get(PROFILE_FIELD_EXPLICIT) or []) if isinstance(x, dict)]
    implicit = [x for x in (data.get(PROFILE_FIELD_IMPLICIT) or []) if isinstance(x, dict)]

    issues += _check_required(data, explicit, implicit)
    issues += _check_structure(explicit, implicit)
    issues += _check_evidence(explicit, implicit)
    issues += _check_duplicates(implicit)
    issues += _check_length(data, explicit, implicit)

    score = _score(issues)
    stats = {
        "explicit_count": len(explicit),
        "implicit_count": len(implicit),
        "error_count": sum(1 for i in issues if i.severity == SEVERITY_ERROR),
        "warn_count": sum(1 for i in issues if i.severity == SEVERITY_WARN),
    }
    return QualityReport(score=score, issues=issues, stats=stats)


def _score(issues: list[Issue]) -> int:
    """100 减去加权扣分，下限 0。"""
    penalty = sum(
        ERROR_PENALTY if i.severity == SEVERITY_ERROR else WARN_PENALTY for i in issues
    )
    return max(0, 100 - penalty)


def _check_required(data: dict, explicit: list, implicit: list) -> list[Issue]:
    out: list[Issue] = []
    summary = data.get(PROFILE_FIELD_SUMMARY)
    if not (isinstance(summary, str) and summary.strip()):
        out.append(Issue(SEVERITY_ERROR, "missing_summary", "missing summary"))
    if not explicit and not implicit:
        out.append(
            Issue(SEVERITY_ERROR, "no_traits", "both explicit_info and implicit_traits empty")
        )
    return out


def _check_structure(explicit: list, implicit: list) -> list[Issue]:
    out: list[Issue] = []
    for idx, item in enumerate(explicit):
        if not (item.get(PROFILE_KEY_DESCRIPTION) or "").strip():
            msg = f"explicit_info #{idx + 1} missing description"
            out.append(Issue(SEVERITY_ERROR, "explicit_no_desc", msg))
    for idx, item in enumerate(implicit):
        if not (item.get(PROFILE_KEY_TRAIT) or "").strip():
            msg = f"implicit_trait #{idx + 1} missing trait name"
            out.append(Issue(SEVERITY_ERROR, "trait_no_name", msg))
    return out


def _check_evidence(explicit: list, implicit: list) -> list[Issue]:
    """缺 evidence = 无溯源依据，标记为潜在幻觉（warn）。"""
    out: list[Issue] = []
    for idx, item in enumerate(explicit):
        if not (item.get(PROFILE_KEY_EVIDENCE) or "").strip():
            msg = f"explicit_info #{idx + 1} missing evidence"
            out.append(Issue(SEVERITY_WARN, "explicit_no_evidence", msg))
    for idx, item in enumerate(implicit):
        if not (item.get(PROFILE_KEY_EVIDENCE) or "").strip():
            trait = (item.get(PROFILE_KEY_TRAIT) or f"#{idx + 1}").strip()
            msg = f"trait '{trait}' missing evidence (possible fabrication)"
            out.append(Issue(SEVERITY_WARN, "trait_no_evidence", msg))
    return out


def _check_duplicates(implicit: list) -> list[Issue]:
    out: list[Issue] = []
    seen: set[str] = set()
    for item in implicit:
        trait = (item.get(PROFILE_KEY_TRAIT) or "").strip()
        if not trait:
            continue
        if trait in seen:
            out.append(Issue(SEVERITY_WARN, "duplicate_trait", f"trait '{trait}' is duplicated"))
        seen.add(trait)
    return out


def _check_length(data: dict, explicit: list, implicit: list) -> list[Issue]:
    out: list[Issue] = []
    summary = data.get(PROFILE_FIELD_SUMMARY) or ""
    if isinstance(summary, str) and len(summary) > SUMMARY_MAX_LEN:
        msg = f"summary too long ({len(summary)}>{SUMMARY_MAX_LEN})"
        out.append(Issue(SEVERITY_WARN, "summary_too_long", msg))
    for item in explicit + implicit:
        desc = item.get(PROFILE_KEY_DESCRIPTION) or ""
        if isinstance(desc, str) and len(desc) > DESC_MAX_LEN:
            msg = f"a description is too long ({len(desc)}>{DESC_MAX_LEN})"
            out.append(Issue(SEVERITY_WARN, "desc_too_long", msg))
    return out


def format_report(report: QualityReport) -> str:
    """渲染为命令可直接输出的英文报告。"""
    verdict = "PASS" if report.ok else "FAIL (structural defects)"
    lines = [
        f"Profile quality score: {report.score}/100 — {verdict}",
        f"explicit: {report.stats.get('explicit_count', 0)} / "
        f"implicit: {report.stats.get('implicit_count', 0)} / "
        f"issues: {report.stats.get('error_count', 0)} errors, "
        f"{report.stats.get('warn_count', 0)} warnings",
    ]
    if not report.issues:
        lines.append("✅ No quality issues found")
        return "\n".join(lines)
    for i in report.issues:
        mark = "❌" if i.severity == SEVERITY_ERROR else "⚠️"
        lines.append(f"{mark} {i.message}")
    return "\n".join(lines)


