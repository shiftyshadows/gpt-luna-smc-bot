#!/usr/bin/env python3
"""
   This module initializes the connection between the Flask application
   and MongoDB using Flask-PyMongo.

   Functionality:
     - Loads environment variables from `.env`.
     - Initializes a global `mongo` object for database operations.
     - Configures Flask with the MongoDB URI.
     - Establishes the database connection when `init_db()` is called.

   Environment Variables:
     - `MONGO_URI`: The connection string for MongoDB.

   Usage:
      - Ensure `.env` contains `MONGO_URI=mongodb://localhost:27017/mydb`.
      - Import `init_db` in `app.py` and call `init_db(app)`.
"""
from flask_pymongo import PyMongo
from os import getenv
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a global PyMongo instance
mongo = PyMongo()


def init_db(app):
    """
       This function initializes the MongoDB connection with Flask:
         - Reads the `MONGO_URI` from environment variables.
         - Configures Flask to use this MongoDB connection.
         - Initializes the global `mongo` object.

       Args:
         - app (Flask): The Flask application instance.

    """
    app.config["MONGO_URI"] = getenv("MONGO_URI")
    if not app.config["MONGO_URI"]:
        raise ValueError("MongoDB URI is missing. Check your .env file.")

    # Initialize the MongoDB connection
    mongo.init_app(app)
    print("✅ MongoDB connected successfully.")
