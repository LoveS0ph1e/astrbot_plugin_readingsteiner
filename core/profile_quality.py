"""画像提取质量校验（任务：画像抽查/验收）。

EverOS 的 profile_data 由 LLM 生成，可能有结构缺陷或语用误判（如把"测试记忆"
误读为"用户健忘"）。本模块以**确定性规则**对单份 profile_data 做体检，输出
可量化的质量报告（score + issues），供 /epk quality 抽查或离线验收脚本调用。

不调 LLM、不调 EverOS（纯函数，05 §三 分层不串味）；输入是 client.get(profile)
返回的 profiles[0]，校验其 profile_data。规则对照 01 §1.1 的实测 schema。
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
            issues=[Issue(SEVERITY_ERROR, "bad_shape", "profile_data 不是结构化对象，无法校验")],
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
        out.append(Issue(SEVERITY_ERROR, "missing_summary", "缺少总体印象 summary"))
    if not explicit and not implicit:
        out.append(
            Issue(SEVERITY_ERROR, "no_traits", "显式信息与隐含特质均为空，画像无实质内容")
        )
    return out


def _check_structure(explicit: list, implicit: list) -> list[Issue]:
    out: list[Issue] = []
    for idx, item in enumerate(explicit):
        if not (item.get(PROFILE_KEY_DESCRIPTION) or "").strip():
            out.append(
                Issue(SEVERITY_ERROR, "explicit_no_desc", f"显式信息第 {idx + 1} 条缺 description")
            )
    for idx, item in enumerate(implicit):
        if not (item.get(PROFILE_KEY_TRAIT) or "").strip():
            out.append(
                Issue(SEVERITY_ERROR, "trait_no_name", f"隐含特质第 {idx + 1} 条缺 trait 名")
            )
    return out


def _check_evidence(explicit: list, implicit: list) -> list[Issue]:
    """缺 evidence = 无溯源依据，标记为潜在幻觉（warn）。"""
    out: list[Issue] = []
    for idx, item in enumerate(explicit):
        if not (item.get(PROFILE_KEY_EVIDENCE) or "").strip():
            out.append(
                Issue(SEVERITY_WARN, "explicit_no_evidence", f"显式信息第 {idx + 1} 条缺证据溯源")
            )
    for idx, item in enumerate(implicit):
        if not (item.get(PROFILE_KEY_EVIDENCE) or "").strip():
            trait = (item.get(PROFILE_KEY_TRAIT) or f"第{idx + 1}条").strip()
            out.append(
                Issue(SEVERITY_WARN, "trait_no_evidence", f"特质「{trait}」缺证据溯源（疑似臆测）")
            )
    return out


def _check_duplicates(implicit: list) -> list[Issue]:
    out: list[Issue] = []
    seen: set[str] = set()
    for item in implicit:
        trait = (item.get(PROFILE_KEY_TRAIT) or "").strip()
        if not trait:
            continue
        if trait in seen:
            out.append(Issue(SEVERITY_WARN, "duplicate_trait", f"特质「{trait}」重复出现"))
        seen.add(trait)
    return out


def _check_length(data: dict, explicit: list, implicit: list) -> list[Issue]:
    out: list[Issue] = []
    summary = data.get(PROFILE_FIELD_SUMMARY) or ""
    if isinstance(summary, str) and len(summary) > SUMMARY_MAX_LEN:
        msg = f"summary 过长（{len(summary)}>{SUMMARY_MAX_LEN}）"
        out.append(Issue(SEVERITY_WARN, "summary_too_long", msg))
    for item in explicit + implicit:
        desc = item.get(PROFILE_KEY_DESCRIPTION) or ""
        if isinstance(desc, str) and len(desc) > DESC_MAX_LEN:
            msg = f"某条 description 过长（{len(desc)}>{DESC_MAX_LEN}）"
            out.append(Issue(SEVERITY_WARN, "desc_too_long", msg))
    return out


def format_report(report: QualityReport) -> str:
    """渲染为命令可直接输出的中文报告。"""
    verdict = "通过" if report.ok else "不通过（含结构性缺陷）"
    lines = [
        f"画像质量评分：{report.score}/100 — {verdict}",
        f"显式信息 {report.stats.get('explicit_count', 0)} 条 / "
        f"隐含特质 {report.stats.get('implicit_count', 0)} 条 / "
        f"问题 {report.stats.get('error_count', 0)} 错 {report.stats.get('warn_count', 0)} 警",
    ]
    if not report.issues:
        lines.append("✅ 未发现质量问题")
        return "\n".join(lines)
    for i in report.issues:
        mark = "❌" if i.severity == SEVERITY_ERROR else "⚠️"
        lines.append(f"{mark} {i.message}")
    return "\n".join(lines)


