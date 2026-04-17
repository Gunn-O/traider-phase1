#!/bin/bash
# Run main.py with unbuffered output

cd "$(dirname "$0")"
source venv/bin/activate
python -u main.py
