#!/bin/bash
export PYTHONUNBUFFERED=TRUE
gunicorn \
    --preload \
    --config ./gunicorn.conf.py \
    --worker-class="gevent" \
    --workers=4 \
    --worker-tmp-dir="/dev/shm" \
    "--bind=0.0.0.0:8090" \
    aerodata:webapp
