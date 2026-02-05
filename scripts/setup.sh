#!/bin/bash
# Trademark Monitor Setup Script
# ===============================
# Run this script to set up the trademark monitoring system

set -e

echo "=================================================="
echo "  Trademark Monitor - Setup Script"
echo "  Relatent, Inc."
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo -e "${GREEN}Found Python $PYTHON_VERSION${NC}"
else
    echo -e "${RED}Python 3 is required but not installed.${NC}"
    exit 1
fi

# Create virtual environment
echo ""
echo -e "${YELLOW}Creating virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}Virtual environment created.${NC}"
else
    echo -e "${GREEN}Virtual environment already exists.${NC}"
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo ""
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}Dependencies installed.${NC}"

# Create necessary directories
echo ""
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p data/uspto_xml
mkdir -p logs
echo -e "${GREEN}Directories created.${NC}"

# Copy environment file if not exists
echo ""
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}.env file created. Please edit it with your settings.${NC}"
else
    echo -e "${GREEN}.env file already exists.${NC}"
fi

# Initialize database
echo ""
echo -e "${YELLOW}Initializing database...${NC}"
python3 -c "from src.database import TrademarkDatabase; db = TrademarkDatabase(); print('Database initialized.')"
echo -e "${GREEN}Database ready.${NC}"

# Test the system with sample data
echo ""
echo -e "${YELLOW}Running test with sample data...${NC}"
python3 run_monitor.py --sample --days 3

echo ""
echo "=================================================="
echo -e "${GREEN}  Setup Complete!${NC}"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your email/Slack settings"
echo "  2. Run a real scan: python run_monitor.py --days 7"
echo "  3. Launch dashboard: python run_monitor.py --dashboard"
echo ""
echo "For scheduled monitoring, set up a cron job:"
echo "  0 8 * * * cd $(pwd) && ./venv/bin/python run_monitor.py >> logs/cron.log 2>&1"
echo ""
