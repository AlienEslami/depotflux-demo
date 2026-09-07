FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 demo

WORKDIR /app
COPY requirements-demo-lock.txt ./
RUN pip install --no-cache-dir -r requirements-demo-lock.txt

COPY --chown=demo:demo . .
RUN chmod 0555 scripts/container-api.sh

USER demo
CMD ["python", "-m", "aggregator_demo.cli"]
