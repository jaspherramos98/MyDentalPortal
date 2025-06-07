# File: dental-portal/app_factory.py
# Application factory pattern with corrected imports

from flask import Flask
from flask_pymongo import PyMongo
from .config import get_config
from models import init_database
import os

mongo = PyMongo()

def create_app(config_name=None):
    """Application factory function"""
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app.config.from_object(get_config())
    
    # Initialize extensions
    mongo.init_app(app)
    
    # Initialize database
    with app.app_context():
        init_database(app, mongo)
    
    # Register blueprints with corrected imports
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.clinics import clinics_bp
    from app.routes.patients import patients_bp
    from app.routes.treatments import treatments_bp
    from app.routes.charts import charts_bp
    
        
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(clinics_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(treatments_bp)
    app.register_blueprint(charts_bp)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)