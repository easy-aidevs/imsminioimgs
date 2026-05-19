# 使用Python 3.9 slim镜像作为基础
FROM python:3.9-slim

LABEL maintainer="IMS Team" \
      description="图片内容安全扫描系统 - 扫描和处置工具"

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p /app/logs && \
    chmod 777 /app/logs

# 设置卷挂载点（仅日志）
VOLUME ["/app/logs"]

# 健康检查：检查 Python 和必要依赖是否可用
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import mysql.connector, minio; print('OK')" || exit 1

# 默认命令：显示帮助信息（可被覆盖）
# 运维人员通过 docker-compose run [service] python [command] 来执行具体的工具
CMD ["python", "-c", "import sys; print('\\n=== 图片内容安全扫描系统 ===\\n请使用以下命令：\\n  扫描器:     docker-compose run --rm scanner python scanner.py\\n  处置工具:   docker-compose run --rm handler python handle_violations.py [command]\\n'); sys.exit(0)"]
