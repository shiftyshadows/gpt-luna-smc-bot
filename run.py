#!/usr/bin/env python3
"""
Run Flask Application

This script runs the Flask app using `src/` as the main module.
"""

import sys
import os

# Add src/ to the Python module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from src.app import app  # ✅ Import app after fixing path
from src.views import app_views  # ✅ Import app_views (manages all blueprints)

# Register the main blueprint containing all routes
#app.register_blueprint(app_views)

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host='0.0.0.0', port=8000, debug=debug)
