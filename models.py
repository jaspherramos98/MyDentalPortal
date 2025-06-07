from datetime import datetime, timedelta
from bson.objectid import ObjectId

# MongoDB Schema Definitions for Dental Portal
# These are documentation/validation schemas - MongoDB is schemaless by nature

class UserModel:
    """
    Users collection schema (Dentists/Staff)
    """
    @staticmethod
    def schema():
        return {
            "_id": ObjectId,
            "name": str,
            "email": str,  # unique
            "password": str,  # hashed
            "license_number": str,
            "specialty": str,  # Optional
            "phone": str,  # Optional
            "created_at": datetime,
            "updated_at": datetime,
            "is_active": bool,
            "last_login": datetime  # Optional
        }
    
    @staticmethod
    def create_indexes(collection):
        """Create necessary indexes for Users collection"""
        collection.create_index("email", unique=True)
        collection.create_index("license_number")

class ClinicModel:
    """
    Clinics collection schema
    """
    @staticmethod
    def schema():
        return {
            "_id": ObjectId,
            "name": str,
            "address": str,
            "phone": str,
            "email": str,  # Optional
            "owner_id": str,  # Reference to User._id
            "staff_ids": [str],  # Array of User._id references
            "operating_hours": {
                "monday": {"open": str, "close": str, "closed": bool},
                "tuesday": {"open": str, "close": str, "closed": bool},
                "wednesday": {"open": str, "close": str, "closed": bool},
                "thursday": {"open": str, "close": str, "closed": bool},
                "friday": {"open": str, "close": str, "closed": bool},
                "saturday": {"open": str, "close": str, "closed": bool},
                "sunday": {"open": str, "close": str, "closed": bool}
            },
            "created_at": datetime,
            "updated_at": datetime,
            "is_active": bool
        }
    
    @staticmethod
    def create_indexes(collection):
        """Create necessary indexes for Clinics collection"""
        collection.create_index("owner_id")
        collection.create_index([("name", 1), ("owner_id", 1)])

class PatientModel:
    """
    Patients collection schema - based on PDA form
    """
    @staticmethod
    def schema():
        return {
            "_id": ObjectId,
            "clinic_id": ObjectId,  # Reference to Clinic._id
            "personal_info": {
                "first_name": str,
                "middle_name": str,
                "last_name": str,
                "nickname": str,
                "gender": str,  # M/F
                "birthdate": str,  # YYYY-MM-DD format
                "age": int,
                "religion": str,
                "nationality": str,
                "home_address": str,
                "occupation": str,
                "dental_insurance": str
            },
            "contact_info": {
                "home_phone": str,
                "cell_phone": str,
                "office_phone": str,
                "fax": str,
                "email": str
            },
            "emergency_contact": {
                "name": str,
                "relationship": str,
                "phone": str
            },
            "guardian_info": {  # For minors
                "name": str,
                "occupation": str
            },
            "referral_info": {
                "referred_by": str,
                "consultation_reason": str
            },
            "dental_history": {
                "previous_dentist": str,
                "last_visit": str
            },
            "medical_history": {
                "physician_info": {
                    "name": str,
                    "specialty": str,
                    "office_address": str,
                    "office_number": str
                },
                "general_health": {
                    "good_health": bool,
                    "under_treatment": bool,
                    "treatment_condition": str,
                    "serious_illness": bool,
                    "illness_details": str,
                    "hospitalized": bool,
                    "hospitalization_details": str,
                    "current_medications": str,
                    "tobacco_use": bool,
                    "alcohol_drugs": bool
                },
                "allergies": {
                    "local_anesthetic": bool,
                    "penicillin": bool,
                    "sulfa_drugs": bool,
                    "aspirin": bool,
                    "latex": bool,
                    "others": str
                },
                "women_health": {
                    "pregnant": bool,
                    "nursing": bool,
                    "birth_control": bool
                },
                "vital_signs": {
                    "blood_type": str,
                    "blood_pressure": str,
                    "bleeding_time": str
                },
                "medical_conditions": {
                    "high_blood_pressure": bool,
                    "heart_disease": bool,
                    "cancer_tumors": bool,
                    "low_blood_pressure": bool,
                    "heart_murmur": bool,
                    "anemia": bool,
                    "epilepsy": bool,
                    "hepatitis_liver": bool,
                    "angina": bool,
                    "aids_hiv": bool,
                    "rheumatic_fever": bool,
                    "asthma": bool,
                    "std": bool,
                    "allergies": bool,
                    "emphysema": bool,
                    "stomach_ulcer": bool,
                    "respiratory": bool,
                    "bleeding_problems": bool,
                    "fainting_seizures": bool,
                    "hepatitis_jaundice": bool,
                    "blood_disease": bool,
                    "weight_loss": bool,
                    "tuberculosis": bool,
                    "head_injuries": bool,
                    "radiation_therapy": bool,
                    "swollen_ankles": bool,
                    "arthritis": bool,
                    "joint_replacement": bool,
                    "kidney_disease": bool,
                    "heart_surgery": bool,
                    "diabetes": bool,
                    "heart_attack": bool,
                    "chest_pain": bool,
                    "thyroid_problem": bool,
                    "stroke": bool,
                    "other": str
                }
            },
            "created_at": datetime,
            "updated_at": datetime,
            "is_active": bool
        }
    
    @staticmethod
    def create_indexes(collection):
        """Create necessary indexes for Patients collection"""
        collection.create_index("clinic_id")
        collection.create_index([("personal_info.first_name", 1), ("personal_info.last_name", 1)])
        collection.create_index("personal_info.nickname")
        collection.create_index("contact_info.cell_phone")
        collection.create_index("contact_info.email")

class DentalChartModel:
    """
    Dental Charts collection schema - based on page 3 of PDA form
    """
    @staticmethod
    def schema():
        return {
            "_id": ObjectId,
            "patient_id": ObjectId,  # Reference to Patient._id
            "chart_date": datetime,
            "intraoral_examination": {
                "name": str,
                "age": int,
                "gender": str,
                "date": str
            },
            "teeth_status": {
                # Adult teeth (1-32) and temporary teeth
                # Each tooth has status indicators
                "tooth_1": {
                    "status": str,  # Present, Decayed, Missing, etc.
                    "restorations": [str],  # Am, Co, JC, Ab, etc.
                    "conditions": [str],  # Based on legend
                    "notes": str
                },
                # ... Continue for all 32 teeth
                "tooth_32": {
                    "status": str,
                    "restorations": [str],
                    "conditions": [str],
                    "notes": str
                }
            },
            "temporary_teeth": {
                # For children - teeth 51-85
                "tooth_51": {
                    "status": str,
                    "conditions": [str],
                    "notes": str
                },
                # ... Continue for temporary teeth
            },
            "periodontal_screening": {
                "gingivitis": bool,
                "early_periodontitis": bool,
                "moderate_periodontitis": bool,
                "advanced_periodontitis": bool,
                "notes": str
            },
            "occlusion": {
                "class_molar": str,  # Class I, II, III
                "overjet": float,
                "overbite": float,
                "midline_deviation": float,
                "crossbite": bool,
                "notes": str
            },
            "appliances": {
                "orthodontic": bool,
                "stayplate": bool,
                "others": str
            },
            "tmd_assessment": {
                "clenching": bool,
                "clicking": bool,
                "trismus": bool,
                "muscle_spasm": bool,
                "notes": str
            },
            "xray_taken": {
                "periapical": {
                    "taken": bool,
                    "tooth_number": str,
                    "date": str
                },
                "panoramic": {
                    "taken": bool,
                    "date": str
                },
                "cephalometric": {
                    "taken": bool,
                    "date": str
                },
                "occlusal": {
                    "taken": bool,
                    "upper_lower": str,
                    "date": str
                },
                "others": {
                    "taken": bool,
                    "type": str,
                    "date": str
                }
            },
            "created_by": str,  # User ID of dentist
            "created_at": datetime,
            "updated_at": datetime
        }
    
    @staticmethod
    def create_indexes(collection):
        """Create necessary indexes for DentalCharts collection"""
        collection.create_index("patient_id")
        collection.create_index("chart_date")
        collection.create_index("created_by")

class TreatmentRecordModel:
    """
    Treatment Records collection schema - based on page 4 of PDA form
    """
    @staticmethod
    def schema():
        return {
            "_id": ObjectId,
            "patient_id": ObjectId,  # Reference to Patient._id
            "date": datetime,
            "tooth_numbers": [str],  # Array of tooth numbers involved
            "procedure": str,
            "dentist": str,  # Name of performing dentist
            "amount_charged": float,
            "amount_paid": float,
            "balance": float,
            "next_appointment": datetime,  # Optional
            "notes": str,
            "procedure_codes": [str],  # Optional - for insurance coding
            "treatment_category": str,  # Preventive, Restorative, Surgical, etc.
            "materials_used": [str],  # Optional
            "created_by": str,  # User ID
            "created_at": datetime,
            "updated_at": datetime
        }
    
    @staticmethod
    def create_indexes(collection):
        """Create necessary indexes for TreatmentRecords collection"""
        collection.create_index("patient_id")
        collection.create_index("date")
        collection.create_index("created_by")
        collection.create_index("procedure")

class InformedConsentModel:
    """
    Informed Consent collection schema - based on page 2 of PDA form
    """
    @staticmethod
    def schema():
        return {
            "_id": ObjectId,
            "patient_id": ObjectId,  # Reference to Patient._id
            "consent_date": datetime,
            "treatment_consent": {
                "understood": bool,
                "initial": str,
                "treatments_explained": [str]  # List of treatments explained
            },
            "drugs_medications": {
                "understood": bool,
                "initial": str,
                "allergic_reactions_explained": bool
            },
            "treatment_plan_changes": {
                "understood": bool,
                "initial": str,
                "permission_given": bool
            },
            "radiograph_consent": {
                "understood": bool,
                "initial": str,
                "necessity_explained": bool
            },
            "teeth_removal": {
                "understood": bool,
                "initial": str,
                "alternatives_explained": bool,
                "risks_explained": bool
            },
            "crowns_bridges": {
                "understood": bool,
                "initial": str,
                "sensitivity_explained": bool,
                "temporary_crown_care": bool
            },
            "endodontics": {
                "understood": bool,
                "initial": str,
                "no_guarantee": bool,
                "referral_may_be_needed": bool
            },
            "periodontal_disease": {
                "understood": bool,
                "initial": str,
                "serious_condition": bool,
                "treatment_options_explained": bool
            },
            "fillings": {
                "understood": bool,
                "initial": str,
                "care_instructions": bool,
                "sensitivity_temporary": bool
            },
            "dentures": {
                "understood": bool,
                "initial": str,
                "adjustment_period": bool,
                "return_responsibility": bool
            },
            "patient_signature": str,
            "patient_signature_date": datetime,
            "dentist_signature": str,
            "dentist_signature_date": datetime,
            "witness_signature": str,  # Optional
            "created_by": str,  # User ID
            "created_at": datetime,
            "updated_at": datetime
        }
    
    @staticmethod
    def create_indexes(collection):
        """Create necessary indexes for InformedConsents collection"""
        collection.create_index("patient_id")
        collection.create_index("consent_date")
        collection.create_index("created_by")

# Utility functions for database operations
class DatabaseUtils:
    """
    Utility functions for database operations
    """
    
    @staticmethod
    def initialize_database(mongo_db):
        """
        Initialize database with indexes and any required setup
        """
        # Create indexes for all collections
        UserModel.create_indexes(mongo_db.users)
        ClinicModel.create_indexes(mongo_db.clinics)
        PatientModel.create_indexes(mongo_db.patients)
        DentalChartModel.create_indexes(mongo_db.dental_charts)
        TreatmentRecordModel.create_indexes(mongo_db.treatment_records)
        InformedConsentModel.create_indexes(mongo_db.informed_consents)
    
    @staticmethod
    def create_default_dental_chart(patient_id):
        """
        Create a default dental chart structure for a new patient
        """
        teeth_status = {}
        
        # Adult teeth (1-32)
        for i in range(1, 33):
            teeth_status[f"tooth_{i}"] = {
                "status": "present",
                "restorations": [],
                "conditions": [],
                "notes": ""
            }
        
        # Temporary teeth (51-85) - for children
        temporary_teeth = {}
        temp_ranges = [(51, 56), (61, 66), (71, 76), (81, 86)]
        for start, end in temp_ranges:
            for i in range(start, end):
                temporary_teeth[f"tooth_{i}"] = {
                    "status": "not_present",
                    "conditions": [],
                    "notes": ""
                }
        
        return {
            "patient_id": ObjectId(patient_id),
            "chart_date": datetime.utcnow(),
            "teeth_status": teeth_status,
            "temporary_teeth": temporary_teeth,
            "periodontal_screening": {
                "gingivitis": False,
                "early_periodontitis": False,
                "moderate_periodontitis": False,
                "advanced_periodontitis": False,
                "notes": ""
            },
            "occlusion": {
                "class_molar": "",
                "overjet": 0.0,
                "overbite": 0.0,
                "midline_deviation": 0.0,
                "crossbite": False,
                "notes": ""
            },
            "appliances": {
                "orthodontic": False,
                "stayplate": False,
                "others": ""
            },
            "tmd_assessment": {
                "clenching": False,
                "clicking": False,
                "trismus": False,
                "muscle_spasm": False,
                "notes": ""
            },
            "xray_taken": {
                "periapical": {"taken": False, "tooth_number": "", "date": ""},
                "panoramic": {"taken": False, "date": ""},
                "cephalometric": {"taken": False, "date": ""},
                "occlusal": {"taken": False, "upper_lower": "", "date": ""},
                "others": {"taken": False, "type": "", "date": ""}
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    
    @staticmethod
    def get_tooth_legend():
        """
        Return the tooth condition legend from the dental chart
        """
        return {
            "conditions": {
                "✓": "Present Teeth",
                "D": "Decayed (Caries Indicated for Filling)",
                "M": "Missing due to Caries",
                "MO": "Missing due to Other Causes",
                "Im": "Impacted Tooth",
                "Sp": "Supernumerary Tooth",
                "Rf": "Root Fragment",
                "Un": "Unerupted"
            },
            "restorations": {
                "Am": "Amalgam Filling",
                "Co": "Composite Filling",
                "JC": "Jacket Crown",
                "Ab": "Abutment",
                "Att": "Attachment",
                "P": "Pontic",
                "In": "Inlay",
                "Imp": "Implant",
                "S": "Sealants",
                "Rm": "Removable Denture"
            },
            "surgery": {
                "X": "Extraction due to Caries",
                "XO": "Extraction due to Other Causes"
            }
        }
    
    @staticmethod
    def validate_patient_data(patient_data):
        """
        Validate patient data before insertion
        """
        required_fields = [
            'clinic_id',
            'personal_info.first_name',
            'personal_info.last_name',
            'personal_info.gender'
        ]
        
        errors = []
        
        for field in required_fields:
            keys = field.split('.')
            current = patient_data
            
            try:
                for key in keys:
                    current = current[key]
                if not current or current.strip() == '':
                    errors.append(f"{field} is required")
            except (KeyError, TypeError):
                errors.append(f"{field} is required")
        
        # Validate gender
        if 'personal_info' in patient_data and 'gender' in patient_data['personal_info']:
            if patient_data['personal_info']['gender'] not in ['M', 'F']:
                errors.append("Gender must be 'M' or 'F'")
        
        # Validate age if provided
        if 'personal_info' in patient_data and 'age' in patient_data['personal_info']:
            try:
                age = int(patient_data['personal_info']['age'])
                if age < 0 or age > 150:
                    errors.append("Age must be between 0 and 150")
            except (ValueError, TypeError):
                errors.append("Age must be a valid number")
        
        return errors

# Database initialization script
def init_database(app, mongo):
    """
    Initialize the database with required indexes and default data
    """
    with app.app_context():
        print("Initializing database...")
        
        # Initialize indexes
        DatabaseUtils.initialize_database(mongo.db)
        
        # Create default admin user if none exists
        if mongo.db.users.count_documents({}) == 0:
            from werkzeug.security import generate_password_hash
            
            admin_user = {
                "name": "Admin User",
                "email": "admin@dental.com",
                "password": generate_password_hash("admin123"),
                "license_number": "ADMIN001",
                "specialty": "General Dentistry",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True
            }
            
            result = mongo.db.users.insert_one(admin_user)
            print(f"Created admin user with ID: {result.inserted_id}")
            
            # Create a default clinic for admin
            default_clinic = {
                "name": "Default Dental Clinic",
                "address": "123 Main Street, City, State",
                "phone": "555-0123",
                "email": "info@dental.com",
                "owner_id": str(result.inserted_id),
                "staff_ids": [str(result.inserted_id)],
                "operating_hours": {
                    "monday": {"open": "09:00", "close": "17:00", "closed": False},
                    "tuesday": {"open": "09:00", "close": "17:00", "closed": False},
                    "wednesday": {"open": "09:00", "close": "17:00", "closed": False},
                    "thursday": {"open": "09:00", "close": "17:00", "closed": False},
                    "friday": {"open": "09:00", "close": "17:00", "closed": False},
                    "saturday": {"open": "09:00", "close": "15:00", "closed": False},
                    "sunday": {"open": "00:00", "close": "00:00", "closed": True}
                },
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True
            }
            
            clinic_result = mongo.db.clinics.insert_one(default_clinic)
            print(f"Created default clinic with ID: {clinic_result.inserted_id}")
        
        print("Database initialization complete!")

# Sample data creation functions
class SampleDataCreator:
    """
    Create sample data for testing
    """
    
    @staticmethod
    def create_sample_patient(clinic_id):
        """
        Create a sample patient with realistic data
        """
        return {
            "clinic_id": ObjectId(clinic_id),
            "personal_info": {
                "first_name": "John",
                "middle_name": "Michael",
                "last_name": "Doe",
                "nickname": "Johnny",
                "gender": "M",
                "birthdate": "1985-06-15",
                "age": 39,
                "religion": "Catholic",
                "nationality": "Filipino",
                "home_address": "456 Oak Street, Quezon City, Metro Manila",
                "occupation": "Software Engineer",
                "dental_insurance": "PhilHealth"
            },
            "contact_info": {
                "home_phone": "02-123-4567",
                "cell_phone": "0917-123-4567",
                "office_phone": "02-987-6543",
                "fax": "",
                "email": "john.doe@email.com"
            },
            "emergency_contact": {
                "name": "Jane Doe",
                "relationship": "Spouse",
                "phone": "0918-765-4321"
            },
            "guardian_info": {
                "name": "",
                "occupation": ""
            },
            "referral_info": {
                "referred_by": "Dr. Smith Family Clinic",
                "consultation_reason": "Routine cleaning and checkup"
            },
            "dental_history": {
                "previous_dentist": "Dr. Maria Santos",
                "last_visit": "2023-12-15"
            },
            "medical_history": {
                "physician_info": {
                    "name": "Dr. Robert Cruz",
                    "specialty": "Internal Medicine",
                    "office_address": "Medical Center, Manila",
                    "office_number": "02-555-0199"
                },
                "general_health": {
                    "good_health": True,
                    "under_treatment": False,
                    "treatment_condition": "",
                    "serious_illness": False,
                    "illness_details": "",
                    "hospitalized": False,
                    "hospitalization_details": "",
                    "current_medications": "None",
                    "tobacco_use": False,
                    "alcohol_drugs": False
                },
                "allergies": {
                    "local_anesthetic": False,
                    "penicillin": False,
                    "sulfa_drugs": False,
                    "aspirin": False,
                    "latex": False,
                    "others": ""
                },
                "women_health": {
                    "pregnant": False,
                    "nursing": False,
                    "birth_control": False
                },
                "vital_signs": {
                    "blood_type": "O+",
                    "blood_pressure": "120/80",
                    "bleeding_time": "Normal"
                },
                "medical_conditions": {
                    "high_blood_pressure": False,
                    "heart_disease": False,
                    "cancer_tumors": False,
                    "low_blood_pressure": False,
                    "heart_murmur": False,
                    "anemia": False,
                    "epilepsy": False,
                    "hepatitis_liver": False,
                    "angina": False,
                    "aids_hiv": False,
                    "rheumatic_fever": False,
                    "asthma": False,
                    "std": False,
                    "allergies": False,
                    "emphysema": False,
                    "stomach_ulcer": False,
                    "respiratory": False,
                    "bleeding_problems": False,
                    "fainting_seizures": False,
                    "hepatitis_jaundice": False,
                    "blood_disease": False,
                    "weight_loss": False,
                    "tuberculosis": False,
                    "head_injuries": False,
                    "radiation_therapy": False,
                    "swollen_ankles": False,
                    "arthritis": False,
                    "joint_replacement": False,
                    "kidney_disease": False,
                    "heart_surgery": False,
                    "diabetes": False,
                    "heart_attack": False,
                    "chest_pain": False,
                    "thyroid_problem": False,
                    "stroke": False,
                    "other": ""
                }
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True
        }
    
    @staticmethod
    def create_sample_treatment_record(patient_id):
        """
        Create a sample treatment record
        """
        return {
            "patient_id": ObjectId(patient_id),
            "date": datetime.utcnow(),
            "tooth_numbers": ["14", "15"],
            "procedure": "Composite filling restoration",
            "dentist": "Dr. Juan Ramos",
            "amount_charged": 2500.00,
            "amount_paid": 2500.00,
            "balance": 0.00,
            "next_appointment": datetime.utcnow() + timedelta(days=180),
            "notes": "Patient tolerated procedure well. Follow-up in 6 months.",
            "procedure_codes": ["D2391", "D2392"],
            "treatment_category": "Restorative",
            "materials_used": ["Composite resin", "Bonding agent"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }