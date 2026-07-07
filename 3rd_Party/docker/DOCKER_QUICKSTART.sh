#!/bin/bash
# DOCKER_QUICKSTART.sh — One-command setup and launch

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "=========================================="
echo "LLM_From_Scratch Docker Quick Start"
echo "=========================================="
echo ""

# Check Docker is installed
if ! command -v docker &> /dev/null && ! command -v /usr/local/bin/docker &> /dev/null && ! command -v /opt/homebrew/bin/docker &> /dev/null; then
    echo "❌ Docker is not installed."
    echo ""
    echo "Install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

echo "✓ Docker found"

# Check .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "❌ .env file not found in $SCRIPT_DIR"
    echo ""
    echo "Create a .env file with your ANTHROPIC_API_KEY:"
    echo "  ANTHROPIC_API_KEY=sk-ant-..."
    exit 1
fi

echo "✓ .env file found"
echo ""

# Navigate to Bolt folder
cd "$SCRIPT_DIR"

# Build and start container
echo "Starting Docker container..."
echo "(First run will take 2-3 minutes to build and install packages)"
echo ""

docker-compose up -d --build

echo ""
echo "✓ Container started!"
echo ""
echo "Next steps:"
echo "  1. Enter the container:"
echo "     docker-compose exec llm-from-scratch bash"
echo ""
echo "  2. Test it works:"
echo "     python3 hello_llm.py"
echo ""
echo "  3. Start Jupyter (optional):"
echo "     jupyter notebook --ip=0.0.0.0 --no-browser --allow-root"
echo "     Then open http://localhost:8888"
echo ""
echo "  4. Stop the container when done:"
echo "     docker-compose down"
echo ""
echo "=========================================="
