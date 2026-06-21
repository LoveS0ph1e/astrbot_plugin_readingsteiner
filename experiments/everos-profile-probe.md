# EverOS Profile 提取质量实测记录（任务0）

> 状态：**未执行 — 环境硬阻塞**。脚本与样本已就绪，待可运行 EverOS 的环境。

## 阻塞原因（2026-06-21 实测确认）

任务 0 要求起真实 EverOS 服务灌数据探画像。本机（Windows 11）三条路全断：

1. **EverOS 原生不支持 Windows**。`everos==1.0.1` 已成功 `pip install` 进 `.venv`（Python 3.12.0），
   但 `everos server start` 在 `import fcntl` 处崩溃——`fcntl` 是 POSIX 专有模块。
   源码 `everos/core/persistence/locking.py:1-9` 注释明文：
   *"Uses fcntl.flock (POSIX advisory locking, available on Linux + macOS; **Windows is not supported**)"*。
2. **无 Docker**：`docker: command not found`，故 `06-Docker部署` 的 compose 路径在本机不可用。
3. **无 WSL**：`wsl --status` 返回「未安装」。

即：**给了 API key 也无法在本机起服务**。阻塞是 OS 层面，不是缺 key。

## 已就绪的产物（待环境到位即可一把跑通）

- `experiments/probe_everos_profile.py`：纯 httpx 探针。add → flush → search(include_profile=true, 5 角度) → get profile。
  严格遵循 `docs/01-实证依据.md` 第二部分 API 契约（全 POST、响应取 data、timestamp 毫秒）。
- `experiments/sample_dialogue.json`：17 轮脱敏对话，覆盖 §11.6 五类目信号
  （TASTE 黑咖啡/民谣、IDENTITY 独居两年、ROUTINE 熬夜到三点、VULNERABILITY 羡慕有人等、BOND 不用端着）。

## 待补：在可运行 EverOS 的环境执行

任一可行环境（Linux/macOS 原生，或装了 Docker/WSL 的机器）：

```bash
# 方式A：裸装（Linux/macOS）
pip install everos==1.0.1
everos init                      # 生成 .env
# 填 .env 的 4 个 key 槽（OpenRouter ×2 + DeepInfra ×2，或 DashScope 一个全包）
everos server start              # 起在 127.0.0.1:8000
# 另开终端：
python experiments/probe_everos_profile.py --base-url http://127.0.0.1:8000

# 方式B：Docker（任务1.5 的 deploy/ 建好后）
docker compose -f deploy/docker-compose.yml up -d
python experiments/probe_everos_profile.py --base-url http://127.0.0.1:8000
```

执行后本文件会被脚本自动覆盖为真实探测结果，再人工填第6节判断。

## 6. 人工判断（待填）

- [ ] profile_data 是否稳定承载『深羁绊+多面向』印象？
- [ ] 比 Mnemosyne 每轮重新推断强多少？
- [ ] 结论：值得迁移 / 不值得（回到方案A）
