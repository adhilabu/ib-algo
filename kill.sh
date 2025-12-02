#!/bin/bash

# IB Algo Trading Shutdown Script
# This script stops all components of the trading system

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  IB Algo Trading - Shutdown Script${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Function to gracefully stop trading
stop_trading() {
    echo -e "${BLUE}🛑 Stopping trading bot...${NC}"
    if curl -s -X POST http://localhost:8005/stop > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Trading bot stopped gracefully${NC}"
        sleep 2
    else
        echo -e "${YELLOW}⚠️  Could not stop trading via API (service may not be running)${NC}"
    fi
}

# Stop trading first (graceful shutdown)
stop_trading

# Stop FastAPI
if [ -f "logs/fastapi.pid" ]; then
    FASTAPI_PID=$(cat logs/fastapi.pid)
    echo -e "${BLUE}🛑 Stopping FastAPI (PID: $FASTAPI_PID)...${NC}"
    
    if kill -0 $FASTAPI_PID 2>/dev/null; then
        kill $FASTAPI_PID
        sleep 2
        
        # Force kill if still running
        if kill -0 $FASTAPI_PID 2>/dev/null; then
            echo -e "${YELLOW}⚠️  Force killing FastAPI...${NC}"
            kill -9 $FASTAPI_PID
        fi
        
        echo -e "${GREEN}✅ FastAPI stopped${NC}"
    else
        echo -e "${YELLOW}⚠️  FastAPI process not found${NC}"
    fi
    
    rm logs/fastapi.pid
else
    echo -e "${YELLOW}⚠️  FastAPI PID file not found${NC}"
fi

# Fallback: kill any uvicorn processes
pkill -f "uvicorn app.main:app" || true

# Stop Streamlit
if [ -f "logs/streamlit.pid" ]; then
    STREAMLIT_PID=$(cat logs/streamlit.pid)
    echo -e "${BLUE}🛑 Stopping Streamlit (PID: $STREAMLIT_PID)...${NC}"
    
    if kill -0 $STREAMLIT_PID 2>/dev/null; then
        kill $STREAMLIT_PID
        sleep 1
        
        # Force kill if still running
        if kill -0 $STREAMLIT_PID 2>/dev/null; then
            echo -e "${YELLOW}⚠️  Force killing Streamlit...${NC}"
            kill -9 $STREAMLIT_PID
        fi
        
        echo -e "${GREEN}✅ Streamlit stopped${NC}"
    else
        echo -e "${YELLOW}⚠️  Streamlit process not found${NC}"
    fi
    
    rm logs/streamlit.pid
else
    echo -e "${YELLOW}⚠️  Streamlit PID file not found${NC}"
fi

# Fallback: kill any streamlit processes
pkill -f "streamlit run" || true

# Ask if user wants to stop PostgreSQL
echo ""
read -p "$(echo -e ${YELLOW}🐘 Stop PostgreSQL container? [y/N]: ${NC})" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🛑 Stopping PostgreSQL...${NC}"
    docker compose down
    echo -e "${GREEN}✅ PostgreSQL stopped${NC}"
else
    echo -e "${YELLOW}ℹ️  PostgreSQL container left running${NC}"
fi

# Clean up any hanging Python processes related to the project
echo -e "${BLUE}🧹 Cleaning up...${NC}"
sleep 1

# Display summary
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Shutdown Complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}📊 Status:${NC}"
echo -e "   • FastAPI:     ${RED}Stopped${NC}"
echo -e "   • Streamlit:   ${RED}Stopped${NC}"

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "   • PostgreSQL:  ${RED}Stopped${NC}"
else
    echo -e "   • PostgreSQL:  ${GREEN}Running${NC}"
fi

echo ""
echo -e "${BLUE}📝 Logs Preserved:${NC}"
echo -e "   • FastAPI:     ${YELLOW}logs/fastapi.log${NC}"
echo -e "   • Streamlit:   ${YELLOW}logs/streamlit.log${NC}"
echo -e "   • Trading:     ${YELLOW}logs/trading.log${NC}"
echo ""
echo -e "${BLUE}🚀 Restart:${NC}"
echo -e "   • Run:         ${YELLOW}./deploy.sh${NC}"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
