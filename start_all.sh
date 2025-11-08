#!/bin/bash

# Master startup script for JackyBot
# This script launches all components: bot, frontend, lavalink, and backend

echo "Starting JackyBot and all services..."
echo "===================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a process is running
check_process() {
    local pid=$1
    local name=$2
    if kill -0 $pid 2>/dev/null; then
        echo -e "${GREEN}✓ $name is running (PID: $pid)${NC}"
        return 0
    else
        echo -e "${RED}✗ $name failed to start${NC}"
        return 1
    fi
}

# Function to start service and track PID
start_service() {
    local script_path=$1
    local service_name=$2
    local log_file=$3

    echo -e "${YELLOW}Starting $service_name...${NC}"

    # Start the service in background and capture PID
    nohup bash "$script_path" > "$log_file" 2>&1 &
    local pid=$!

    # Wait a moment for the process to start
    sleep 3

    # Check if it's still running
    if check_process $pid "$service_name"; then
        echo "$pid" >> .running_pids
        return 0
    else
        return 1
    fi
}

# Clean up any existing PID file
rm -f .running_pids

# Start Lavalink first (other services may depend on it)
echo "Starting Lavalink..."
start_service "./start_lavalink.sh" "Lavalink" "lavalink_master.log"

# Small delay between services
sleep 2

# Start the Flask backend
echo "Starting Flask Backend..."
cd jackybot_web/backend
nohup uv run python3 app.py > ../../../backend_master.log 2>&1 &
backend_pid=$!
cd ../../
sleep 3
if check_process $backend_pid "Flask Backend"; then
    echo "$backend_pid" >> .running_pids
fi

# Small delay
sleep 2

# Start the frontend
echo "Starting Frontend..."
start_service "./jackybot_web/start_frontend.sh" "Frontend" "frontend_master.log"

# Small delay
sleep 2

# Start the main bot
echo "Starting Main Bot..."
start_service "./start_linux.sh" "Main Bot" "bot_master.log"

echo ""
echo -e "${GREEN}All services started!${NC}"
echo "Log files:"
echo "  - Lavalink: lavalink_master.log"
echo "  - Backend: backend_master.log"
echo "  - Frontend: frontend_master.log"
echo "  - Bot: bot_master.log"
echo ""
echo "To stop all services, run: ./stop_all.sh"
echo ""
echo "Process PIDs saved in .running_pids"
