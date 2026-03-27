#!/bin/bash

# Bitcoin Scanner Startup Script

# Get the absolute path of the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "🚀 Starting Bitcoin Scanner..."

# Function to cleanup background processes on exit
cleanup() {
    echo -e "\n🛑 Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}

# Trap SIGINT (Ctrl+C)
trap cleanup SIGINT

# 1. Start Backend
echo "📡 Starting Backend (FastAPI)..."
cd "$BACKEND_DIR"
source venv/bin/activate
python3 main.py &
BACKEND_PID=$!

# 2. Start Frontend
echo "💻 Starting Frontend (Angular)..."
cd "$FRONTEND_DIR"
npm start &
FRONTEND_PID=$!

echo "✅ Both servers are starting!"
echo "   - Frontend: http://localhost:4200"
echo "   - Backend:  http://localhost:8765"
echo "   - WebSocket: ws://localhost:8765/ws"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait for background processes
wait
