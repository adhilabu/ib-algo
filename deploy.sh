#!/bin/bash

# IB Algo Trading Deployment Script
# This script starts all components of the trading system

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  IB Algo Trading - Deployment Script${NC}"
echo -e "${BLUE}  LuxAlgo Smart Money Concepts Strategy${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found${NC}"
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "${BLUE}📦 Activating virtual environment...${NC}"
source venv/bin/activate

# Install/Update dependencies
echo -e "${BLUE}📥 Installing dependencies...${NC}"
pip install -q -r requirements.txt
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker Desktop.${NC}"
    exit 1
fi

# Function to pull Docker images with retry logic
pull_docker_images() {
    local max_retries=3
    local retry_count=0
    local images=("postgres:13-alpine" "redis:7-alpine")
    
    for image in "${images[@]}"; do
        echo -e "${BLUE}📥 Checking Docker image: $image${NC}"
        
        # Check if image already exists locally
        if docker image inspect "$image" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Image $image already exists locally${NC}"
            continue
        fi
        
        # Try to pull the image with retries
        retry_count=0
        while [ $retry_count -lt $max_retries ]; do
            echo -e "${BLUE}📥 Pulling $image (attempt $((retry_count + 1))/$max_retries)...${NC}"
            
            if timeout 60 docker pull "$image" > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Successfully pulled $image${NC}"
                break
            else
                retry_count=$((retry_count + 1))
                if [ $retry_count -lt $max_retries ]; then
                    echo -e "${YELLOW}⚠️  Failed to pull $image, retrying in 5 seconds...${NC}"
                    sleep 5
                else
                    echo -e "${RED}❌ Failed to pull $image after $max_retries attempts${NC}"
                    echo -e "${YELLOW}ℹ️  This might be due to:${NC}"
                    echo -e "${YELLOW}   1. Network connectivity issues${NC}"
                    echo -e "${YELLOW}   2. Docker Hub being temporarily unavailable${NC}"
                    echo -e "${YELLOW}   3. Firewall/proxy blocking Docker Hub${NC}"
                    echo -e "${YELLOW}   4. VPN interfering with Docker${NC}"
                    echo ""
                    echo -e "${BLUE}💡 Troubleshooting steps:${NC}"
                    echo -e "${BLUE}   1. Check your internet connection${NC}"
                    echo -e "${BLUE}   2. Try: docker pull $image${NC}"
                    echo -e "${BLUE}   3. Restart Docker Desktop${NC}"
                    echo -e "${BLUE}   4. If on VPN, try disconnecting temporarily${NC}"
                    echo -e "${BLUE}   5. Check Docker Hub status: https://status.docker.com/${NC}"
                    exit 1
                fi
            fi
        done
    done
}

# Pull Docker images before starting
echo -e "${BLUE}🐳 Preparing Docker images...${NC}"
pull_docker_images

# Start PostgreSQL and Redis
echo -e "${BLUE}🐘 Starting PostgreSQL and Redis...${NC}"
if docker compose up -d; then
    sleep 3  # Wait for services to initialize
    echo -e "${GREEN}✅ Services started${NC}"
else
    echo -e "${RED}❌ Failed to start services${NC}"
    echo -e "${YELLOW}ℹ️  Check docker compose logs for details${NC}"
    exit 1
fi

# Wait for PostgreSQL to be ready
echo -e "${BLUE}⏳ Waiting for PostgreSQL to be ready...${NC}"
for i in {1..30}; do
    if docker exec ib-algo-db-1 pg_isready -U postgres > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL is ready${NC}"
        break
    fi
    
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ PostgreSQL failed to start${NC}"
        exit 1
    fi
    
    sleep 1
done

# Create logs directory if it doesn't exist
if [ ! -d "logs" ]; then
    mkdir logs
    echo -e "${GREEN}✅ Logs directory created${NC}"
fi

# Check if IB is running
echo -e "${BLUE}🔍 Checking Interactive Brokers connection...${NC}"
echo -e "${YELLOW}ℹ️  Make sure TWS or IB Gateway is running and API is enabled${NC}"
echo -e "${YELLOW}ℹ️  TWS Paper: Port 7497${NC}"
echo -e "${YELLOW}ℹ️  Gateway Paper: Port 4001${NC}"

# Kill any existing FastAPI processes
echo -e "${BLUE}🧹 Cleaning up old processes...${NC}"
pkill -f "uvicorn app.main:app" || true
pkill -f "streamlit run" || true
sleep 2

# Start FastAPI backend
echo -e "${BLUE}🚀 Starting FastAPI backend...${NC}"
nohup uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
echo $FASTAPI_PID > logs/fastapi.pid
echo -e "${GREEN}✅ FastAPI started (PID: $FASTAPI_PID)${NC}"

# Wait for FastAPI to be ready
echo -e "${BLUE}⏳ Waiting for FastAPI to be ready...${NC}"
for i in {1..15}; do
    if curl -s http://localhost:8005/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ FastAPI is ready${NC}"
        break
    fi
    
    if [ $i -eq 15 ]; then
        echo -e "${RED}❌ FastAPI failed to start. Check logs/fastapi.log${NC}"
        exit 1
    fi
    
    sleep 1
done

# Ask if user wants to start Streamlit dashboard
echo ""
read -p "$(echo -e ${YELLOW}📊 Start Streamlit dashboard? [y/N]: ${NC})" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -f "ui/dashboard.py" ]; then
        echo -e "${BLUE}🚀 Starting Streamlit dashboard...${NC}"
        nohup streamlit run ui/dashboard.py --server.port 8501 > logs/streamlit.log 2>&1 &
        STREAMLIT_PID=$!
        echo $STREAMLIT_PID > logs/streamlit.pid
        echo -e "${GREEN}✅ Streamlit started (PID: $STREAMLIT_PID)${NC}"
        sleep 2
    else
        echo -e "${YELLOW}⚠️  ui/dashboard.py not found, skipping${NC}"
    fi
fi

# Run verification tests
echo ""
read -p "$(echo -e ${YELLOW}🧪 Run verification tests? [y/N]: ${NC})" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🧪 Running verification tests...${NC}"
    python verify_algo.py
fi

# Display summary
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}📡 Services:${NC}"
echo -e "   • FastAPI:     ${GREEN}http://localhost:8005${NC}"
echo -e "   • API Docs:    ${GREEN}http://localhost:8005/docs${NC}"
echo -e "   • PostgreSQL:  ${GREEN}localhost:5432${NC}"
if [ -f "logs/streamlit.pid" ]; then
    echo -e "   • Dashboard:   ${GREEN}http://localhost:8501${NC}"
fi
echo ""
echo -e "${BLUE}🎮 Control:${NC}"
echo -e "   • Start trading:  ${YELLOW}curl -X POST http://localhost:8005/start${NC}"
echo -e "   • Stop trading:   ${YELLOW}curl -X POST http://localhost:8005/stop${NC}"
echo -e "   • Check status:   ${YELLOW}curl http://localhost:8005/status${NC}"
echo ""
echo -e "${BLUE}📊 Monitoring:${NC}"
echo -e "   • FastAPI logs:   ${YELLOW}tail -f logs/fastapi.log${NC}"
echo -e "   • Trading logs:   ${YELLOW}tail -f logs/trading.log${NC}"
if [ -f "logs/streamlit.pid" ]; then
    echo -e "   • Streamlit logs: ${YELLOW}tail -f logs/streamlit.log${NC}"
fi
echo ""
echo -e "${BLUE}🛑 Shutdown:${NC}"
echo -e "   • Stop all:       ${YELLOW}./kill.sh${NC}"
echo ""
echo -e "${RED}⚠️  IMPORTANT:${NC}"
echo -e "   1. Ensure TWS/IB Gateway is running"
echo -e "   2. API must be enabled (Port 7497 or 4001)"
echo -e "   3. Start with PAPER TRADING first"
echo -e "   4. Verify structures match TradingView"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
