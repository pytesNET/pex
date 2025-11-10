#!/usr/bin/env bash
cd "$(dirname "$0")"/.. || exit
.venv/bin/python -m pex "$@"
