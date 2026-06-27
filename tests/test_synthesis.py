"""整体印象合成测试（synthesis.py）：注入式 chat_fn，asyncio.run 跑协程，无网络。"""

from __future__ import annotations

import asyncio

from core.synthesis import synthesize_impression


def _exp(*descs):
    return [{"category": "爱好", "description": d} for d in descs]


def _imp(*traits):
    return [{"trait": t, "description": "略"} for t in traits]


def _run(coro):
    return asyncio.run(coro)


def test_synthesize_success_and_clean():
    calls = []

    async def chat(prompt: str) -> str:
        calls.append(prompt)
        return "  「一个嘴硬心软、把约定当真的人」  "

    out = _run(
        synthesize_impression(
            _exp("爱爬山"), _imp("行动力强"), chat_fn=chat, persona_name="测试人格", max_chars=80
        )
    )
    assert out == "一个嘴硬心软、把约定当真的人"  # 去引号/首尾空白
    assert len(calls) == 1
    # 给定事实/特质确实进了 prompt（合成只依据它们）
    assert "爱爬山" in calls[0]
    assert "行动力强" in calls[0]


def test_empty_profile_skips_llm():
    calls = []

    async def chat(prompt: str) -> str:
        calls.append(prompt)
        return "不该被调用"

    out = _run(synthesize_impression([], [], chat_fn=chat, persona_name="测试人格"))
    assert out == ""
    assert calls == []  # 空画像不触发 LLM（省钱）


def test_llm_failure_returns_empty():
    async def chat(prompt: str) -> str:
        raise RuntimeError("LLM down")

    assert _run(synthesize_impression(_exp("x"), [], chat_fn=chat, persona_name="测试人格")) == ""


def test_blank_response_returns_empty():
    async def chat(prompt: str) -> str:
        return "   \n  "

    assert _run(synthesize_impression(_exp("x"), [], chat_fn=chat, persona_name="测试人格")) == ""


def test_clean_strips_prefix_and_takes_first_line():
    async def chat(prompt: str) -> str:
        return "整体印象：这是核心印象那一句\n这是多余的第二行"

    out = _run(synthesize_impression(_exp("x"), [], chat_fn=chat, persona_name="测试人格"))
    assert out == "这是核心印象那一句"


def test_none_inputs_safe():
    async def chat(prompt: str) -> str:
        return "印象"

    # explicit/implicit 传 None 不应崩；都空 → 不调 LLM → ''
    assert _run(synthesize_impression(None, None, chat_fn=chat, persona_name="测试人格")) == ""
