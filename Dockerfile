FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 demo

WORKDIR /app
COPY requirements-demo-lock.txt ./
RUN pip install --no-cache-dir -r requirements-demo-lock.txt

COPY --chown=demo:demo alembic.ini ./
COPY --chown=demo:demo aggregator_demo ./aggregator_demo
COPY --chown=demo:demo migrations ./migrations
COPY --chown=demo:demo scripts/container-api.sh ./scripts/container-api.sh
COPY --chown=demo:demo scripts/run_gridtwin_evidence.py ./scripts/run_gridtwin_evidence.py
RUN chmod 0555 scripts/container-api.sh

USER demo
CMD ["python", "-m", "aggregator_demo.cli"]
