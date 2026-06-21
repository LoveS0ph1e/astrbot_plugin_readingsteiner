# Docker 部署与开箱即用

> 本文件定义本插件如何配合 Docker 实现「尽量开箱即用」。
> **部署形态已锁定**（基于用户实际环境）：AstrBot 跑在 Docker 里 + 用户能接受一次手动 `docker compose up`。
> 据此选定：**插件做纯客户端，仓库随附 docker-compose，EverOS 与 AstrBot 同处一个 docker 网络。插件不调 docker、不内嵌引擎。**
> 所有 EverOS 部署细节来自源码实证（`.env.example` / `pyproject.toml` / `QUICKSTART.md`），已标注。

---

## 一、为什么是这个形态（决策依据）

| 候选 | 为何否决/采纳 |
|---|---|
| 插件内嵌 EverOS 引擎 | ❌ EverOS 硬约束：`QUICKSTART.md` 明文「There is no in-process library mode; an everos server is always in front of your agent」。它只能作为独立服务运行。 |
| 插件自动 `docker compose up` 拉起容器 | ❌ AstrBot 自己在容器里，插件要调 docker 得挂 docker socket，有安全代价、配置别扭、跨平台坑多。用户已明确「一次手动 up 可接受」，无需为全自动付这个代价。 |
| **插件纯客户端 + 随附 compose + 同 docker 网络** | ✅ **采纳**。EverOS 和 AstrBot 在同一 compose/网络里，插件用服务名连（`http://everos:8000`），不碰宿主机 IP，不碰 docker 命令。最稳健，且 AstrBot 在容器里反而让「同网络」天然成立。 |

**"开箱即用"在本方案里的定义**：用户 `docker compose up -d` 一次（EverOS + 可选 AstrBot 一起起），在插件配置面板填两个 API key，插件自动连上并工作。中间不需要敲 EverOS 的任何命令，也不需要懂 EverOS 内部。

---

## 二、EverOS 容器化的实证事实（写 Dockerfile/compose 的依据）

| 事实 | 值 | 出处 |
|---|---|---|
| 包名 / 版本 | `everos` 1.0.1（PyPI 有发布，`pip install everos`） | `pyproject.toml:2-3`；`README.md:137` |
| Python 要求 | >= 3.12 | `pyproject.toml:7` |
| CLI 入口 | `everos = everos.entrypoints.cli.main:app` | `pyproject.toml:110-111` |
| 启动命令 | `everos server start` | `QUICKSTART.md`；`README.md:159` |
| 默认绑定 | `127.0.0.1:8000` | `QUICKSTART.md:69`；`.env.example` HTTP API 段 |
| ⚠️ 容器内必须改绑定 | `EVEROS_API__HOST=0.0.0.0` 否则同网络其它容器连不上 | `.env.example`：「Set HOST=0.0.0.0 only after... gateway」 |
| 端口可配 | `EVEROS_API__PORT=8000` | `.env.example` HTTP API 段 |
| 数据目录 | `~/.everos`（md + `.index/` LanceDB + `.system.db` SQLite） | `.env.example` Storage 段；`docs/storage_layout.md` |
| 数据目录可配 | `EVEROS_MEMORY__ROOT=~/.everos` | `.env.example` Storage 段 |
| 配置查找顺序 | `--env-file` → `./.env` → `~/.config/everos/.env` → `~/.everos/.env` | `QUICKSTART.md:56`；`README.md:174` |
| 必需的两个外部 key | OpenRouter（LLM+多模态共用）、DeepInfra（embedding+rerank 共用） | `QUICKSTART.md` Prerequisites |
| 无内置鉴权 | 默认 loopback；暴露需自加网关 | `.env.example`；`docs/api.md:55-60` |

**四组模型环境变量（两个 key 填四个槽，`.env.example` 实证）**：
```
EVEROS_LLM__API_KEY          (OpenRouter)   EVEROS_LLM__MODEL=openai/gpt-4.1-mini
EVEROS_MULTIMODAL__API_KEY   (OpenRouter)   EVEROS_MULTIMODAL__MODEL=google/gemini-3-flash-preview
EVEROS_EMBEDDING__API_KEY    (DeepInfra)    EVEROS_EMBEDDING__MODEL=Qwen/Qwen3-Embedding-4B
EVEROS_RERANK__API_KEY       (DeepInfra)    EVEROS_RERANK__MODEL=Qwen/Qwen3-Reranker-4B
```
> 也支持阿里百炼 DashScope（一个 key 覆盖全部），`.env.example` 里有注释掉的备选行。文档要把两种都告诉用户。

---

## 三、随附文件清单（放插件仓库的 `deploy/` 下）

```
astrbot_plugin_everos/
└── deploy/
    ├── Dockerfile            # 现 build EverOS 镜像（基于 python:3.12-slim，pip install everos）
    ├── docker-compose.yml    # EverOS 服务 + 数据卷 + 健康检查 + 网络
    ├── .env.example          # 两个 API key 的填写模板（精简自 EverOS 官方）
    └── README.md             # 三步部署说明
```

### 3.1 Dockerfile（自建，现 build——已按你的选择）

```dockerfile
# deploy/Dockerfile —— 自建 EverOS 镜像，不依赖上游发不发镜像
FROM python:3.12-slim

# EverOS 需要 3.12+（pyproject.toml:7 实证）
RUN pip install --no-cache-dir everos==1.0.1

# 数据目录（md + LanceDB + SQLite），挂 volume 持久化
ENV EVEROS_MEMORY__ROOT=/data/everos
# 容器内必须绑 0.0.0.0，否则同网络其它容器连不上（.env.example 实证）
ENV EVEROS_API__HOST=0.0.0.0
ENV EVEROS_API__PORT=8000

EXPOSE 8000
# server start 会按查找顺序读 .env（compose 用 env_file 注入）
CMD ["everos", "server", "start"]
```
> 固定 `everos==1.0.1` 而非浮动版本——对应 `05` 的「依赖锁版本」规约，避免上游升级悄悄破坏契约。升级时显式改这一行 + 回归测试。

### 3.2 docker-compose.yml（EverOS 与 AstrBot 同网络）

```yaml
# deploy/docker-compose.yml
services:
  everos:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: everos
    env_file:
      - .env                       # 用户从 .env.example 复制并填 key
    volumes:
      - everos_data:/data/everos   # 数据持久化：换插件/重启容器，记忆不丢
    ports:
      - "127.0.0.1:8000:8000"      # 仅本机暴露；同网络容器走服务名不需要它
    healthcheck:
      # GET /health（docs/api.md:45-48 实证 /health 存在于 /api/v1 之外）
      test: ["CMD", "python", "-c",
             "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s            # 首次起容器+装包留足时间
    restart: unless-stopped
    networks:
      - astrbot_net

volumes:
  everos_data:

networks:
  astrbot_net:
    # 关键：与 AstrBot 容器共用同一网络。
    # 若 AstrBot 已有 compose，把它的网络设成 external 引用，或把 everos 服务并进 AstrBot 的 compose。
    # 这样插件用 http://everos:8000 即可连接，无需宿主机 IP。
    driver: bridge
```

> **两种接入姿势（README 要讲清）**：
> 1. **并进 AstrBot 的 compose**（推荐）：把上面的 `everos` 服务块 + volume 直接加进你现有 AstrBot 的 `docker-compose.yml`，同一文件天然同网络。插件 `everos_base_url` 填 `http://everos:8000`。
> 2. **独立 compose + external 网络**：EverOS 单独一个 compose，`networks` 指向 AstrBot 已存在的网络（`external: true`）。

### 3.3 .env.example（精简模板）

```bash
# deploy/.env.example —— 复制为 .env 并填入你的 key（.env 已在 .gitignore，勿提交）
# 方案A：OpenRouter + DeepInfra（两个 key）
EVEROS_LLM__API_KEY=<你的_OpenRouter_key>
EVEROS_MULTIMODAL__API_KEY=<同一个_OpenRouter_key>
EVEROS_EMBEDDING__API_KEY=<你的_DeepInfra_key>
EVEROS_RERANK__API_KEY=<同一个_DeepInfra_key>

# 方案B（可选）：阿里百炼 DashScope 一个 key 全包，取消下面注释、改 BASE_URL/MODEL
# 详见 EverOS 官方 .env.example 的 DashScope 备选段
```

---

## 四、用户的开箱流程（写进插件 README 顶部）

```
1. 把 deploy/ 里的 everos 服务并进你的 AstrBot docker-compose.yml（或用独立 compose + external 网络）
2. cp deploy/.env.example deploy/.env  并填入 OpenRouter + DeepInfra 两个 key
3. docker compose up -d        # 起 EverOS（首次会 build 镜像，几分钟）
4. 在 AstrBot 装本插件，配置面板里 everos_base_url 填 http://everos:8000
5. 完成。插件自动检测 EverOS 健康、自动注入记忆、自动归档对话。
```

唯一的手动步骤是第 3 步的一次 `up`——这正是你确认可接受的边界。

---

## 五、插件侧的配套设计（不调 docker，但要优雅处理引擎状态）

插件不碰 docker，但要把「EverOS 没起好」这件事处理得体面：

| 场景 | 插件行为 | 实现位置 |
|---|---|---|
| EverOS 未连接 | `on_llm_request/response` 钩子 health 检查失败 → 跳过记忆、不阻断对话、日志 warning | `04` main.py `_healthy()` |
| 启动时引擎未就绪 | `initialize()` 里 health 探测，失败只告警不抛错；后续钩子里惰性重试 | `04` main.py `initialize` |
| `/everos status` | 明确显示「EverOS: 已连接 http://everos:8000」或「未连接——请确认容器已 up」 | `commands/handlers.py` |
| base_url 默认值 | 默认 `http://everos:8000`（同网络服务名），单机非容器场景用户改 `http://127.0.0.1:8000` | `_conf_schema.json` |

> ⚠️ `everos_base_url` 默认值改为 `http://everos:8000`（同网络服务名），这与 `02`/`04` 里写的 `127.0.0.1:8000` 不同——因为你的实际部署是容器同网络。`_conf_schema.json` 的 default 用 `http://everos:8000`，并在 hint 注明「非容器/单机部署改为 http://127.0.0.1:8000」。

---

## 六、风险与边界（补进 05 风险表）

| 风险 | 说明 | 缓解 |
|---|---|---|
| 用户机器需装 Docker | 本方案前提 | README 首行写明前提；非 Docker 用户走 `everos server start` 裸装（指 EverOS QUICKSTART） |
| 首次 build 镜像耗时 | pip install everos + 依赖，几分钟 | compose healthcheck 的 `start_period:30s`；README 提示首次较慢 |
| 数据卷备份 | 记忆在 `everos_data` volume 里 | README 给 `docker run --rm -v everos_data:/data ... tar` 备份示例 |
| EverOS 暴露 0.0.0.0 | 容器内绑 0.0.0.0 才能同网络访问，但 ports 只映射到宿主 127.0.0.1 | 不把 8000 端口公网映射；靠 docker 网络隔离；公网需自加网关 |
| 上游版本漂移 | everos 升级可能改 API 契约 | Dockerfile 固定 `everos==1.0.1`；升级显式改版本号+跑回归 |
| 两个外部 API key 成本 | LLM 提取 + embedding 要调外部 | 文档说明；archive_strategy=auto 省调用；支持 DashScope 等更便宜的兼容端点 |
