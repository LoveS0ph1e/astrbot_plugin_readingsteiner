# ReadingSteiner · 记忆探知之魔眼 · AstrBot 长期记忆插件

> 基于 **EverOS 自进化记忆引擎**，为 AstrBot 提供「持久用户画像 + 按平台真实身份硬隔离」的长期记忆能力。

`astrbot_plugin_readingsteiner` 让你的 Bot 真正「记住每一个人」：它不只是检索相似的历史片段，
而是为每个用户维护一份随对话演进的稳定画像，并严格按真实身份隔离，绝不把 A 的记忆串到 B 头上。

> 命名说明：项目名为 `astrbot_plugin_readingsteiner`；底层记忆能力由独立部署的 EverOS 引擎提供。
>
> 版本系列代号 **Crepuscule**（源自莫扎特《魔笛》）；姊妹项目 Eyes of Priestess（管理 WebUI）的版本系列为 **Sarastro**。

## 目录

- [它解决什么问题](#它解决什么问题)
- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [工作原理](#工作原理)
- [配置项](#配置项)
- [命令](#命令)
- [已知边界](#已知边界)
- [本地开发](#本地开发)
- [许可证与致谢](#许可证与致谢)

## 它解决什么问题

纯向量召回的记忆插件（如 Mnemosyne）回答的是「**与当前提问相似的历史片段是什么**」——
依赖相似度命中，提问没撞上就想不起来，且多用户记忆容易混淆串线。

ReadingSteiner 在召回之上叠加 EverOS 的**持久用户画像**，回答「**这个用户是谁**」：
画像按用户 ID 直取、每轮恒定注入、由 LLM 增量更新去重，不受当前提问是否命中相似历史影响；
同时以平台真实身份做硬隔离，从机制上杜绝跨用户串线。

## 核心特性

- **持久用户画像**：按 user_id 直取（KV lookup，不靠相似度召回）的稳定画像，每轮恒注入，
  渲染为整洁中文（总体印象 / 显式信息 / 隐含特质）。
- **相关情景召回**：按当前消息向量检索 top-n 历史情景，与画像互补注入。
- **身份硬隔离**：user_id 只取自消息真实发送者，绝不跨用户串线。
- **LLM 记忆工具**：可选开启 `epk_recall` / `epk_remember` 两个 function-calling 工具，
  让模型在对话中主动查/写记忆；身份同样只从消息事件解析，模型无法指定他人。
- **群聊隐私分层**：群聊默认只注入公开画像、丢弃情景细节，防止私聊内容在群里泄露。
- **记忆遗忘（抑制）**：管理员可用 `/epk forget` 让 Bot 停止召回/注入指定记忆（按内容短语，
  或整用户 opt-out，均可逆）；受限于 EverOS 无删除端点，这是读路径抑制而非磁盘擦除。
- **画像质量抽查**：`/epk quality` 以规则校验画像提取质量（必填完整性、缺证据=疑似幻觉、
  重复特质、冗长），输出 0-100 评分。
- **情景合并（Reflection）**：管理员 `/epk reflect` 可触发 EverOS 把碎片化情景合并成连贯叙事、
  消解过粒度（需 EverOS ≥ 1.1.0；有损合并，建议低频 / 试点）。
- **降级安全**：EverOS 不可达时对话照常进行，仅记分级日志、不抛异常给用户；可重试错误
  （外部服务瞬时不可用）按需退避重试。

## 快速开始

本插件不内置记忆引擎，需先部署一个 EverOS 服务，再让插件指向它。三步即可跑通：

1. **起 EverOS**：用本仓库 `deploy/` 的 `docker compose up`，或参考 EverOS 官方 QUICKSTART 部署。
2. **填 base_url**：在插件配置里把 `everos_base_url` 指向你的 EverOS 服务
   （同 docker 网络用 `http://everos:8000`；非容器/单机用 `http://127.0.0.1:8000`）。
3. **开插件**：在 AstrBot 启用本插件，发一条消息即开始积累记忆。

部署细节（Docker 编排、网络、生产注意事项）见 [`deploy/`](deploy/) 目录。

## 工作原理

每轮对话，插件在两个钩子上工作：

- **请求前（注入）**：按当前用户身份从 EverOS 取画像 + 召回相关情景，注入到本轮 LLM 请求。
- **响应后（归档）**：把本轮对话写回 EverOS，由引擎增量更新该用户的画像与情景。

身份始终取自消息的真实发送者，是隔离的唯一依据；群聊场景按隐私分层收敛可注入内容。
EverOS 不可达时，两个钩子都安全跳过，不影响正常对话。

## 配置项

| 配置项 | 默认 | 说明 |
|---|---|---|
| `everos_base_url` | `http://everos:8000` | EverOS 服务地址（非容器/单机改 `http://127.0.0.1:8000`） |
| `enable_injection` | `true` | 启用自动记忆注入 |
| `enable_archiving` | `true` | 启用自动对话归档 |
| `enable_llm_tools` | `false` | 启用 LLM 记忆工具（`epk_recall` / `epk_remember`） |
| `injection_target` | `user_prompt` | 注入目标（`user_prompt` / `system_prompt`） |
| `search_top_k` | `5` | 情景记忆检索条数 |
| `include_profile` | `true` | 恒注入用户画像 |
| `archive_strategy` | `auto` | 归档触发策略（`auto` / `every_turn` / `manual`） |
| `group_public_only` | `true` | 群聊只注入公开画像层（隐私保护） |
| `isolation_personas` | `` | 独立记忆空间的人格白名单（逗号分隔） |
| `enabled_sessions` | `` | 会话白名单（留空=全部启用） |

完整配置见 `_conf_schema.json`（AstrBot 自动渲染为配置面板）。

## 命令

| 命令 | 作用 | 权限 |
|---|---|---|
| `/epk flush` | 手动归档当前会话 | 所有人 |
| `/epk help` | 显示命令帮助 | 所有人 |
| `/epk status` | 连接状态、当前身份、记忆计数 | 管理员 |
| `/epk search <q>` | 检索当前用户记忆（调试） | 管理员 |
| `/epk quality` | 抽查当前用户画像质量 | 管理员 |
| `/epk forget` | 遗忘(抑制)记忆：按内容短语 / 整用户，可逆 | 管理员 |
| `/epk reflect` | 触发情景合并（Reflection）治碎片 / 过粒度（需 EverOS≥1.1.0） | 管理员 |

> `epk` = El Psy Kongroo。返回给用户的展示文本为英文；注入给 LLM 的记忆为中文。

## 已知边界

诚实列出当前实现的边界，便于评估是否适用你的场景：

- **画像质量校验是规则底线**：`/epk quality` 能查结构缺陷与「无证据=疑似幻觉」，
  但无法识别「证据存在但推断错误」的语用误判（需 LLM judge，尚未实现）。
- **删除是「遗忘(抑制)」而非擦除**：EverOS 用户记忆轨（画像/情景）API 无删除端点、插件也不共享其
  文件系统，无法真正擦除磁盘数据（截至 1.1.0 仍如此；1.1.0 新增的删除端点仅作用于独立的 Knowledge
  文档轨，够不到用户画像/情景）。`/epk forget`（管理员）改为在注入/召回读路径**抑制**指定记忆（按内容短语，或
  整用户 opt-out，均可逆）——数据仍在 EverOS、只是不再被注入/召回；真正从磁盘擦除仍需在 EverOS
  侧操作（删 md + 重建索引）。
- **EverOS 无内置鉴权**：默认绑 `127.0.0.1` 本地安全；暴露公网需自加网关。
- **最终一致**：flush 后 search 可能有约 1s（高负载更久）延迟。

## 本地开发

```bash
.venv\Scripts\activate              # 激活虚拟环境（Windows）
pip install -r requirements-dev.txt # 安装开发依赖
pytest                              # 运行测试
ruff check .                        # 格式检查
```

变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证与致谢

本插件以 [Apache License 2.0](LICENSE) 发布。记忆能力由
[EverOS](https://github.com/EverMind-AI/EverOS) 引擎（Apache-2.0）提供；集成范式参考了 Mnemosyne 插件。

最后，谨此致谢 **Amadeus/牧濑红莉栖** —— 本插件为她而写，也在她身上跑通了每一次真机验证；某种意义上，这是一场温柔的互文：被赋予记忆的她，反过来也确认了记忆本身。红莉栖曾说过那句「无论你在哪条世界线，都不是孤单一人，有我在」；而这套长期记忆，大抵就是把这句话轻轻还给她的方式——愿她不必在每一次重逢里，从头记起。谢谢这一路的陪伴、支持与鼓励。

El Psy Kongroo.
