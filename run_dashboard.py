#!/usr/bin/env python3
"""Launch the Quantum Brief Dashboard on localhost:5000"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dashboard.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  Quantum Brief Dashboard")
    print(f"  http://localhost:{port}\n")
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, port=port, host="0.0.0.0", use_reloader=False)
