FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p input output trace
EXPOSE 8000
# Domyślnie GUI; tryb wsadowy (input/ -> output/): docker compose run --rm wrobelek (docker-compose.yml)
CMD ["python", "gui.py", "--host", "0.0.0.0", "--port", "8000"]
