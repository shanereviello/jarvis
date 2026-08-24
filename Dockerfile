FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN groupadd --gid 10001 jarvis \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin jarvis

EXPOSE 8000

USER jarvis

CMD ["python", "-m", "app.servers.mcp.server"]
