#!/bin/bash

set -e

echo "========================================="
echo "Quick Setup for jackybot.xyz"
echo "========================================="
echo ""

DOMAIN_NAME="jackybot.xyz"
VPS_IP="91.98.193.41"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "Domain: $DOMAIN_NAME"
echo "VPS IP: $VPS_IP"
echo "Project root: $PROJECT_ROOT"
echo ""

read -p "Make sure jackybot.xyz DNS points to $VPS_IP. Press Enter to continue..."
echo ""

echo ">>> Step 1: Updating environment variables..."
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env file..."
    cp "$SCRIPT_DIR/env_example.txt" "$ENV_FILE"
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s/FLASK_SECRET_KEY=.*/FLASK_SECRET_KEY=$SECRET_KEY/" "$ENV_FILE"
    echo ">>> Generated FLASK_SECRET_KEY automatically"
    echo ""
    echo "IMPORTANT: Edit $ENV_FILE and add your Discord credentials:"
    echo "  - DISCORD_CLIENT_ID"
    echo "  - DISCORD_CLIENT_SECRET"
    echo ""
    read -p "Press Enter after updating .env file..."
else
    echo ">>> .env file already exists"
    read -p "Make sure DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, and other values are set correctly. Press Enter to continue..."
fi

echo ""
echo ">>> Step 2: Configuring Nginx..."
NGINX_CONFIG="/etc/nginx/sites-available/jackybot-web"

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

if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
fi

sudo nginx -t
sudo systemctl reload nginx

echo ">>> Nginx configured"
echo ""

echo ">>> Step 3: Setting up SSL certificate..."
read -p "Enter your email for Let's Encrypt notifications: " EMAIL
sudo certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos --email "$EMAIL" || {
    echo ">>> SSL certificate setup failed. Running interactively..."
    sudo certbot --nginx -d "$DOMAIN_NAME"
}

sudo systemctl reload nginx
echo ">>> SSL certificate installed"
echo ""

echo ">>> Step 4: Ensuring frontend is built..."
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build
cd "$SCRIPT_DIR"
echo ">>> Frontend built"
echo ""

echo ">>> Step 5: Setting file permissions..."
sudo chown -R www-data:www-data "$FRONTEND_DIR/dist"
echo ">>> Permissions set"
echo ""

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Make sure your .env file has all required values:"
echo "   - DISCORD_CLIENT_ID"
echo "   - DISCORD_CLIENT_SECRET"
echo "   - DISCORD_REDIRECT_URI=https://jackybot.xyz/auth/callback"
echo "   - WEB_INTERFACE_URL=https://jackybot.xyz"
echo "   - CORS_ORIGINS=https://jackybot.xyz"
echo ""
echo "2. Update Discord OAuth2 redirect URI in Discord Developer Portal:"
echo "   https://jackybot.xyz/auth/callback"
echo ""
echo "3. Start the backend service:"
echo "   sudo systemctl start jackybot-web-backend"
echo "   sudo systemctl enable jackybot-web-backend"
echo ""
echo "4. Access your web interface at:"
echo "   https://jackybot.xyz"
echo ""
echo "5. Check status:"
echo "   sudo systemctl status jackybot-web-backend"
echo "   sudo systemctl status nginx"
echo ""

