#!/bin/bash
# Setup script for Oracle Cloud / Ubuntu server
# Run as: bash deploy/setup.sh

set -e

echo "=== Quantum Brief Server Setup ==="

# Install Python 3.11
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev git

# Create project directory
mkdir -p ~/quantum-brief
cd ~/quantum-brief

# If repo not cloned yet, prompt for it
if [ ! -f "main.py" ]; then
    echo ""
    echo "Copy your project files to ~/quantum-brief/ first."
    echo "Options:"
    echo "  - git clone <your-repo-url> ~/quantum-brief"
    echo "  - scp -r /path/to/Bot\\ twitter/* ubuntu@<ip>:~/quantum-brief/"
    echo ""
    exit 1
fi

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create data directory
mkdir -p data

# Install systemd service
sudo cp deploy/quantum-brief.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable quantum-brief

# Install Tailscale (private VPN for secure dashboard access)
echo ""
echo "=== Installing Tailscale ==="
curl -fsSL https://tailscale.com/install.sh | sh
echo ""
echo "Run 'sudo tailscale up' to connect this VM to your Tailscale network."
echo "It will display a link to open in your browser to authenticate."

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy your .env file to ~/quantum-brief/.env"
echo "     Required new vars: DASHBOARD_USER, DASHBOARD_PASSWORD, FLASK_SECRET_KEY"
echo "     Generate password:  python3 -c \"import secrets; print(secrets.token_urlsafe(24))\""
echo "     Generate flask key: python3 -c \"import secrets; print(secrets.token_hex(32))\""
echo "  2. Copy twikit_cookies.json to ~/quantum-brief/data/"
echo "  3. (Optional) Copy your database: scp quantum_brief.db ubuntu@<ip>:~/quantum-brief/data/"
echo "  4. Connect Tailscale: sudo tailscale up"
echo "  5. Start the service: sudo systemctl start quantum-brief"
echo "  6. Check logs: sudo journalctl -u quantum-brief -f"
echo "  7. Get Tailscale IP: tailscale ip -4"
echo "  8. Install Tailscale on your Mac: brew install tailscale"
echo "  9. Access dashboard: http://<tailscale-ip>:5001"
echo ""
