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

check_command() {
    if ! command -v $1 &> /dev/null; then
        return 1
    fi
    return 0
}

echo ">>> Step 0: Installing system dependencies (if needed)..."
if check_command apt-get; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv curl nginx certbot python3-certbot-nginx || true
    if ! check_command node; then
        echo ">>> Installing Node.js via NodeSource..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
elif check_command yum; then
    sudo yum install -y python3 python3-pip curl nginx certbot python3-certbot-nginx || true
    if ! check_command node; then
        echo ">>> Installing Node.js via NodeSource..."
        curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
        sudo yum install -y nodejs
    fi
elif check_command dnf; then
    sudo dnf install -y python3 python3-pip curl nginx certbot python3-certbot-nginx || true
    if ! check_command node; then
        echo ">>> Installing Node.js via NodeSource..."
        curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
        sudo dnf install -y nodejs
    fi
fi
echo ""

echo ">>> Step 1: Setting up Python virtual environment..."
if [ ! -d "$BACKEND_DIR/venv" ]; then
    python3 -m venv "$BACKEND_DIR/venv"
fi

source "$BACKEND_DIR/venv/bin/activate"
pip install --upgrade pip --quiet
pip install -r "$BACKEND_DIR/requirements.txt" --quiet
echo ">>> Python virtual environment ready"
echo ""

echo ">>> Step 2: Updating environment variables..."
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env file..."
    cp "$SCRIPT_DIR/env_example.txt" "$ENV_FILE"
fi

SECRET_KEY=$(openssl rand -hex 32)
sed -i "s|FLASK_SECRET_KEY=.*|FLASK_SECRET_KEY=$SECRET_KEY|" "$ENV_FILE"
sed -i "s|DISCORD_REDIRECT_URI=.*|DISCORD_REDIRECT_URI=https://jackybot.xyz/auth/callback|" "$ENV_FILE"
sed -i "s|WEB_INTERFACE_URL=.*|WEB_INTERFACE_URL=https://jackybot.xyz|" "$ENV_FILE"
sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=https://jackybot.xyz|" "$ENV_FILE"

echo ">>> Updated .env file with jackybot.xyz URLs"
echo ">>> Generated FLASK_SECRET_KEY automatically"
echo ""
echo "IMPORTANT: Make sure $ENV_FILE has your Discord credentials:"
echo "  - DISCORD_CLIENT_ID=your_client_id"
echo "  - DISCORD_CLIENT_SECRET=your_client_secret"
echo ""
read -p "Press Enter after verifying/updating Discord credentials in .env file..."

echo ""
echo ">>> Step 3: Configuring Nginx (HTTP first, SSL will be added by certbot)..."
NGINX_CONFIG="/etc/nginx/sites-available/jackybot-web"

# Create initial HTTP-only config for certbot to work
sudo tee "$NGINX_CONFIG" > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN_NAME;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
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

sudo ln -sf "$NGINX_CONFIG" /etc/nginx/sites-enabled/jackybot-web

if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
fi

sudo nginx -t
sudo systemctl reload nginx

echo ">>> Nginx configured (HTTP)"
echo ""

echo ">>> Step 4: Setting up SSL certificate with Let's Encrypt..."
read -p "Enter your email for Let's Encrypt notifications: " EMAIL
echo ">>> Requesting SSL certificate (this may take a moment)..."
sudo certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos --email "$EMAIL" --redirect || {
    echo ">>> SSL certificate setup failed. Running interactively..."
    sudo certbot --nginx -d "$DOMAIN_NAME"
}

sudo systemctl reload nginx
echo ">>> SSL certificate installed and HTTPS configured"
echo ""

echo ">>> Step 5: Ensuring frontend is built..."
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build
cd "$SCRIPT_DIR"
echo ">>> Frontend built"
echo ""

echo ">>> Step 6: Setting file permissions..."
sudo chown -R www-data:www-data "$FRONTEND_DIR/dist" 2>/dev/null || sudo chown -R nginx:nginx "$FRONTEND_DIR/dist" 2>/dev/null || echo ">>> Note: Could not set ownership, may need manual adjustment"
echo ">>> Permissions set"
echo ""

echo ">>> Step 7: Creating systemd service..."
VPS_USER=${SUDO_USER:-$USER}
if [ "$VPS_USER" = "root" ]; then
    VPS_USER=$(who | awk '{print $1}' | head -1)
fi

read -p "Enter VPS user for the service (default: $VPS_USER): " INPUT_USER
VPS_USER=${INPUT_USER:-$VPS_USER}

SERVICE_FILE="/etc/systemd/system/jackybot-web-backend.service"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=JackyBot Web Interface Backend
After=network.target

[Service]
Type=simple
User=$VPS_USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin"
ExecStart=$BACKEND_DIR/venv/bin/python $BACKEND_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable jackybot-web-backend.service
echo ">>> Systemd service created and enabled"
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
echo "   sudo systemctl status jackybot-web-backend"
echo ""
echo "4. Verify Nginx is running:"
echo "   sudo systemctl status nginx"
echo ""
echo "5. Access your web interface at:"
echo "   https://jackybot.xyz"
echo ""
echo "6. Useful commands:"
echo "   Check backend logs: sudo journalctl -u jackybot-web-backend -f"
echo "   Restart backend: sudo systemctl restart jackybot-web-backend"
echo "   Restart Nginx: sudo systemctl restart nginx"
echo ""

