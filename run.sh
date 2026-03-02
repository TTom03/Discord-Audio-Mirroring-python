#!/usr/bin/env bash
# ─────────────────────────────────────────────
#  run.sh – Install dependencies and run the bot
# ─────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create .env from example if it doesn't exist yet
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "  ✗  .env file created from .env.example"
    echo "     → Edit it with your credentials before running again."
    echo ""
    exit 1
fi

# Ensure python3-venv is installed (Debian / Ubuntu)
if command -v apt-get &>/dev/null; then
    if ! python3 -m venv --help &>/dev/null; then
        echo "Installing python3-venv …"
        apt-get install -y python3-venv python3-pip
    fi
fi

# Remove a broken/empty venv if activate is missing
if [ -d venv ] && [ ! -f venv/bin/activate ]; then
    echo "Removing broken virtual environment …"
    rm -rf venv
fi

# Create virtual environment if needed
if [ ! -d venv ]; then
    echo "Creating Python virtual environment …"
    python3 -m venv venv
fi

# Verify venv was created successfully
if [ ! -f venv/bin/activate ]; then
    echo ""
    echo "  ✗  Failed to create virtual environment."
    echo "     Try running manually:"
    echo "       python3 -m venv venv"
    echo ""
    exit 1
fi

# Activate venv
source venv/bin/activate

# Install / upgrade dependencies
echo "Installing dependencies …"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo ""
echo "Starting Voice Bridge bot …"
echo ""
exec python bot.py
