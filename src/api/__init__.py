#!/usr/bin/env python3
"""
API Initialization

This module ensures all API routes are imported so they are attached to `app_views`.
"""

# ✅ Import all route modules inside `api/routes/`
from src.api.routes import Oauth, ctrader, ctrader_trade # Import OAuth routes
# You can add more routes here, like:
# from src.api.routes import users, trades, etc.

# ✅ No need to define a blueprint here, `app_views` in `views/__init__.py` handles that.
