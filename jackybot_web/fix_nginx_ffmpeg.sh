#!/bin/bash

echo ">>> Fixing Nginx configuration to serve FFmpeg files..."

# Define paths
DOMAIN_NAME="jackybot.xyz"
FRONTEND_DIR="$(pwd)/frontend"
NGINX_CONFIG="/etc/nginx/sites-available/jackybot-web"

# Backup current config
sudo cp "$NGINX_CONFIG" "$NGINX_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"

echo ">>> Updating Nginx configuration to serve FFmpeg files..."

sudo tee "$NGINX_CONFIG" > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN_NAME;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location ~* \.(js|wasm)$ {
        root $FRONTEND_DIR/dist;
        add_header Cache-Control "public, max-age=31536000, immutable";
        add_header Access-Control-Allow-Origin "*";
        expires 1y;
    }

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

echo ">>> Testing Nginx configuration..."
if sudo nginx -t; then
    echo ">>> Reloading Nginx..."
    sudo systemctl reload nginx
    echo "✓ Nginx configuration updated successfully!"
    echo ""
    echo "FFmpeg files should now be accessible at:"
    echo "  - https://jackybot.xyz/ffmpeg-core.js"
    echo "  - https://jackybot.xyz/ffmpeg-core.wasm"
else
    echo "✗ Nginx configuration test failed!"
    echo "Restoring backup..."
    sudo cp "$NGINX_CONFIG.backup.*" "$NGINX_CONFIG" 2>/dev/null || echo "No backup found"
    exit 1
fi