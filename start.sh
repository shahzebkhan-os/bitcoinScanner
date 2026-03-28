#!/bin/bash

# Bitcoin Scanner Startup Script

# Get the absolute path of the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
LOGS_DIR="$PROJECT_DIR/logs"

# Ensure logs directory exists
mkdir -p "$LOGS_DIR"

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
    if [ ! -z "$BACKEND_PID" ]; then kill -TERM -$BACKEND_PID 2>/dev/null; fi
    if [ ! -z "$FRONTEND_PID" ]; then kill -TERM -$FRONTEND_PID 2>/dev/null; fi
    # Kill specific ports again just in case
    lsof -ti :8765,4200 | xargs kill -9 2>/dev/null || true
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

# 1. Start Backend
echo "📡 Starting Backend (FastAPI)..."
cd "$BACKEND_DIR"

if [ ! -d "venv" ]; then
    echo "❌ Error: Virtual environment (venv) not found in $BACKEND_DIR"
    exit 1
fi

source venv/bin/activate
# Run in its own process group to make killing easier
set -m
python3 main.py > "$LOGS_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
set +m

# Wait for backend to be responsive
echo "⏳ Waiting for backend to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! curl -s http://localhost:8765/health > /dev/null; do
    sleep 1
    RETRY_COUNT=$((RETRY_COUNT+1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "❌ Error: Backend failed to start after $MAX_RETRIES seconds."
        cat "$LOGS_DIR/backend.log"
        cleanup
    fi
    # Check if process is still running
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "❌ Error: Backend process died unexpectedly."
        cat "$LOGS_DIR/backend.log"
        cleanup
    fi
done
echo "✅ Backend is ready!"

# 2. Start Frontend
echo "💻 Starting Frontend (Angular)..."
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    echo "❌ Error: node_modules not found in $FRONTEND_DIR. Please run 'npm install'."
    cleanup
fi

npm start > "$LOGS_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

echo "✅ Both servers are starting!"
echo "   - Frontend: http://localhost:4200"
echo "   - Backend:  http://localhost:8765"
echo "   - WebSocket: ws://localhost:8765/ws"
echo ""
echo "📝 Logs are available in: $LOGS_DIR"
echo "Press Ctrl+C to stop both servers."

# Monitor processes
while true; do
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "❌ Backend process stopped. Shutting down..."
        cleanup
    fi
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "❌ Frontend process stopped. Shutting down..."
        cleanup
    fi
    sleep 2
done
