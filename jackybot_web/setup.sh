#!/bin/bash

set -e

echo "========================================="
echo "JackyBot Web UI - Complete Setup Script"
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
echo "Backend directory: $BACKEND_DIR"
echo "Frontend directory: $FRONTEND_DIR"
echo ""

read -p "Make sure jackybot.xyz DNS points to $VPS_IP. Press Enter to continue..."
echo ""

check_command() {
    if ! command -v $1 &> /dev/null; then
        return 1
    fi
    return 0
}

echo "========================================="
echo "Step 1: Installing system dependencies"
echo "========================================="
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
else
    echo "Error: Could not detect package manager. Please install dependencies manually."
    exit 1
fi

echo ">>> System dependencies installed"
echo ">>> Python version: $(python3 --version)"
echo ">>> Node.js version: $(node --version)"
echo ">>> npm version: $(npm --version)"
echo ""

echo "========================================="
echo "Step 2: Setting up Python backend"
echo "========================================="
echo ">>> Creating Python virtual environment..."
if [ ! -d "$BACKEND_DIR/venv" ]; then
    python3 -m venv "$BACKEND_DIR/venv"
fi

source "$BACKEND_DIR/venv/bin/activate"
pip install --upgrade pip --quiet
echo ">>> Installing Python dependencies..."
pip install -r "$BACKEND_DIR/requirements.txt" --quiet
echo ">>> Python backend setup complete"
echo ""

echo "========================================="
echo "Step 3: Setting up frontend"
echo "========================================="
cd "$FRONTEND_DIR"
echo ">>> Installing Node.js dependencies..."
if [ ! -d "node_modules" ]; then
    npm install
else
    echo ">>> node_modules exists, running npm install to update..."
    npm install
fi

echo ">>> Building frontend for production..."
npm run build

if [ ! -d "dist" ]; then
    echo "ERROR: Frontend build failed! dist directory not found."
    exit 1
fi

echo ">>> Frontend built successfully"
cd "$SCRIPT_DIR"
echo ""

echo "========================================="
echo "Step 4: Configuring environment variables"
echo "========================================="
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo ">>> Creating .env file from template..."
    cp "$SCRIPT_DIR/env_example.txt" "$ENV_FILE"
else
    echo ">>> .env file already exists, updating values..."
fi

SECRET_KEY=$(openssl rand -hex 32)
sed -i "s|FLASK_SECRET_KEY=.*|FLASK_SECRET_KEY=$SECRET_KEY|" "$ENV_FILE" 2>/dev/null || \
    echo "FLASK_SECRET_KEY=$SECRET_KEY" >> "$ENV_FILE"
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

echo "========================================="
echo "Step 5: Configuring Nginx"
echo "========================================="
NGINX_CONFIG="/etc/nginx/sites-available/jackybot-web"

echo ">>> Creating Nginx configuration (HTTP first, SSL will be added)..."
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

echo ">>> Testing Nginx configuration..."
sudo nginx -t
echo ">>> Reloading Nginx..."
sudo systemctl reload nginx
echo ">>> Nginx configured (HTTP)"
echo ""

echo "========================================="
echo "Step 6: Setting up SSL/HTTPS"
echo "========================================="
read -p "Enter your email for Let's Encrypt notifications: " EMAIL
echo ">>> Requesting SSL certificate (this may take a moment)..."
sudo certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos --email "$EMAIL" --redirect || {
    echo ">>> SSL certificate setup failed. Running interactively..."
    sudo certbot --nginx -d "$DOMAIN_NAME"
}

sudo systemctl reload nginx
echo ">>> SSL certificate installed and HTTPS configured"
echo ""

echo "========================================="
echo "Step 7: Setting file permissions"
echo "========================================="

NGINX_USER="www-data"
if id "nginx" &>/dev/null; then
    NGINX_USER="nginx"
fi

echo ">>> Detected nginx user: $NGINX_USER"
echo ">>> Making parent directories traversable for nginx..."

PROJECT_PARENT="$(dirname "$PROJECT_ROOT")"
if [ "$PROJECT_PARENT" = "/root" ] || [ "$(dirname "$PROJECT_PARENT")" = "/root" ]; then
    echo ">>> Setting execute permission on parent directories (for traversal)..."
    sudo chmod 755 /root 2>/dev/null || true
    sudo chmod 755 "$PROJECT_PARENT" 2>/dev/null || true
    sudo chmod 755 "$PROJECT_ROOT" 2>/dev/null || true
fi

echo ">>> Setting ownership and permissions on dist directory..."
sudo chown -R $NGINX_USER:$NGINX_USER "$FRONTEND_DIR/dist" 2>/dev/null || \
    echo ">>> Warning: Could not set ownership, may need manual adjustment"
sudo chmod -R 755 "$FRONTEND_DIR/dist" 2>/dev/null || true

echo ">>> Permissions set"
echo ""

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "All components have been set up:"
echo "  ✓ System dependencies installed"
echo "  ✓ Python backend dependencies installed"
echo "  ✓ Frontend built for production"
echo "  ✓ Environment variables configured"
echo "  ✓ Nginx configured"
echo "  ✓ SSL/HTTPS enabled"
echo ""
echo "========================================="
echo "Next Steps - Start Services Manually"
echo "========================================="
echo ""
echo "1. Verify .env file has Discord credentials:"
echo "   $ENV_FILE"
echo "   Required: DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET"
echo ""
echo "2. Update Discord OAuth2 redirect URI in Discord Developer Portal:"
echo "   https://jackybot.xyz/auth/callback"
echo ""
echo "3. Start the backend (Terminal 1):"
echo "   cd $BACKEND_DIR"
echo "   python app.py"
echo ""
echo "4. Start the frontend (Terminal 2 - optional for development):"
echo "   cd $SCRIPT_DIR"
echo "   ./start_frontend.sh"
echo ""
echo "   Note: For production, frontend is already built and served by Nginx"
echo ""
echo "5. Verify Nginx is running:"
echo "   sudo systemctl status nginx"
echo ""
echo "6. Access your web interface at:"
echo "   https://jackybot.xyz"
echo ""
echo "========================================="
echo "Useful Commands"
echo "========================================="
echo "  Restart Nginx:      sudo systemctl restart nginx"
echo "  Check Nginx logs:   sudo tail -f /var/log/nginx/error.log"
echo "  Check Nginx access: sudo tail -f /var/log/nginx/access.log"
echo "  Test Nginx config:  sudo nginx -t"
echo "  Renew SSL cert:     sudo certbot renew"
echo ""

