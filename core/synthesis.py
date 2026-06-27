"""整体印象合成：从 EverOS 画像的 explicit/implicit 合成「k_makise 视角」的一句话整体印象。

为什么需要：everalgo 的 summary 是 explicit[0] 的逐字复制(非真总结)；本模块产出
真正的、人格感知的整体印象，由 relationship 层缓存、injection 层注入(取代伪 summary)。

分层不串味：本模块**不直接依赖 AstrBot/具体 provider**，而是收一个注入式 ``chat_fn``
(prompt → 回复文本)。真实 LLM 由 main.py 注入(包机器人现有 provider 或配置端点)；单测
传 fake chat_fn 即可，无网络。on-change 触发(见 relationship.is_stale)，故合成调用很少。

防新退化的约束(全写进 prompt)：仅依据给定事实/特质、k_makise 视角、一句话、≤max_chars、
不复述清单、不新增事实。任何失败(LLM 异常 / 空响应)→ 返回 ''，调用方回退「无整体印象」。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# prompt → 回复文本；由 main.py 注入真实 LLM，单测注入 fake。
ChatFn = Callable[[str], Awaitable[str]]

_PROMPT = """你是{persona}。下面是关于某个人的一组已知事实与隐含特质（均由过往对话提取）。
请**只依据**这些信息，用你的视角，为这个人写**一句**整体印象。

要求：
- 一句话，不超过 {max_chars} 字，不分点、不复述清单。
- 只能基于给定信息，**绝不新增**未提及的事实或主观臆测。
- 是「整体印象」而非罗列：抓住这个人最核心的样子（性格底色 / 与你的关系基调），而非堆事实。
- 这是给你自己看的内部印象，不是对话回复；保留你的语气底色即可，无需对谁说话。

【显式信息】
{explicit}

【隐含特质】
{implicit}

只输出那一句整体印象本身，不要任何前缀、解释或引号。"""


def _render_items(
    explicit: list[dict[str, Any]], implicit: list[dict[str, Any]]
) -> tuple[str, str]:
    """把 explicit/implicit 渲染成喂给 LLM 的紧凑清单（只取人设相关字段，丢溯源）。"""
    exp_lines = []
    for it in explicit:
        if not isinstance(it, dict):
            continue
        desc = (it.get("description") or "").strip()
        if not desc:
            continue
        cat = (it.get("category") or "").strip()
        exp_lines.append(f"- [{cat}] {desc}" if cat else f"- {desc}")
    imp_lines = []
    for it in implicit:
        if not isinstance(it, dict):
            continue
        trait = (it.get("trait") or "").strip()
        desc = (it.get("description") or "").strip()
        if not trait and not desc:
            continue
        imp_lines.append(f"- {trait}：{desc}".rstrip("：") if trait else f"- {desc}")
    return ("\n".join(exp_lines) or "（无）", "\n".join(imp_lines) or "（无）")


async def synthesize_impression(
    explicit_info: list[dict[str, Any]] | None,
    implicit_traits: list[dict[str, Any]] | None,
    *,
    chat_fn: ChatFn,
    persona_name: str,
    max_chars: int = 80,
) -> str:
    """合成一句 k_makise 视角整体印象；空画像不调 LLM；任何异常/空结果 → ''（安全降级）。

    persona_name：传给 LLM 的人格显示名（必须是真实角色名，由 main.py 从配置注入）。
    代码/字段一律用机器标识 k_makise；真实角色名只作运行期内容，存在于本参数与配置中。
    """
    explicit_info = explicit_info or []
    implicit_traits = implicit_traits or []
    if not explicit_info and not implicit_traits:
        return ""
    exp, imp = _render_items(explicit_info, implicit_traits)
    prompt = _PROMPT.format(persona=persona_name, max_chars=max_chars, explicit=exp, implicit=imp)
    try:
        raw = await chat_fn(prompt)
    except Exception:  # LLM 不可用/超时/任意失败 → 不阻断，回退无印象
        return ""
    return _clean(raw, max_chars)


def _clean(raw: str, max_chars: int) -> str:
    """清洗 LLM 输出：去首尾空白/引号、去「整体印象：」类前缀、只取首行、宽容截断。"""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    s = raw.strip().strip("“”「」『』\"'`").strip()
    for pre in ("整体印象：", "整体印象:", "印象：", "印象:"):
        if s.startswith(pre):
            s = s[len(pre) :].strip()
    s = s.splitlines()[0].strip() if s else s
    # 明显超长才截（留 20 字宽容，避免把正常一句话切断）
    if len(s) > max_chars + 20:
        s = s[: max_chars + 20].rstrip()
    return s
