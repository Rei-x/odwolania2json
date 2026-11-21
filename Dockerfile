FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN grep -v '^anthropic' requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt
COPY . .
EXPOSE 8000
CMD ["python", "gui.py", "--host", "0.0.0.0", "--port", "8000"]
