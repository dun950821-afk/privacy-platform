#!/bin/bash
# 启动脚本 - 在openEuler上启动隐私合规平台

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Python venv
VENV="${VENV:-/tmp/venv}"

echo "========================================="
echo "  App个人信息保护检测与治理平台"
echo "========================================="

# 1. Start PostgreSQL
if ! pg_isready -h localhost -p 5432 2>/dev/null; then
    echo "[1/4] Starting PostgreSQL..."
    sudo -u postgres /usr/bin/postgres -D /var/lib/pgsql/data -c config_file=/var/lib/pgsql/data/postgresql.conf &
    sleep 3
else
    echo "[1/4] PostgreSQL already running."
fi

# 2. Start Redis
if ! redis-cli ping 2>/dev/null | grep -q PONG; then
    echo "[2/4] Starting Redis..."
    redis-server --daemonize yes --port 6379 --save "" --appendonly no
    sleep 1
else
    echo "[2/4] Redis already running."
fi

# 3. Start Backend
if ! curl -s http://localhost:8000/health 2>/dev/null | grep -q ok; then
    echo "[3/4] Starting Backend (FastAPI)..."
    cd "$PROJECT_DIR/backend"
    $VENV/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
    sleep 2
else
    echo "[3/4] Backend already running."
fi

# 4. Start Frontend
if [ -d "$PROJECT_DIR/frontend/node_modules" ]; then
    echo "[4/4] Starting Frontend (Vite)..."
    cd "$PROJECT_DIR/frontend"
    npx vite --host 0.0.0.0 --port 5173 &
    sleep 2
    echo ""
    echo "Frontend: http://localhost:5173"
else
    echo "[4/4] Frontend not installed. Run: cd frontend && npm install"
fi

echo ""
echo "Backend API: http://localhost:8000/docs"
echo "Admin login: admin / admin123"
echo ""
echo "Press Ctrl+C to stop all services."
wait
