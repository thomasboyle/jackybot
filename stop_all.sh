#!/bin/bash

# Stop script for JackyBot
# This script stops all running JackyBot services

echo "Stopping JackyBot and all services..."
echo "==================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to stop a process
stop_process() {
    local pid=$1
    local name=$2

    if kill -0 $pid 2>/dev/null; then
        echo -e "${YELLOW}Stopping $name (PID: $pid)...${NC}"
        kill $pid 2>/dev/null

        # Wait up to 10 seconds for graceful shutdown
        local count=0
        while kill -0 $pid 2>/dev/null && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done

        if kill -0 $pid 2>/dev/null; then
            echo -e "${RED}Force killing $name...${NC}"
            kill -9 $pid 2>/dev/null
            sleep 1
        fi

        if kill -0 $pid 2>/dev/null; then
            echo -e "${RED}✗ Failed to stop $name${NC}"
        else
            echo -e "${GREEN}✓ $name stopped${NC}"
        fi
    else
        echo -e "${GREEN}✓ $name was not running${NC}"
    fi
}

# Check if PID file exists
if [ ! -f .running_pids ]; then
    echo -e "${RED}No .running_pids file found. Services may not be running.${NC}"
    echo "You can try manually stopping with: pkill -f 'python3\|java\|npm'"
    exit 1
fi

# Stop all processes from the PID file
while read -r pid; do
    if [ ! -z "$pid" ] && [ "$pid" != "" ]; then
        # Try to identify the process
        if ps -p $pid > /dev/null 2>&1; then
            process_name=$(ps -p $pid -o cmd= | head -1)
            if [[ $process_name == *"python3"* ]]; then
                if [[ $process_name == *"app.py"* ]]; then
                    stop_process $pid "Flask Backend"
                elif [[ $process_name == *"bot.py"* ]]; then
                    stop_process $pid "Main Bot"
                else
                    stop_process $pid "Python Process"
                fi
            elif [[ $process_name == *"java"* ]]; then
                stop_process $pid "Lavalink"
            elif [[ $process_name == *"npm"* ]] || [[ $process_name == *"vite"* ]]; then
                stop_process $pid "Frontend"
            else
                stop_process $pid "Process"
            fi
        fi
    fi
done < .running_pids

# Clean up
rm -f .running_pids

echo ""
echo -e "${GREEN}All services stopped!${NC}"
echo "Log files remain available for review."
