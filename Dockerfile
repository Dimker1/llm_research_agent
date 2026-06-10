FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/

# 持久化数据目录挂载点
VOLUME ["/app/data", "/app/daily"]

CMD ["python", "-m", "src.scheduler"]
