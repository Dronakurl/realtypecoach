#!/bin/bash
# PostgreSQL VPS Setup Script for RealTypeCoach
#
# This script sets up a PostgreSQL database on a VPS using Docker Compose.
# Run this script on your VPS (e.g., dronakurl.duckdns.org)
#
# Usage: ./setup_postgres_vps.sh

set -e

echo "=== RealTypeCoach PostgreSQL VPS Setup ==="
echo ""

# Configuration
PROJECT_DIR="$HOME/realtypecoach-db"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_DIR/.env"
POSTGRES_PORT=5432
CERTS_DIR="$PROJECT_DIR/certs"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed."
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose is not available."
    echo "Please install Docker Compose first."
    exit 1
fi

# Create project directory
echo "Creating project directory: $PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Generate a secure random password
if [ ! -f "$ENV_FILE" ]; then
    echo "Generating secure password..."
    POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "Password generated and stored in $ENV_FILE"
else
    echo "Using existing password from $ENV_FILE"
    source "$ENV_FILE"
fi

# Generate SSL certificates
echo "Generating SSL certificates..."
mkdir -p "$CERTS_DIR"

if [ ! -f "$CERTS_DIR/server.crt" ]; then
    openssl req -new -x509 -days 3650 -nodes \
        -out "$CERTS_DIR/server.crt" \
        -keyout "$CERTS_DIR/server.key" \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=$(hostname -f | head -n1 || echo 'localhost')"
    chmod 600 "$CERTS_DIR/server.key"
    chmod 644 "$CERTS_DIR/server.crt"
    echo "SSL certificates generated in $CERTS_DIR"
else
    echo "Using existing SSL certificates"
fi

# Create docker-compose.yml
echo "Creating docker-compose.yml..."
cat > "$COMPOSE_FILE" << 'EOF'
services:
  postgres:
    image: postgres:16-alpine
    container_name: realtypecoach_db
    restart: unless-stopped
    command:
      - "postgres"
      - "-c"
      - "ssl=on"
      - "-c"
      - "ssl_cert_file=/var/lib/postgresql/certs/server.crt"
      - "-c"
      - "ssl_key_file=/var/lib/postgresql/certs/server.key"
    environment:
      POSTGRES_DB: realtypecoach
      POSTGRES_USER: realtypecoach
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./certs:/var/lib/postgresql/certs:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U realtypecoach -d realtypecoach"]
      interval: 30s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M

volumes:
  postgres_data:
    driver: local
EOF

# Open firewall port (UFW)
echo "Configuring firewall..."
if command -v ufw &> /dev/null; then
    echo "Opening PostgreSQL port (5432) in UFW..."
    sudo ufw allow $POSTGRES_PORT/tcp
    sudo ufw reload
    echo "Firewall configured."
else
    echo "Warning: UFW not found. Please manually open port $POSTGRES_PORT/tcp if needed."
fi

# Start PostgreSQL container
echo "Starting PostgreSQL container..."
docker compose up -d

# Wait for container to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 5

# Verify container is running
if docker compose ps | grep -q "realtypecoach_db.*Up"; then
    echo "PostgreSQL container is running!"
else
    echo "Error: PostgreSQL container failed to start."
    echo "Check logs with: docker compose logs postgres"
    exit 1
fi

# Test connection
echo "Testing database connection..."
if docker compose exec -T postgres psql -U realtypecoach -d realtypecoach -c "SELECT version();" > /dev/null; then
    echo "Database connection successful!"
else
    echo "Warning: Could not connect to database. Check logs."
fi

# Display connection info
echo ""
echo "=== Setup Complete! ==="
echo ""
echo "PostgreSQL database is now running on:"
echo "  Host: $(hostname -f | head -n1 || echo 'your-vps-hostname')"
echo "  Port: $POSTGRES_PORT"
echo "  Database: realtypecoach"
echo "  User: realtypecoach"
echo "  Password: $POSTGRES_PASSWORD"
echo "  SSL: Enabled (verify-full)"
echo ""
echo "To connect from your local machine:"
echo "  psql \"host=$(hostname -f | head -n1 || echo 'your-vps-hostname') port=$POSTGRES_PORT dbname=realtypecoach user=realtypecoach sslmode=require\""
echo ""
echo "IMPORTANT: For the RealTypeCoach app to connect securely:"
echo "  1. Copy the server certificate: scp $(whoami)@$(hostname -f | head -n1 || echo 'your-vps'):$CERTS_DIR/server.crt ~/realtypecoach-cert.crt"
echo "  2. In the app settings, set SSL mode to 'verify-ca' or 'verify-full'"
echo "  3. Or simply use 'require' mode to enable encryption without certificate verification"
echo ""
echo "To view logs:"
echo "  cd $PROJECT_DIR && docker compose logs -f postgres"
echo ""
echo "To stop the database:"
echo "  cd $PROJECT_DIR && docker compose down"
echo ""
echo "To start the database:"
echo "  cd $PROJECT_DIR && docker compose up -d"
echo ""
echo "IMPORTANT: Save the password above! You'll need it to configure RealTypeCoach."
