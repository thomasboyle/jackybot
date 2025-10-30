#!/bin/bash

echo "========================================="
echo "JackyBot Web UI - Diagnostic Script"
echo "========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "Checking components..."
echo ""

echo "1. Checking if backend is running on port 5000..."
if netstat -tlnp 2>/dev/null | grep -q ':5000' || ss -tlnp 2>/dev/null | grep -q ':5000'; then
    echo "   ✓ Backend is running on port 5000"
else
    echo "   ✗ Backend is NOT running on port 5000"
    echo "     Run: cd $BACKEND_DIR && python app.py"
fi
echo ""

echo "2. Checking frontend dist directory..."
if [ -d "$FRONTEND_DIR/dist" ]; then
    echo "   ✓ Frontend dist directory exists"
    if [ -f "$FRONTEND_DIR/dist/index.html" ]; then
        echo "   ✓ index.html exists"
    else
        echo "   ✗ index.html is missing - rebuild frontend"
    fi
else
    echo "   ✗ Frontend dist directory does NOT exist"
    echo "     Run: cd $FRONTEND_DIR && npm run build"
fi
echo ""

echo "3. Checking file permissions..."
if [ -d "$FRONTEND_DIR/dist" ]; then
    ls -ld "$FRONTEND_DIR/dist" 2>/dev/null | head -1
fi
echo ""

echo "4. Checking Nginx configuration..."
if sudo nginx -t 2>&1 | grep -q "successful"; then
    echo "   ✓ Nginx configuration is valid"
else
    echo "   ✗ Nginx configuration has errors:"
    sudo nginx -t
fi
echo ""

echo "5. Checking Nginx status..."
if systemctl is-active --quiet nginx; then
    echo "   ✓ Nginx is running"
else
    echo "   ✗ Nginx is NOT running"
    echo "     Run: sudo systemctl start nginx"
fi
echo ""

echo "6. Checking recent Nginx error logs..."
echo "   Last 10 lines of error log:"
sudo tail -n 10 /var/log/nginx/error.log 2>/dev/null || echo "   Could not read error log"
echo ""

echo "7. Checking environment variables..."
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    echo "   ✓ .env file exists"
    if grep -q "DISCORD_CLIENT_ID=" "$ENV_FILE" && ! grep -q "DISCORD_CLIENT_ID=your_" "$ENV_FILE"; then
        echo "   ✓ DISCORD_CLIENT_ID is set"
    else
        echo "   ✗ DISCORD_CLIENT_ID is missing or not configured"
    fi
    if grep -q "DISCORD_CLIENT_SECRET=" "$ENV_FILE" && ! grep -q "DISCORD_CLIENT_SECRET=your_" "$ENV_FILE"; then
        echo "   ✓ DISCORD_CLIENT_SECRET is set"
    else
        echo "   ✗ DISCORD_CLIENT_SECRET is missing or not configured"
    fi
else
    echo "   ✗ .env file does NOT exist"
fi
echo ""

echo "========================================="
echo "Diagnostic Complete"
echo "========================================="
echo ""
echo "Common fixes:"
echo "  1. Start backend: cd $BACKEND_DIR && python app.py"
echo "  2. Rebuild frontend: cd $FRONTEND_DIR && npm run build"
echo "  3. Fix permissions: sudo chown -R www-data:www-data $FRONTEND_DIR/dist"
echo "  4. Restart Nginx: sudo systemctl restart nginx"
echo "  5. Check logs: sudo tail -f /var/log/nginx/error.log"
echo ""
