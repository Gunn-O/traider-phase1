#!/bin/bash
# Run main.py with 10-minute limit for testing

echo "🚀 Starting Tra(i)der test run (10 minutes max)..."
echo "Press Ctrl+C to stop earlier"
echo ""

cd "$(dirname "$0")"
source venv/bin/activate

# Run with timeout (600s = 10 min)
timeout 600 python -u main.py

echo ""
echo "🛑 Test run completed or stopped"
