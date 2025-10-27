#!/bin/bash

set -e

echo "================================================"
echo "JackyBot Deployment Script"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please create a .env file based on env.example"
    echo "Run: cp env.example .env"
    echo "Then edit .env with your actual credentials"
    exit 1
fi

# Pull latest code from Git
echo -e "${YELLOW}Pulling latest code from Git...${NC}"
git pull

# Build Docker image
echo -e "${YELLOW}Building Docker image...${NC}"
docker-compose build --no-cache

# Stop and remove existing container
echo -e "${YELLOW}Stopping existing container...${NC}"
docker-compose down

# Start new container
echo -e "${YELLOW}Starting new container...${NC}"
docker-compose up -d

# Wait a few seconds for container to start
sleep 5

# Show container status
echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Container status:"
docker-compose ps

# Show recent logs
echo ""
echo -e "${YELLOW}Recent logs (last 50 lines):${NC}"
docker-compose logs --tail=50

echo ""
echo "================================================"
echo -e "${GREEN}Deployment successful!${NC}"
echo "================================================"
echo ""
echo "Useful commands:"
echo "  View logs:        docker-compose logs -f"
echo "  Restart bot:      docker-compose restart"
echo "  Stop bot:         docker-compose down"
echo "  Container status: docker-compose ps"
echo ""

