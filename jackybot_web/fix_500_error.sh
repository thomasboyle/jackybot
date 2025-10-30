#!/bin/bash

set -e

echo "========================================="
echo "JackyBot Web UI - Fix 500 Error Script"
echo "========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
DOMAIN_NAME="jackybot.xyz"
NGINX_CONFIG="/etc/nginx/sites-available/jackybot-web"

echo "Fixing Nginx configuration..."
echo ""

if [ ! -d "$FRONTEND_DIR/dist" ]; then
    echo "ERROR: Frontend dist directory not found!"
    echo "Building frontend..."
    cd "$FRONTEND_DIR"
    npm run build
    cd "$SCRIPT_DIR"
fi

echo ">>> Creating correct Nginx configuration..."
sudo tee "$NGINX_CONFIG" > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN_NAME;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name $DOMAIN_NAME;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN_NAME/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 20M;

    location /api {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    location /auth {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /socket.io {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }

    location / {
        root $FRONTEND_DIR/dist;
        try_files \$uri \$uri/ /index.html;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
    }
}
EOF

sudo ln -sf "$NGINX_CONFIG" /etc/nginx/sites-enabled/jackybot-web

echo ">>> Testing Nginx configuration..."
if sudo nginx -t; then
    echo ">>> Nginx configuration is valid"
else
    echo "ERROR: Nginx configuration test failed!"
    exit 1
fi

echo ">>> Setting file permissions..."
sudo chown -R www-data:www-data "$FRONTEND_DIR/dist" 2>/dev/null || \
    sudo chown -R nginx:nginx "$FRONTEND_DIR/dist" 2>/dev/null || \
    echo ">>> Note: Could not set ownership, may need manual adjustment"

sudo chmod -R 755 "$FRONTEND_DIR/dist" 2>/dev/null || true

echo ">>> Reloading Nginx..."
sudo systemctl reload nginx

echo ""
echo "========================================="
echo "Configuration Fixed!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Check if backend is running:"
echo "   netstat -tlnp | grep 5000"
echo "   or: ss -tlnp | grep 5000"
echo ""
echo "2. If backend is not running, start it:"
echo "   cd $BACKEND_DIR"
echo "   python app.py"
echo ""
echo "3. Check Nginx error logs if issues persist:"
echo "   sudo tail -f /var/log/nginx/error.log"
echo ""
echo "4. Verify frontend files exist:"
echo "   ls -la $FRONTEND_DIR/dist"
echo ""

