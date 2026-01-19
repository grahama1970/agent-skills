#!/usr/bin/env bash
#
# Install Pi Agent Extensions
#
# Copies hooks, tools, and services to ~/.pi/agent/
# Installs npm dependencies for the Switchboard service
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$HOME/.pi/agent"

echo "Installing Pi Agent Extensions..."
echo "Source: $SCRIPT_DIR"
echo "Target: $PI_DIR"
echo ""

# Create directories
mkdir -p "$PI_DIR/hooks"
mkdir -p "$PI_DIR/tools"
mkdir -p "$PI_DIR/services/switchboard"

# Install hooks
echo "Installing hooks..."
for hook in "$SCRIPT_DIR/hooks/"*.ts; do
    if [ -f "$hook" ]; then
        name=$(basename "$hook")
        cp "$hook" "$PI_DIR/hooks/$name"
        echo "  - $name"
    fi
done

# Install tools
echo "Installing tools..."
for tool_dir in "$SCRIPT_DIR/tools/"*/; do
    if [ -d "$tool_dir" ]; then
        name=$(basename "$tool_dir")
        mkdir -p "$PI_DIR/tools/$name"
        cp -r "$tool_dir"* "$PI_DIR/tools/$name/"
        echo "  - $name/"
    fi
done

# Install services
echo "Installing services..."
cp "$SCRIPT_DIR/services/switchboard.ts" "$PI_DIR/services/switchboard/index.ts"
cp "$SCRIPT_DIR/services/switchboard.sh" "$PI_DIR/services/switchboard/switchboard.sh"
cp "$SCRIPT_DIR/services/package.json" "$PI_DIR/services/switchboard/package.json"
chmod +x "$PI_DIR/services/switchboard/switchboard.sh"
echo "  - switchboard/"

# Install npm dependencies
echo ""
echo "Installing Switchboard dependencies..."
cd "$PI_DIR/services/switchboard"
npm install --silent
echo "  - Dependencies installed"

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Start the Switchboard:"
echo "     $PI_DIR/services/switchboard/switchboard.sh start"
echo ""
echo "  2. Verify it's running:"
echo "     curl http://127.0.0.1:7890/health"
echo ""
echo "  3. In a Pi agent session, test messaging:"
echo "     emit_message(action=\"status\")"
echo ""
echo "  4. (Optional) Auto-start on login - add to ~/.bashrc:"
echo "     if ! pgrep -f \"pi-switchboard\" > /dev/null; then"
echo "         $PI_DIR/services/switchboard/switchboard.sh start &>/dev/null"
echo "     fi"
