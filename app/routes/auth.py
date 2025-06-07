# File: dental-portal/routes/auth.py
# Authentication routes - login, register, logout

from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime
import re

# Import your mongo instance (you'll need to adjust this import)
from app_factory import mongo

auth_bp = Blueprint('auth', __name__)

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, "Password is valid"

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        # Validate input
        if not email or not password:
            error = 'Email and password are required'
            if request.is_json:
                return jsonify({'success': False, 'error': error}), 400
            flash(error, 'error')
            return render_template('auth/login.html')
        
        # Find user
        user = mongo.db.users.find_one({'email': email})
        
        if user and check_password_hash(user['password'], password):
            # Update last login
            mongo.db.users.update_one(
                {'_id': user['_id']},
                {'$set': {'last_login': datetime.utcnow()}}
            )
            
            # Set session
            session.permanent = True
            session['user_id'] = str(user['_id'])
            session['user_email'] = user['email']
            session['user_name'] = user['name']
            
            if request.is_json:
                return jsonify({
                    'success': True, 
                    'redirect': url_for('main.dashboard'),
                    'user': {
                        'name': user['name'],
                        'email': user['email']
                    }
                })
            flash('Login successful!', 'success')
            return redirect(url_for('main.dashboard'))
        
        error = 'Invalid email or password'
        if request.is_json:
            return jsonify({'success': False, 'error': error}), 401
        flash(error, 'error')
        return render_template('auth/login.html')
    
    # GET request
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        
        # Get form data
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        license_number = data.get('license_number', '').strip()
        specialty = data.get('specialty', '').strip()
        phone = data.get('phone', '').strip()
        
        # Validate input
        errors = []
        
        if not name:
            errors.append('Name is required')
        if not email:
            errors.append('Email is required')
        elif not validate_email(email):
            errors.append('Invalid email format')
        if not password:
            errors.append('Password is required')
        elif password != confirm_password:
            errors.append('Passwords do not match')
        else:
            is_valid, message = validate_password(password)
            if not is_valid:
                errors.append(message)
        if not license_number:
            errors.append('License number is required')
        
        # Check if user already exists
        if not errors and mongo.db.users.find_one({'email': email}):
            errors.append('Email already registered')
        
        if not errors and mongo.db.users.find_one({'license_number': license_number}):
            errors.append('License number already registered')
        
        if errors:
            if request.is_json:
                return jsonify({'success': False, 'errors': errors}), 400
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        # Create new user
        user_data = {
            'name': name,
            'email': email,
            'password': generate_password_hash(password),
            'license_number': license_number,
            'specialty': specialty,
            'phone': phone,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True
        }
        
        try:
            result = mongo.db.users.insert_one(user_data)
            
            if request.is_json:
                return jsonify({
                    'success': True, 
                    'user_id': str(result.inserted_id),
                    'message': 'Registration successful! Please login.'
                })
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            error = 'Registration failed. Please try again.'
            if request.is_json:
                return jsonify({'success': False, 'error': error}), 500
            flash(error, 'error')
            return render_template('auth/register.html')
    
    # GET request
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('auth/register.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    
    return render_template('auth/profile.html', user=user)

@auth_bp.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    data = request.get_json() if request.is_json else request.form
    
    # Get current user
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    
    # Update fields
    update_data = {
        'updated_at': datetime.utcnow()
    }
    
    if data.get('name'):
        update_data['name'] = data.get('name').strip()
        session['user_name'] = update_data['name']
    
    if data.get('specialty'):
        update_data['specialty'] = data.get('specialty').strip()
    
    if data.get('phone'):
        update_data['phone'] = data.get('phone').strip()
    
    # Update password if provided
    if data.get('current_password') and data.get('new_password'):
        if check_password_hash(user['password'], data.get('current_password')):
            new_password = data.get('new_password')
            confirm_password = data.get('confirm_new_password')
            
            if new_password == confirm_password:
                is_valid, message = validate_password(new_password)
                if is_valid:
                    update_data['password'] = generate_password_hash(new_password)
                else:
                    if request.is_json:
                        return jsonify({'success': False, 'error': message}), 400
                    flash(message, 'error')
                    return redirect(url_for('auth.profile'))
            else:
                error = 'New passwords do not match'
                if request.is_json:
                    return jsonify({'success': False, 'error': error}), 400
                flash(error, 'error')
                return redirect(url_for('auth.profile'))
        else:
            error = 'Current password is incorrect'
            if request.is_json:
                return jsonify({'success': False, 'error': error}), 400
            flash(error, 'error')
            return redirect(url_for('auth.profile'))
    
    # Update user in database
    try:
        mongo.db.users.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': update_data}
        )
        
        if request.is_json:
            return jsonify({'success': True, 'message': 'Profile updated successfully'})
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
        
    except Exception as e:
        error = 'Failed to update profile. Please try again.'
        if request.is_json:
            return jsonify({'success': False, 'error': error}), 500
        flash(error, 'error')
        return redirect(url_for('auth.profile'))

# Password reset functionality (basic implementation)
@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip().lower()
        
        if not email or not validate_email(email):
            error = 'Please provide a valid email address'
            if request.is_json:
                return jsonify({'success': False, 'error': error}), 400
            flash(error, 'error')
            return render_template('auth/forgot_password.html')
        
        # Check if user exists
        user = mongo.db.users.find_one({'email': email})
        
        # Always show success message for security (don't reveal if email exists)
        message = 'If an account with that email exists, password reset instructions have been sent.'
        
        if user:
            # TODO: Implement actual email sending
            # For now, just log that a reset was requested
            print(f"Password reset requested for: {email}")
            # In production, you would:
            # 1. Generate a secure reset token
            # 2. Store it in database with expiration
            # 3. Send email with reset link
        
        if request.is_json:
            return jsonify({'success': True, 'message': message})
        flash(message, 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')