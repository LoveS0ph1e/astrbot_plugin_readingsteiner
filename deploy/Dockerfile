# EverOS 服务镜像（供 astrbot_plugin_readingsteiner 使用）
# EverOS 仅支持 Linux/macOS（用 fcntl POSIX 锁），容器化是 Windows 宿主上的标准跑法。
FROM python:3.12-slim

# LibreOffice 等多模态可选依赖此处不装（MVP 只用文本）；需要时再加。
WORKDIR /app

# 固定版本，避免上游变动破坏契约（与本机验证版本一致）
RUN pip install --no-cache-dir "everos==1.0.1"

# 记忆数据目录（md + .index/ + .system.db），用具名卷持久化
ENV EVEROS_MEMORY__ROOT=/data/everos
RUN mkdir -p /data/everos

# 绑定 0.0.0.0 以便同 docker 网络的 AstrBot 容器访问；网络隔离靠 compose 私网
ENV EVEROS_API__HOST=0.0.0.0
ENV EVEROS_API__PORT=8000
EXPOSE 8000

# 健康检查打 /health（在 /api/v1 之外）
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)"

CMD ["everos", "server", "start"]
