#!/bin/bash
set -e

echo "=== Claude Code Web Wrapper ==="
echo ""

# Install backend dependencies
echo "Installing backend dependencies..."
cd "$(dirname "$0")/backend"
pip install -q -r requirements.txt

# Install frontend dependencies
echo "Installing frontend dependencies..."
cd "$(dirname "$0")/frontend"
npm install --silent 2>/dev/null

echo ""
echo "Starting servers..."
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""

# Start backend
cd "$(dirname "$0")/backend"
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
cd "$(dirname "$0")/frontend"
npm run dev &
FRONTEND_PID=$!

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

wait
