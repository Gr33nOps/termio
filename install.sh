#!/bin/bash

# ─────────────────────────────────────────────
#   Termio Installer — Linux
# ─────────────────────────────────────────────

TERMIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER_CONTENT="#!/bin/bash
cd \"$TERMIO_DIR\" && python3 -m termio \"\$@\""

echo ""
echo "=================================================="
echo "         Termio Installer — Linux"
echo "=================================================="
echo ""

# ── Step 1: Check Python ──────────────────────────────
echo "[ 1/6 ] Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed."
    echo "   Install it with: sudo apt install python3"
    exit 1
fi
echo "✅ Python found: $(python3 --version)"

# ── Step 2: Check Ollama ──────────────────────────────
echo ""
echo "[ 2/6 ] Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama not found. Installing now..."
    curl -fsSL https://ollama.com/install.sh | sh
    if ! command -v ollama &> /dev/null; then
        echo "❌ Ollama install failed. Install manually from https://ollama.com"
        exit 1
    fi
fi
echo "✅ Ollama found: $(ollama --version)"

# ── Step 3: Create venv ───────────────────────────────
echo ""
echo "[ 3/6 ] Setting up virtual environment..."
if [ ! -d "$TERMIO_DIR/venv" ]; then
    python3 -m venv "$TERMIO_DIR/venv"
    echo "✅ venv created"
else
    echo "✅ venv already exists"
fi

# ── Step 4: Install dependencies ─────────────────────
echo ""
echo "[ 4/6 ] Installing dependencies..."
"$TERMIO_DIR/venv/bin/pip" install --upgrade pip -q
"$TERMIO_DIR/venv/bin/pip" install -r "$TERMIO_DIR/requirements.txt" -q
echo "✅ Dependencies installed"

# ── Step 5: Create global launcher ───────────────────
echo ""
echo "[ 5/6 ] Creating global launcher..."

create_launcher_sudo() {
    sudo bash -c "echo '$LAUNCHER_CONTENT' > /usr/local/bin/termio && chmod +x /usr/local/bin/termio"
}

create_launcher_local() {
    mkdir -p "$HOME/.local/bin"
    echo "$LAUNCHER_CONTENT" > "$HOME/.local/bin/termio"
    chmod +x "$HOME/.local/bin/termio"

    # Add ~/.local/bin to PATH if not already there
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        SHELL_RC=""
        if [ -f "$HOME/.zshrc" ]; then
            SHELL_RC="$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then
            SHELL_RC="$HOME/.bashrc"
        fi

        if [ -n "$SHELL_RC" ]; then
            echo "" >> "$SHELL_RC"
            echo "# Termio" >> "$SHELL_RC"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
            echo "✅ Added ~/.local/bin to PATH in $SHELL_RC"
            echo "   Run: source $SHELL_RC"
        else
            echo "⚠️  Add this to your shell config manually:"
            echo '   export PATH="$HOME/.local/bin:$PATH"'
        fi
    fi
}

# Try /usr/local/bin first, fall back to ~/.local/bin
if [ -w "/usr/local/bin" ]; then
    echo "$LAUNCHER_CONTENT" > /usr/local/bin/termio
    chmod +x /usr/local/bin/termio
    echo "✅ Launcher created at /usr/local/bin/termio"
else
    # Try with sudo
    echo "   /usr/local/bin requires sudo. Trying..."
    if sudo bash -c "echo '$LAUNCHER_CONTENT' > /usr/local/bin/termio && chmod +x /usr/local/bin/termio" 2>/dev/null; then
        echo "✅ Launcher created at /usr/local/bin/termio"
    else
        # Fall back to ~/.local/bin (no sudo needed)
        echo "   sudo not available. Using ~/.local/bin instead..."
        create_launcher_local
        echo "✅ Launcher created at ~/.local/bin/termio"
    fi
fi

# ── Step 6: Verify ────────────────────────────────────
echo ""
echo "[ 6/6 ] Verifying..."
if command -v termio &> /dev/null; then
    echo "✅ termio command is available globally"
else
    # Reload PATH and check again
    export PATH="$HOME/.local/bin:$PATH"
    if command -v termio &> /dev/null; then
        echo "✅ termio command is available (restart terminal to use globally)"
    else
        echo "⚠️  termio not found in PATH yet."
        echo "   Restart your terminal or run:"
        echo "   source ~/.bashrc"
    fi
fi

# ── Done ──────────────────────────────────────────────
echo ""
echo "=================================================="
echo "✅ Termio is installed!"
echo ""
echo "   Start anywhere:  termio"
echo "   Pull model:      ollama pull qwen2.5-coder:3b"
echo "   Reconfigure:     type 'setup' inside Termio"
echo "=================================================="
echo ""