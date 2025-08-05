# Chainlit RAG Knowledge Base - Docker Image
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/data /app/logs /app/uploads

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000 5000

# 创建启动脚本
RUN echo '#!/bin/bash\n\
    set -e\n\
    \n\
    echo "🚀 启动 Chainlit RAG 知识库系统..."\n\
    \n\
    # 等待数据库启动\n\
    echo "⏳ 等待数据库启动..."\n\
    while ! pg_isready -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER; do\n\
    echo "数据库未就绪，等待中..."\n\
    sleep 2\n\
    done\n\
    echo "✅ 数据库连接成功"\n\
    \n\
    # 初始化数据库\n\
    echo "🔧 初始化数据库..."\n\
    python docker/init_db.py\n\
    \n\
    # 启动Flask API服务器（后台）\n\
    echo "📡 启动 API 服务器..."\n\
    python docker/integrated_server.py &\n\
    API_PID=$!\n\
    \n\
    # 等待API服务器启动\n\
    echo "⏳ 等待 API 服务器启动..."\n\
    for i in {1..30}; do\n\
    if curl -s http://localhost:5000/health >/dev/null 2>&1; then\n\
    echo "✅ API 服务器启动成功"\n\
    break\n\
    fi\n\
    if [ $i -eq 30 ]; then\n\
    echo "❌ API 服务器启动超时"\n\
    exit 1\n\
    fi\n\
    sleep 1\n\
    done\n\
    \n\
    # 启动Chainlit前端\n\
    echo "🌐 启动 Chainlit 前端..."\n\
    exec chainlit run frontend/app.py --host 0.0.0.0 --port 8000\n\
    ' > /app/start.sh && chmod +x /app/start.sh

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# 启动命令
CMD ["/app/start.sh"]