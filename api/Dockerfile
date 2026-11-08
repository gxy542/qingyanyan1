# API 服务镜像（FastAPI）
FROM python:3.12-slim

# 设置工作目录与 Python 输出缓冲
WORKDIR /app
ENV PYTHONUNBUFFERED=1

# 先复制依赖清单并安装，便于利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app

# 暴露 FastAPI 端口
EXPOSE 8000

# 启动命令：uvicorn 监听 0.0.0.0
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
