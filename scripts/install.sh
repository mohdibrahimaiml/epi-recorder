#!/bin/bash
# EPI Recorder Universal Installation Script for Unix/Mac
# Usage: curl -sSL https://install.epilabs.org/epi.sh | sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  EPI Recorder - Universal Installer   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux*)     OS_TYPE=Linux;;
    Darwin*)    OS_TYPE=Mac;;
    *)          OS_TYPE="UNKNOWN";;
esac

echo -e "${BLUE}→${NC} Detected OS: ${GREEN}$OS_TYPE${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found!${NC}"
    echo -e "  Please install Python 3.11+ first"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${BLUE}→${NC} Python version: ${GREEN}$PYTHON_VERSION${NC}"
echo ""

# Install EPI via pip
echo -e "${BLUE}→${NC} Installing EPI Recorder..."
python3 -m pip install --user --upgrade epi-recorder

# Get the user's Scripts/bin directory
if [ "$OS_TYPE" = "Mac" ] || [ "$OS_TYPE" = "Linux" ]; then
    SCRIPTS_DIR=$(python3 -c "import site; import os; print(os.path.join(site.USER_BASE, 'bin'))")
else
    SCRIPTS_DIR=$(python3 -c "import site; import os; print(os.path.join(site.USER_BASE, 'bin'))")
fi

echo -e "${BLUE}→${NC} Scripts directory: ${YELLOW}$SCRIPTS_DIR${NC}"

# Detect shell and config file
SHELL_NAME=$(basename "$SHELL")
case "$SHELL_NAME" in
    bash)
        SHELL_RC="$HOME/.bashrc"
        [ -f "$HOME/.bash_profile" ] && SHELL_RC="$HOME/.bash_profile"
        ;;
    zsh)
        SHELL_RC="$HOME/.zshrc"
        ;;
    fish)
        SHELL_RC="$HOME/.config/fish/config.fish"
        ;;
    *)
        SHELL_RC="$HOME/.profile"
        ;;
esac

echo -e "${BLUE}→${NC} Shell detected: ${GREEN}$SHELL_NAME${NC}"
echo -e "${BLUE}→${NC} Config file: ${YELLOW}$SHELL_RC${NC}"

# Add to PATH if not already there
if [[ ":$PATH:" != *":$SCRIPTS_DIR:"* ]]; then
    echo ""
    echo -e "${YELLOW}➜${NC} Adding EPI to PATH in $SHELL_RC..."
    
    # Add to shell config
    if [ "$SHELL_NAME" = "fish" ]; then
        echo "set -gx PATH \$PATH $SCRIPTS_DIR" >> "$SHELL_RC"
    else
        echo "" >> "$SHELL_RC"
        echo "# EPI Recorder" >> "$SHELL_RC"
        echo "export PATH=\"\$PATH:$SCRIPTS_DIR\"" >> "$SHELL_RC"
    fi
    
    # Also add to current session
    export PATH="$PATH:$SCRIPTS_DIR"
    
    echo -e "${GREEN}✓${NC} PATH updated"
else
    echo -e "${GREEN}✓${NC} PATH already contains Scripts directory"
fi

echo ""
echo -e "${BLUE}→${NC} Verifying installation..."

# Test if epi command works
if command -v epi &> /dev/null; then
    EPI_VERSION=$(epi version 2>&1 | grep -i 'version' | head -n1 || echo "installed")
    echo -e "${GREEN}✓ EPI command is available!${NC}"
    echo -e "  $EPI_VERSION"
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║    Installation Successful! 🎉         ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BLUE}Quick Start:${NC}"
    echo -e "  ${GREEN}epi init${NC}           # Interactive setup wizard"
    echo -e "  ${GREEN}epi run script.py${NC}  # Record your first script"
    echo ""
    echo -e "${YELLOW}Note:${NC} If 'epi' command doesn't work immediately,"
    echo -e "      restart your terminal or run: ${BLUE}source $SHELL_RC${NC}"
else
    echo -e "${YELLOW}⚠ EPI installed but command not immediately available${NC}"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo -e "  1. Close and reopen your terminal"
    echo -e "  2. Or run: ${GREEN}source $SHELL_RC${NC}"
    echo -e "  3. Then try: ${GREEN}epi init${NC}"
    echo ""
    echo -e "${YELLOW}Alternative:${NC} Use ${BLUE}python3 -m epi_cli${NC} (works immediately)"
fi

echo ""
echo -e "${BLUE}Documentation:${NC} https://github.com/mohdibrahimaiml/EPI-V2.2.0"
echo -e "${BLUE}Issues:${NC} https://github.com/mohdibrahimaiml/EPI-V2.2.0/issues"

