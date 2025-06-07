# App package initialization
from flask import Flask
from flask_pymongo import PyMongo
import os

# Initialize extensions
mongo = PyMongo()

def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
    app.config['MONGO_URI'] = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/dental_portal')
    
    # Initialize extensions
    mongo.init_app(app)
    
    # Register blueprints
    from .routes import (
        main_bp, auth_bp, appointments_bp, 
        clinics_bp, patients_bp, treatments_bp, charts_bp
    )
    
    if main_bp:
        app.register_blueprint(main_bp)
    if auth_bp:
        app.register_blueprint(auth_bp, url_prefix='/auth')
    if appointments_bp:
        app.register_blueprint(appointments_bp, url_prefix='/appointments')
    if clinics_bp:
        app.register_blueprint(clinics_bp, url_prefix='/clinics')
    if patients_bp:
        app.register_blueprint(patients_bp, url_prefix='/patients')
    if treatments_bp:
        app.register_blueprint(treatments_bp, url_prefix='/treatments')
    if charts_bp:
        app.register_blueprint(charts_bp, url_prefix='/charts')
    
    return app