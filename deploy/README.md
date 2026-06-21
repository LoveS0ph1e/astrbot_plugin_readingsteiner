# EverOS 部署（配合 astrbot_plugin_readingsteiner）

本插件不内嵌记忆引擎，依赖一个独立的 EverOS 服务。本目录提供把 EverOS 跑起来的最小编排。

> **为什么要容器化**：EverOS 用 `fcntl`（POSIX 文件锁），**不支持 Windows 原生运行**。
> Windows 宿主请用本目录的 Docker 方案；Linux/macOS 可选择裸装（见末节）。

## 前置

- 已安装 Docker / Docker Compose
- 至少一组模型 API key（OpenRouter+DeepInfra，或 DashScope 一个全包）

## 快速开始

```bash
cd deploy
cp .env.example .env          # 填入你的 key（.env 已 gitignore）
docker compose up -d --build  # 构建并后台启动
docker compose ps             # 等 everos 状态变 healthy
curl http://127.0.0.1:8000/health   # 期望 {"status":"ok"} 或 healthy
```

启动后在 AstrBot 插件配置里把 `everos_base_url` 设为：
- 插件与 EverOS **同 docker 网络**：`http://everos:8000`（推荐，用服务名）
- 插件在宿主机直接跑：`http://127.0.0.1:8000`

## 与 AstrBot 容器接入同一网络

插件用服务名 `everos` 连接，前提是两个容器在**同一 docker 网络**。两种姿势：

**姿势 1（推荐）**：把本 `compose` 的 `everos` 服务块并入 AstrBot 自己的 `docker-compose.yml`，
同文件内的服务天然同网络，无需额外配置。

**姿势 2**：保持独立 compose，把网络改为引用 AstrBot 已建的外部网络：

```yaml
# 本文件 networks 段改成（假设 AstrBot 网络名为 astrbot_default）：
networks:
  astrbot_net:
    external: true
    name: astrbot_default
```

用 `docker network ls` 查 AstrBot 实际网络名。

## 数据持久化与删除

- 记忆存于具名卷 `everos_data`（容器内 `/data/everos`），含 md 文件 + `.index/` + `.system.db`。
- 重启/重建容器不丢记忆。
- 彻底清空：`docker compose down -v`（**会删卷，记忆不可恢复**，谨慎）。
- 删单个用户记忆：EverOS v1 API 无删除端点，需进卷删对应 user 的 md 目录后重建索引。

## 验证任务 0（画像质量探针）

服务 healthy 后，从仓库根运行探针（探针在宿主机用 httpx 打 8000，无需进容器）：

```bash
python experiments/probe_everos_profile.py --base-url http://127.0.0.1:8000
```

它会灌入 `experiments/sample_dialogue.json` → flush → search，把画像与情景 dump 到
`experiments/everos-profile-probe.md` 供人工判断（详见该文件与 `docs/03` 任务 0）。

## 生产环境注意事项（投产前必读）

1. **EverOS 无内置鉴权**：默认绑 `127.0.0.1`，仅本机/同 docker 网络可达，本地安全。
   ⚠️ **切勿把 8000 端口直接暴露公网**——任何人都能读写记忆。需公网访问请在前面加
   带鉴权的网关（Nginx + Basic Auth / API 网关），并用防火墙限制来源。

2. **进程自启**：用本目录 Docker 方案时 `restart: unless-stopped` 已保证容器随 Docker 自启。
   若裸装（见下节），EverOS 是普通进程，**服务器重启后不会自动拉起**——记忆功能会静默失效。
   生产环境务必配 systemd 守护（`everos server start` 作为 ExecStart），别用裸 `nohup`。

3. **模型弃用时间线**：LLM 用 DeepSeek 时，旧模型名 `deepseek-chat` / `deepseek-reasoner`
   于 **2026-07-24** 弃用，迁移到 `deepseek-v4-flash` / `deepseek-v4-pro`（见 `.env.example`）。

4. **数据备份**：记忆是用户资产。定期备份具名卷 `everos_data`（或裸装的 `~/.everos`）：
   `docker run --rm -v everos_data:/d -v $PWD:/b alpine tar czf /b/everos-backup.tar.gz -C /d .`

## Linux/macOS 裸装（不用 Docker）

```bash
pip install everos==1.0.1
everos init                  # 生成 .env
# 编辑 .env 填 key
everos server start          # 默认 127.0.0.1:8000
```

