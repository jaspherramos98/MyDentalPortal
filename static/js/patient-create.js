// patient-create.js — extracted from templates/patients/create.html (2026-09-26).
// Patient create form: validation, guardian rules, formatting, resilient submit (explicit mode).
// Enhanced form validation and age-based guardian requirements
// Enhanced Dental Patient Form Validation and Interactive Features
(function() {
    'use strict';
    
    // Configuration object for easy maintenance
    const CONFIG = {
        MINOR_AGE_LIMIT: 18,
        PHONE_PATTERN: /^\(\d{3}\) \d{3}-\d{4}$/,
        EMAIL_PATTERN: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        REQUIRED_RADIO_GROUPS: ['good_health', 'under_treatment', 'serious_illness', 'hospitalized', 'taking_medication', 'tobacco_use', 'drug_use']
    };

    // Utility functions
    const Utils = {
        calculateAge: function(birthDate) {
            const today = new Date();
            const birth = new Date(birthDate);
            let age = today.getFullYear() - birth.getFullYear();
            const monthDiff = today.getMonth() - birth.getMonth();
            
            if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
                age--;
            }
            return age;
        },

        formatPhoneNumber: function(value) {
            // Leave phone numbers exactly as entered. PH numbers vary widely
            // (mobile 09xx / +639xx, landlines with 2- or 3-digit area codes),
            // so we don't force any single format.
            return value;
        },

        showAlert: function(container, type, message, icon = '') {
            const existingAlert = container.querySelector('.dynamic-alert');
            if (existingAlert) {
                existingAlert.remove();
            }

            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type} dynamic-alert fade-in`;
            alertDiv.innerHTML = `
                ${icon ? `<i class="${icon}"></i>` : ''}
                ${message}
            `;
            container.appendChild(alertDiv);
        },

        removeAlert: function(container) {
            const alert = container.querySelector('.dynamic-alert');
            if (alert) {
                alert.classList.add('fade-out');
                setTimeout(() => alert.remove(), 300);
            }
        }
    };

    // Guardian Information Handler
    const GuardianHandler = {
        checkRequirement: function() {
            const ageInput = document.getElementById('age');
            const birthdateInput = document.getElementById('birthdate');
            const guardianSection = document.getElementById('guardian-section');
            const guardianNameInput = document.getElementById('guardian_name');
            const guardianOccupationInput = document.getElementById('guardian_occupation');
            
            if (!guardianSection || !guardianNameInput) return;
            
            let age = null;
            
            // Get age from input or calculate from birthdate
            if (ageInput && ageInput.value) {
                age = parseInt(ageInput.value);
            } else if (birthdateInput && birthdateInput.value) {
                age = Utils.calculateAge(birthdateInput.value);
            }

            this.updateGuardianSection(age, guardianSection, guardianNameInput, guardianOccupationInput);
        },

        updateGuardianSection: function(age, section, nameInput, occupationInput) {
            const title = section.querySelector('h6') || section.querySelector('.form-section-title');
            
            if (age !== null && age < CONFIG.MINOR_AGE_LIMIT) {
                // Minor - Guardian required
                section.className = 'form-section guardian-required';
                if (title) {
                    title.innerHTML = '<i class="fas fa-child text-danger"></i> Guardian Information <span class="text-danger">(Required for Minors)</span>';
                }
                
                nameInput.setAttribute('required', 'required');
                if (occupationInput) {
                    occupationInput.setAttribute('required', 'required');
                }
                
                Utils.showAlert(section, 'warning', 
                    `<strong>Minor Patient (Age ${age}):</strong> Guardian information is required for patients under ${CONFIG.MINOR_AGE_LIMIT} years old.`, 
                    'fas fa-exclamation-triangle'
                );
                
            } else if (age !== null && age >= CONFIG.MINOR_AGE_LIMIT) {
                // Adult - Guardian optional
                section.className = 'form-section guardian-optional';
                if (title) {
                    title.innerHTML = '<i class="fas fa-users text-muted"></i> Guardian Information <span class="text-muted">(Optional)</span>';
                }
                
                nameInput.removeAttribute('required');
                if (occupationInput) {
                    occupationInput.removeAttribute('required');
                }
                
                Utils.showAlert(section, 'info', 
                    `<strong>Adult Patient (Age ${age}):</strong> Guardian information is optional.`, 
                    'fas fa-info-circle'
                );
                
            } else {
                // Age unknown - neutral state
                section.className = 'form-section';
                if (title) {
                    title.innerHTML = '<i class="fas fa-child"></i> Guardian Information';
                }
                nameInput.removeAttribute('required');
                if (occupationInput) {
                    occupationInput.removeAttribute('required');
                }
                Utils.removeAlert(section);
            }
        }
    };

    // Form Validation Handler
    const ValidationHandler = {
        validateRadioGroups: function() {
            let allValid = true;
            
            CONFIG.REQUIRED_RADIO_GROUPS.forEach(groupName => {
                const radios = document.querySelectorAll(`input[name="${groupName}"]`);
                if (radios.length === 0) return; // Skip if group doesn't exist
                
                const isChecked = Array.from(radios).some(radio => radio.checked);
                const container = radios[0].closest('.form-group, .col-md-6, .row');
                
                if (!isChecked) {
                    this.addRadioError(container);
                    allValid = false;
                } else {
                    this.removeRadioError(container);
                }
            });
            
            return allValid;
        },

        addRadioError: function(container) {
            if (container) {
                container.classList.add('radio-group-error');
                container.style.border = '2px solid #dc3545';
                container.style.borderRadius = '8px';
                container.style.padding = '10px';
                container.style.backgroundColor = '#ffeaa7';
                container.style.transition = 'all 0.3s ease';
            }
        },

        removeRadioError: function(container) {
            if (container) {
                container.classList.remove('radio-group-error');
                container.style.border = '';
                container.style.borderRadius = '';
                container.style.padding = '';
                container.style.backgroundColor = '';
            }
        },

        validateSpecialFields: function() {
            let isValid = true;
            const errors = [];

            // Validate email if provided
            const emailInput = document.getElementById('email');
            if (emailInput && emailInput.value && !CONFIG.EMAIL_PATTERN.test(emailInput.value)) {
                emailInput.classList.add('is-invalid');
                errors.push('Please enter a valid email address.');
                isValid = false;
            } else if (emailInput) {
                emailInput.classList.remove('is-invalid');
            }

            // Validate phone numbers if provided
            const phoneInputs = document.querySelectorAll('input[type="tel"]');
            phoneInputs.forEach(input => {
                if (input.value && input.value.length > 0) {
                    const cleaned = input.value.replace(/\D/g, '');
                    if (cleaned.length < 7) {
                        input.classList.add('is-invalid');
                        errors.push('Phone numbers must have at least 7 digits.');
                        isValid = false;
                    } else {
                        input.classList.remove('is-invalid');
                    }
                }
            });

            // Require at least one contact method (home/cell/office phone or email)
            const contactIds = ['home_phone', 'cell_phone', 'office_phone', 'email'];
            const hasContact = contactIds.some(id => {
                const el = document.getElementById(id);
                return el && el.value.trim().length > 0;
            });
            if (!hasContact) {
                contactIds.forEach(id => document.getElementById(id)?.classList.add('is-invalid'));
                errors.push('Please provide at least one contact method (home, cell, or office phone, or email).');
                isValid = false;
            } else {
                contactIds.forEach(id => document.getElementById(id)?.classList.remove('is-invalid'));
            }

            // Check minor guardian requirement
            const age = parseInt(document.getElementById('age')?.value || 0);
            const guardianName = document.getElementById('guardian_name')?.value?.trim();
            
            if (age > 0 && age < CONFIG.MINOR_AGE_LIMIT && !guardianName) {
                errors.push(`Guardian information is required for patients under ${CONFIG.MINOR_AGE_LIMIT} years old.`);
                document.getElementById('guardian_name')?.focus();
                isValid = false;
            }

            if (errors.length > 0) {
                this.showValidationErrors(errors);
            }

            return isValid;
        },

        showValidationErrors: function(errors) {
            const errorContainer = document.getElementById('validation-errors') || this.createErrorContainer();
            errorContainer.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <h6><i class="fas fa-exclamation-triangle"></i> Please correct the following errors:</h6>
                    <ul class="mb-0">
                        ${errors.map(error => `<li>${error}</li>`).join('')}
                    </ul>
                </div>
            `;
            errorContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
        },

        createErrorContainer: function() {
            const container = document.createElement('div');
            container.id = 'validation-errors';
            container.className = 'mb-3';
            const form = document.querySelector('form');
            form.insertBefore(container, form.firstChild);
            return container;
        }
    };

    // Gender-based Section Handler
    const GenderHandler = {
        toggleWomenSection: function(gender) {
            const section = document.getElementById('womenOnlySection');
            if (!section) return;
            if (gender === 'F' || gender === 'female') {
                section.style.display = 'block';
                section.classList.add('fade-in');
            } else {
                section.style.display = 'none';
                // Clear women's health fields when not applicable
                section.querySelectorAll('input[type="radio"], input[type="checkbox"]')
                    .forEach(input => { input.checked = false; });
            }
        }
    };

    // Event Listeners Setup
    const EventListeners = {
        init: function() {
            this.setupFormValidation();
            this.setupAgeCalculation();
            this.setupPhoneFormatting();
            this.setupGenderHandling();
            this.setupRadioValidation();
            this.setupGuardianChecks();
        },

        setupFormValidation: function() {
            const forms = document.getElementsByClassName('needs-validation');
            Array.from(forms).forEach(form => {
                // Attach up front so keepalive + the unsaved-changes guard run
                // while the form is being filled, not just at submit.
                const resilient = ResilientSubmit.attach(form);
                form.addEventListener('submit', function(event) {
                    let formValid = true;
                    
                    // Custom validations
                    if (!ValidationHandler.validateRadioGroups()) formValid = false;
                    if (!ValidationHandler.validateSpecialFields()) formValid = false;
                    
                    // Standard HTML5 validation
                    if (!form.checkValidity() || !formValid) {
                        event.preventDefault();
                        event.stopPropagation();
                        form.classList.add('was-validated');
                        // Critical on long/mobile forms: make the block obvious by
                        // jumping to and focusing the first invalid field, plus a
                        // visible message (otherwise the submit silently does nothing).
                        const firstInvalid = form.querySelector(':invalid, .is-invalid');
                        if (firstInvalid) {
                            firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            try { firstInvalid.focus({ preventScroll: true }); } catch (e) {}
                        }
                        const ec = document.getElementById('validation-errors')
                                   || ValidationHandler.createErrorContainer();
                        if (ec) {
                            ec.innerHTML = '<div class="alert alert-danger mb-3">'
                                + '<i class="fas fa-exclamation-triangle"></i> '
                                + 'Please complete the required fields highlighted in red, then Save again.'
                                + '</div>';
                        }
                        return;
                    }
                    // Valid — clear any prior error message.
                    const errorContainer = document.getElementById('validation-errors');
                    if (errorContainer) errorContainer.innerHTML = '';
                    form.classList.add('was-validated');

                    // Send it ourselves so a dropped connection or expired
                    // session never loses the typed form (resilient-submit.js).
                    // Falls through to the native submit on very old browsers.
                    if (resilient) {
                        event.preventDefault();
                        resilient.submit();
                    }
                }, false);
            });
        },

        setupAgeCalculation: function() {
            const birthdateInput = document.getElementById('birthdate');
            const ageInput = document.getElementById('age');
            
            if (birthdateInput) {
                birthdateInput.addEventListener('change', function() {
                    const age = Utils.calculateAge(this.value);
                    if (age >= 0 && age <= 150 && ageInput) {
                        ageInput.value = age;
                        GuardianHandler.checkRequirement();
                    }
                });
            }
            
            if (ageInput) {
                ageInput.addEventListener('input', function() {
                    GuardianHandler.checkRequirement();
                });
            }
        },

        setupPhoneFormatting: function() {
            const phoneInputs = document.querySelectorAll('input[type="tel"]');
            phoneInputs.forEach(input => {
                input.addEventListener('input', function() {
                    this.value = Utils.formatPhoneNumber(this.value);
                });
                
                input.addEventListener('blur', function() {
                    if (this.value) {
                        this.value = Utils.formatPhoneNumber(this.value);
                    }
                });
            });
        },

        setupGenderHandling: function() {
            const genderInput = document.getElementById('gender');
            if (genderInput) {
                genderInput.addEventListener('change', function() {
                    GenderHandler.toggleWomenSection(this.value);
                });
                
                // Initial check
                if (genderInput.value) {
                    GenderHandler.toggleWomenSection(genderInput.value);
                }
            }
        },

        setupRadioValidation: function() {
            document.querySelectorAll('input[type="radio"]').forEach(radio => {
                radio.addEventListener('change', function() {
                    const container = this.closest('.form-group, .col-md-6, .row');
                    ValidationHandler.removeRadioError(container);
                });
            });
        },

        setupGuardianChecks: function() {
            // Initial check on page load
            setTimeout(() => {
                GuardianHandler.checkRequirement();
            }, 100);
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            EventListeners.init();
        });
    } else {
        EventListeners.init();
    }

    // Expose public methods for external use
    window.DentalFormValidator = {
        validateForm: () => ValidationHandler.validateSpecialFields() && ValidationHandler.validateRadioGroups(),
        checkGuardianRequirement: () => GuardianHandler.checkRequirement(),
        formatPhone: Utils.formatPhoneNumber
    };

})();
