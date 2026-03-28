#!/bin/bash

# Bitcoin Scanner Startup Script

# Get the absolute path of the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "🚀 Starting Bitcoin Scanner..."

# 0. Cleanup Existing Processes
cleanup_ports() {
    echo "🧹 Cleaning up existing processes on ports 8765 and 4200..."
    # Port 8765 (Backend)
    lsof -ti :8765 | xargs kill -9 2>/dev/null || true
    # Port 4200 (Frontend)
    lsof -ti :4200 | xargs kill -9 2>/dev/null || true
    sleep 1
}

cleanup_ports

# Function to cleanup background processes on exit
cleanup() {
    echo -e "\n🛑 Shutting down..."
    # Kill the process groups to ensure all sub-sub-processes are gone
    kill -TERM -$BACKEND_PID 2>/dev/null
    kill -TERM -$FRONTEND_PID 2>/dev/null
    # Kill specific ports again just in case
    lsof -ti :8765,4200 | xargs kill -9 2>/dev/null || true
    exit
}

# Trap SIGINT (Ctrl+C)
trap cleanup SIGINT

# 1. Start Backend
echo "📡 Starting Backend (FastAPI)..."
cd "$BACKEND_DIR"
source venv/bin/activate
# Run in its own process group to make killing easier
set -m
python3 main.py &
BACKEND_PID=$!

# 2. Start Frontend
echo "💻 Starting Frontend (Angular)..."
cd "$FRONTEND_DIR"
npm start &
FRONTEND_PID=$!
set +m

echo "✅ Both servers are starting!"
echo "   - Frontend: http://localhost:4200"
echo "   - Backend:  http://localhost:8765"
echo "   - WebSocket: ws://localhost:8765/ws"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait for background processes
wait
