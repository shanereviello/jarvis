FROM python:3.11.17-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY deploy/mcp/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

COPY app ./app

RUN groupadd --gid 10001 jarvis \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin jarvis

EXPOSE 8000

USER jarvis

CMD ["python", "-m", "app.servers.mcp.server"]
