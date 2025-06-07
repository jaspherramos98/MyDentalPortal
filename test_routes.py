#!/usr/bin/env python3
"""
Test script to verify routes are working correctly
Run this with: python test_routes.py
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test if all modules can be imported"""
    print("Testing imports...")
    
    try:
        # Test main app import
        from app import app
        print("✓ Main app imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import main app: {e}")
        return False
    
    # Test blueprint imports
    blueprints_to_test = [
        ('app.routes.appointments', 'appointments_bp'),
        ('app.routes.auth', 'auth_bp'),
        ('app.routes.clinics', 'clinics_bp'),
        ('app.routes.patients', 'patients_bp'),
        ('app.routes.treatments', 'treatments_bp'),
        ('app.routes.charts', 'charts_bp'),
        ('app.routes.main', 'main_bp')
    ]
    
    for module_path, blueprint_name in blueprints_to_test:
        try:
            module = __import__(module_path, fromlist=[blueprint_name])
            blueprint = getattr(module, blueprint_name)
            print(f"✓ {blueprint_name} imported successfully")
        except ImportError as e:
            print(f"✗ Failed to import {blueprint_name}: {e}")
        except AttributeError as e:
            print(f"✗ Blueprint {blueprint_name} not found in module: {e}")
    
    return True

def test_routes():
    """Test if routes are registered correctly"""
    print("\nTesting route registration...")
    
    try:
        from app import app
        
        with app.app_context():
            # Get all registered routes
            routes = []
            for rule in app.url_map.iter_rules():
                routes.append({
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods),
                    'path': str(rule)
                })
            
            print(f"Total routes registered: {len(routes)}")
            
            # Look for appointment routes
            appointment_routes = [r for r in routes if 'appointment' in r['endpoint'].lower()]
            print(f"Appointment routes found: {len(appointment_routes)}")
            
            for route in appointment_routes:
                print(f"  - {route['endpoint']}: {route['path']} [{', '.join(route['methods'])}]")
            
            # Check for fallback routes
            fallback_routes = [r for r in routes if 'fallback' in r['endpoint']]
            print(f"Fallback routes found: {len(fallback_routes)}")
            
            for route in fallback_routes:
                print(f"  - {route['endpoint']}: {route['path']} [{', '.join(route['methods'])}]")
            
            return True
            
    except Exception as e:
        print(f"✗ Error testing routes: {e}")
        return False

def test_database_connection():
    """Test database connection"""
    print("\nTesting database connection...")
    
    try:
        from app import app, mongo
        
        with app.app_context():
            # Test database connection
            mongo.db.command('ping')
            print("✓ Database connection successful")
            
            # Check collections
            collections = mongo.db.list_collection_names()
            print(f"Available collections: {', '.join(collections)}")
            
            return True
            
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def create_missing_files():
    """Create missing __init__.py files if needed"""
    print("\nChecking for missing __init__.py files...")
    
    required_dirs = [
        'app',
        'app/routes',
        'app/models',
        'app/utils'
    ]
    
    for dir_path in required_dirs:
        init_file = os.path.join(dir_path, '__init__.py')
        if not os.path.exists(init_file):
            print(f"Creating missing {init_file}")
            try:
                os.makedirs(dir_path, exist_ok=True)
                with open(init_file, 'w') as f:
                    f.write(f"# {dir_path} package\n")
                print(f"✓ Created {init_file}")
            except Exception as e:
                print(f"✗ Failed to create {init_file}: {e}")
        else:
            print(f"✓ {init_file} exists")

def main():
    """Main test function"""
    print("=== Dental Portal Route Testing ===\n")
    
    # Create missing files first
    create_missing_files()
    
    # Run tests
    tests = [
        test_imports,
        test_routes,
        test_database_connection
    ]
    
    for test_func in tests:
        try:
            success = test_func()
            if not success:
                print(f"\n⚠️  Test {test_func.__name__} failed")
        except Exception as e:
            print(f"\n⚠️  Test {test_func.__name__} crashed: {e}")
    
    print("\n=== Test Summary ===")
    print("If you see appointment routes listed above, your routing should work.")
    print("If not, make sure:")
    print("1. All __init__.py files exist in app/ and app/routes/")
    print("2. Your blueprint files define the blueprint variables correctly")
    print("3. MongoDB is running and accessible")
    print("\nTo test the web interface:")
    print("1. Run: python app.py")
    print("2. Go to: http://localhost:5000")
    print("3. Login with: admin@dental.com / admin123")
    print("4. Try navigating to appointments")

if __name__ == '__main__':
    main()