# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

FROM python:3.13.7-slim@sha256:2be5d3cb08aa616c6e38d922bd7072975166b2de772004f79ee1bae59fe983dc

WORKDIR /app
COPY pyproject.toml .
COPY ramose ramose
RUN pip install --no-cache-dir ".[benchmark]"
