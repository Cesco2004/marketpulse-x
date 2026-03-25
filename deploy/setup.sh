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

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy your .env file to ~/quantum-brief/.env"
echo "  2. Copy twikit_cookies.json to ~/quantum-brief/data/"
echo "  3. (Optional) Copy your database: scp quantum_brief.db ubuntu@<ip>:~/quantum-brief/data/"
echo "  4. Start the service: sudo systemctl start quantum-brief"
echo "  5. Check logs: sudo journalctl -u quantum-brief -f"
echo "  6. Access dashboard: ssh -L 5001:localhost:5001 ubuntu@<ip>"
echo "     Then open http://localhost:5001"
echo ""
