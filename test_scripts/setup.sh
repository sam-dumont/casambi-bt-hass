#!/bin/bash
# Quick setup script for Casambi BT network level 11 testing

set -e

echo "=================================================="
echo "Casambi BT Network Level 11 Testing Setup"
echo "=================================================="
echo ""

# Check if casambi-bt path is provided
if [ -z "$1" ]; then
    echo "Usage: ./setup.sh /path/to/casambi-bt"
    echo ""
    echo "Example:"
    echo "  ./setup.sh ~/casambi-bt"
    echo ""
    echo "This script will:"
    echo "  1. Check if the casambi-bt directory exists"
    echo "  2. Verify the MAX_VERSION fix is applied"
    echo "  3. Install dependencies"
    echo "  4. Install casambi-bt in development mode"
    echo ""
    exit 1
fi

CASAMBI_BT_PATH="$1"

# Check if directory exists
if [ ! -d "$CASAMBI_BT_PATH" ]; then
    echo "ERROR: Directory not found: $CASAMBI_BT_PATH"
    echo ""
    echo "Please clone your casambi-bt fork first:"
    echo "  git clone https://github.com/YOUR_USERNAME/casambi-bt.git"
    exit 1
fi

# Check if _client.py exists
CLIENT_FILE="$CASAMBI_BT_PATH/src/CasambiBt/_client.py"
if [ ! -f "$CLIENT_FILE" ]; then
    echo "ERROR: File not found: $CLIENT_FILE"
    echo "Is this the correct casambi-bt directory?"
    exit 1
fi

echo "✓ Found casambi-bt at: $CASAMBI_BT_PATH"
echo ""

# Check if MAX_VERSION is set to 11
echo "Checking MAX_VERSION setting..."
if grep -q "MAX_VERSION.*=.*11" "$CLIENT_FILE"; then
    echo "✓ MAX_VERSION is set to 11 (fix applied)"
else
    echo "⚠ WARNING: MAX_VERSION may not be set to 11"
    echo ""
    echo "Please edit: $CLIENT_FILE"
    echo "Change line ~29 from:"
    echo "  MAX_VERSION: Final[int] = 10"
    echo "To:"
    echo "  MAX_VERSION: Final[int] = 11"
    echo ""
    read -p "Have you applied the fix? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Please apply the fix and run this script again."
        exit 1
    fi
fi

echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Installing casambi-bt in development mode..."
pip install -e "$CASAMBI_BT_PATH"

echo ""
echo "=================================================="
echo "✓ Setup Complete!"
echo "=================================================="
echo ""
echo "You can now run the tests:"
echo "  python3 test_connection.py"
echo "  python3 debug_protocol.py"
echo ""
echo "See README.md for detailed instructions."
echo ""
