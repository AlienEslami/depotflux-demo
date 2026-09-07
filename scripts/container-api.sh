#!/bin/sh
set -eu

alembic upgrade head
exec python -m aggregator_demo.cli
