"""
Shared Flask extension instances.
Created here (unbound) and initialized in the app factory to avoid
circular imports between app/__init__.py and the models/routes modules.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access PlantPulse AI."
login_manager.login_message_category = "info"
