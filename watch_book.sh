#!/bin/bash

# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

echo "Starting Jupyter Book watcher..."
echo "Watching markdown files in: docs/"
echo "Press Ctrl+C to stop"
echo ""

echo "Performing initial build..."
uv run jupyter-book clean docs
uv run jupyter-book build docs

uv run watchmedo shell-command \
    --patterns="*.md" \
    --recursive \
    --drop \
    --command='echo "Changes detected, rebuilding..." && uv run jupyter-book clean docs && uv run jupyter-book build docs' \
    docs/
