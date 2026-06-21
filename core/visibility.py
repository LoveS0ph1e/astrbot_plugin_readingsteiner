"""visibility 隐私分层（02 §五）。

EverOS schema 不支持自定义可见性标签（01 §1.3），故隐私分层靠本插件旁路实现。

MVP 实现方案 A 的粗粒度版：群聊时只保留画像、跳过情景细节（episode 常含具体事件，
更易泄露隐私）。细粒度方案 B（user_id → visibility 规则本地表，对应审计 §11.6 五类目
TASTE/IDENTITY/ROUTINE/VULNERABILITY/BOND）留作 v1.1，在此预留接口。

本模块不调 EverOS、不写 EverOS（旁路过滤，05 §三）。
"""
from __future__ import annotations

from typing import Any


def filter_public(
    profiles: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """群聊公开层过滤（方案 A，MVP）。

    群聊场景调用：保留画像（长期印象相对安全），丢弃情景细节（episode 含具体事件，
    封堵审计『事故 Z』式的私聊内容在群聊泄露）。
    返回过滤后的 (profiles, episodes)。
    """
    return profiles, []


# ── v1.1 扩展点（方案 B）──
# def filter_by_taxonomy(profiles, episodes, user_id, is_group, rules_table):
#     """按 user_id 的 visibility 规则表（五类目）逐条过滤。待 v1.1 实现。"""
#     ...
