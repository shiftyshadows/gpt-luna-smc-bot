#!/usr/bin/env python3
"""
Blueprint Manager for API Views

This module creates the `app_views` Blueprint to manage all API routes.
Each route module (inside `api/routes/`) registers itself to `app_views`.
"""

from flask import Blueprint

# ✅ Define a single Blueprint for all API routes
app_views = Blueprint("app_views", __name__, url_prefix="/api")

# ✅ Import routes after app_views is defined (prevents circular imports)
from src.api.routes import Oauth  # ✅ This will attach decorated routes automatically
