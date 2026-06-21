#!/usr/bin/env python3
"""任务0 实测探针：探测 EverOS 对『深羁绊+多面向』用户印象的提取质量。

用法（先起好 EverOS 服务，填好 .env 的 key）：
    python experiments/probe_everos_profile.py --base-url http://127.0.0.1:8000

做什么（对照 03-构建任务清单.md 任务0）：
    1. 读 sample_dialogue.json
    2. POST /api/v1/memory/add  灌入多轮对话（timestamp 用 Unix 毫秒）
    3. POST /api/v1/memory/flush 强制提取（触发一次 LLM extraction）
    4. POST /api/v1/memory/search 带 include_profile=true，多个查询角度
    5. 把 profiles[].profile_data + episodes 原样 dump 出来，供人工判断画像质量

契约出处：01-实证依据.md 第二部分（2.1 响应包络 / 2.2 add / 2.3 flush / 2.4 search）。
本脚本纯 httpx，不依赖 AstrBot；输出落 experiments/everos-profile-probe.md。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
SAMPLE_PATH = HERE / "sample_dialogue.json"
REPORT_PATH = HERE / "everos-profile-probe.md"

# search 用的多角度查询：分别探 五类目 是否被提炼进画像/情景
QUERIES = [
    "这个用户的作息和生活习惯是怎样的？",
    "这个用户喜欢什么音乐、喝什么咖啡？",
    "这个用户的情感状态和内心需求是什么？",
    "这个用户和我（assistant）是什么关系？",
    "关于吉他，这个用户说过什么？",
]


def _post(client: httpx.Client, base_url: str, path: str, payload: dict) -> dict:
    """统一 POST：发请求 → raise_for_status → 取 data（响应包络见 01 §2.1）。"""
    resp = client.post(f"{base_url}{path}", json=payload)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"EverOS error @ {path}: {body['error']}")
    return body.get("data", {})


def build_messages(sample: dict) -> list[dict]:
    """把样本对话转成 MessageItem 列表。
    ⚠️ user 消息 sender_id = user_id（索引键）；assistant 用稳定 bot 标识。
    ⚠️ timestamp = Unix 毫秒 int，逐条递增保证有序（01 §2.2）。"""
    meta = sample["_meta"]
    user_id = meta["user_id"]
    bot_id = meta["bot_id"]
    base_ms = int(time.time() * 1000) - len(sample["turns"]) * 10_000
    messages = []
    for i, turn in enumerate(sample["turns"]):
        is_user = turn["role"] == "user"
        messages.append(
            {
                "sender_id": user_id if is_user else bot_id,
                "role": "user" if is_user else "assistant",
                "timestamp": base_ms + i * 10_000,
                "content": turn["text"],
            }
        )
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description="EverOS profile 提取质量探针")
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="EverOS 服务地址（默认 127.0.0.1:8000）"
    )
    parser.add_argument("--app-id", default="default")
    parser.add_argument("--project-id", default="default")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--settle", type=float, default=3.0, help="flush 后等待索引落地的秒数（最终一致，01 §1.3）"
    )
    args = parser.parse_args()

    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    meta = sample["_meta"]
    user_id = meta["user_id"]
    session_id = meta["session_id"]
    base_url = args.base_url.rstrip("/")
    scope = {"app_id": args.app_id, "project_id": args.project_id}

    report: list[str] = []

    def out(line: str = "") -> None:
        print(line)
        report.append(line)

    out("# EverOS Profile 提取质量实测记录（任务0）\n")
    out(f"- base_url: `{base_url}`")
    out(f"- user_id: `{user_id}` / session_id: `{session_id}` / scope: `{scope}`")
    out(f"- 样本: {len(sample['turns'])} 轮对话（脱敏，覆盖 §11.6 五类目信号）")
    out(f"- 运行时刻: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    with httpx.Client(timeout=120.0) as client:
        # 0. 健康检查
        try:
            h = client.get(f"{base_url}/health")
            out(f"## 0. 健康检查\n\n`GET /health` → {h.status_code} {h.text.strip()}\n")
        except httpx.HTTPError as e:
            out(f"**健康检查失败**：{e}\n服务没起或地址不对，终止。")
            REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
            return 2

        # 1. add
        messages = build_messages(sample)
        add_payload = {"session_id": session_id, **scope, "messages": messages}
        try:
            add_data = _post(client, base_url, "/api/v1/memory/add", add_payload)
        except (httpx.HTTPError, RuntimeError) as e:
            out(f"**add 失败**：{e}")
            REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
            return 3
        out(f"## 1. add（灌入 {len(messages)} 条消息）\n")
        out(f"```json\n{json.dumps(add_data, ensure_ascii=False, indent=2)}\n```\n")

        # 2. flush（触发 LLM 提取）
        try:
            flush_data = _post(
                client, base_url, "/api/v1/memory/flush", {"session_id": session_id, **scope}
            )
        except (httpx.HTTPError, RuntimeError) as e:
            out(f"**flush 失败**：{e}")
            REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
            return 4
        out("## 2. flush（强制提取）\n")
        out(f"```json\n{json.dumps(flush_data, ensure_ascii=False, indent=2)}\n```\n")

        out(f"_等待 {args.settle}s 让 LanceDB 索引落地（最终一致）……_\n")
        time.sleep(args.settle)

        # 3. search 多角度
        out(f"## 3. search（include_profile=true，{len(QUERIES)} 个查询角度）\n")
        first_profile_dump = None
        for i, q in enumerate(QUERIES, 1):
            search_payload = {
                "user_id": user_id,
                **scope,
                "query": q,
                # vector 而非 hybrid：DashScope 无 OpenAI 协议 rerank，hybrid 会触发 rerank。
                # 任务0 验证的是画像质量(LLM提取+embedding索引)，rerank 只影响 episode 排序，
                # 对 profile_data 零影响。生产代码 search_method 仍可配 hybrid（配 rerank key 后）。
                "method": "vector",
                "top_k": args.top_k,
                "include_profile": True,
            }
            try:
                data = _post(client, base_url, "/api/v1/memory/search", search_payload)
            except (httpx.HTTPError, RuntimeError) as e:
                out(f"### 查询 {i}: {q}\n\n**search 失败**：{e}\n")
                continue
            profiles = data.get("profiles", [])
            episodes = data.get("episodes", [])
            if first_profile_dump is None and profiles:
                first_profile_dump = profiles
            out(f"### 查询 {i}: {q}\n")
            out(f"- profiles: {len(profiles)} 条 / episodes: {len(episodes)} 条\n")
            ep_brief = [
                {"score": e.get("score"), "subject": e.get("subject"), "summary": e.get("summary")}
                for e in episodes
            ]
            out("**episodes（score/subject/summary）**:\n")
            out(f"```json\n{json.dumps(ep_brief, ensure_ascii=False, indent=2)}\n```\n")

        # 4. profile_data 完整 dump（画像质量判断的核心证据）
        out("## 4. profile_data 完整内容（画像质量核心证据）\n")
        if first_profile_dump:
            out(f"```json\n{json.dumps(first_profile_dump, ensure_ascii=False, indent=2)}\n```\n")
        else:
            out(
                "**未返回任何 profile**。可能原因：flush 后画像聚类尚未生成、"
                "或样本量不足以触发 profile 提取。可加大样本或多 flush 几轮再试。\n"
            )

        # 5. get profile 直取（KV lookup，不经相似度）
        out("## 5. get profile（KV 直取，memory_type=profile）\n")
        try:
            get_data = _post(
                client,
                base_url,
                "/api/v1/memory/get",
                {
                    "user_id": user_id,
                    **scope,
                    "memory_type": "profile",
                    "page": 1,
                    "page_size": 20,
                    "sort_by": "updated_at",
                    "sort_order": "desc",
                },
            )
            out(f"- total_count: {get_data.get('total_count')} / count: {get_data.get('count')}\n")
            out(f"```json\n{json.dumps(get_data, ensure_ascii=False, indent=2)}\n```\n")
        except (httpx.HTTPError, RuntimeError) as e:
            out(f"**get 失败**：{e}\n")

    out("## 6. 人工判断（待填）\n")
    out("- [ ] profile_data 是否稳定承载『深羁绊+多面向』印象？")
    out("- [ ] 比 Mnemosyne 每轮重新推断强多少？")
    out("- [ ] 结论：值得迁移 / 不值得（回到方案A）\n")

    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[报告已写入] {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
