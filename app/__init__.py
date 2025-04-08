from flask import Flask

# Initialize the Flask application
app = Flask(__name__)

# Import routes after initializing the app to avoid circular imports
# We will create the routes.py file next
from app import routes