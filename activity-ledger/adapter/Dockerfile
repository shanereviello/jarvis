FROM python:3.13-slim-bookworm
WORKDIR /app
COPY adapter/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY src /app/src
COPY contracts /app/contracts
RUN chmod -R a-w /app/contracts
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["python", "-m", "activity_ledger.pg_adapter"]
