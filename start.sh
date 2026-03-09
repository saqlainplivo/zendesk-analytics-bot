#!/bin/bash
# Startup script for Zendesk Analytics Bot

echo "🎯 Starting Zendesk Analytics Bot..."
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run setup first:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please create it:"
    echo "   cp .env.example .env"
    echo "   # Then add your API keys"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

echo "✅ Environment ready"
echo "🚀 Starting server at http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start the server
uvicorn app.api.server:app --reload --host 0.0.0.0 --port 8000
