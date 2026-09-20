#!/usr/bin/env python3
"""
Application Initialization

This module imports `app` from `app.py` and registers all API blueprints
via `app_views` from `src/views/`.
"""

import sys
import os

# Add src/ to the Python module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

#from src.app import app  # ✅ Import the Flask app instance
#from src.views import app_views  # ✅ Import app_views (manages all blueprints)

# Register the main blueprint containing all routes
#app.register_blueprint(app_views)
