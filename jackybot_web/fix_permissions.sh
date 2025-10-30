#!/bin/bash

set -e

echo "========================================="
echo "JackyBot Web UI - Fix Permissions Script"
echo "========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "Project root: $PROJECT_ROOT"
echo "Frontend directory: $FRONTEND_DIR"
echo ""

if [ ! -d "$FRONTEND_DIR/dist" ]; then
    echo "ERROR: Frontend dist directory not found at $FRONTEND_DIR/dist"
    echo "Please build the frontend first:"
    echo "  cd $FRONTEND_DIR"
    echo "  npm run build"
    exit 1
fi

echo ">>> Fixing permissions for nginx access..."
echo ""

NGINX_USER="www-data"
if id "nginx" &>/dev/null; then
    NGINX_USER="nginx"
fi

echo "Detected nginx user: $NGINX_USER"
echo ""

echo "Step 1: Making parent directories traversable for nginx..."
if [ -d "/root" ]; then
    echo "  Setting execute permission on /root (for traversal only)..."
    sudo chmod 755 /root
fi

if [ -d "/root/jackybot" ]; then
    echo "  Setting execute permission on /root/jackybot..."
    sudo chmod 755 /root/jackybot
    
    if [ -d "/root/jackybot/jackybot_web" ]; then
        echo "  Setting execute permission on /root/jackybot/jackybot_web..."
        sudo chmod 755 /root/jackybot/jackybot_web
        
        if [ -d "/root/jackybot/jackybot_web/frontend" ]; then
            echo "  Setting execute permission on /root/jackybot/jackybot_web/frontend..."
            sudo chmod 755 /root/jackybot/jackybot_web/frontend
        fi
    fi
fi

echo ""
echo "Step 2: Setting ownership and permissions on dist directory..."
sudo chown -R $NGINX_USER:$NGINX_USER "$FRONTEND_DIR/dist"
sudo chmod -R 755 "$FRONTEND_DIR/dist"

echo "  Ownership set to: $NGINX_USER:$NGINX_USER"
echo "  Permissions set to: 755"

echo ""
echo "Step 3: Verifying permissions..."
if [ -r "$FRONTEND_DIR/dist/index.html" ]; then
    echo "  ✓ index.html is readable"
else
    echo "  ✗ ERROR: index.html is not readable!"
    exit 1
fi

echo ""
echo "Step 4: Testing as nginx user..."
if sudo -u $NGINX_USER test -r "$FRONTEND_DIR/dist/index.html"; then
    echo "  ✓ nginx user can read index.html"
else
    echo "  ✗ ERROR: nginx user cannot read index.html!"
    echo "  This may indicate an SELinux or AppArmor restriction."
    exit 1
fi

echo ""
echo "========================================="
echo "Permissions Fixed Successfully!"
echo "========================================="
echo ""
echo "Reloading nginx..."
sudo systemctl reload nginx

echo ""
echo "Checking nginx status..."
if sudo systemctl is-active --quiet nginx; then
    echo "  ✓ Nginx is running"
else
    echo "  ✗ Nginx is not running. Check logs:"
    echo "    sudo journalctl -u nginx -n 50"
fi

echo ""
echo "Next steps:"
echo "1. Check nginx error logs: sudo tail -f /var/log/nginx/error.log"
echo "2. Test the website: curl -I https://jackybot.xyz"
echo "3. If issues persist, check SELinux/AppArmor:"
echo "   - SELinux: getenforce (if enabled, may need: sudo setsebool -P httpd_read_user_content 1)"
echo "   - AppArmor: sudo aa-status"

