/**
 * Appointments API JavaScript Module
 * Handles all appointment-related API calls and calendar functionality
 */

class AppointmentsAPI {
    constructor() {
        this.baseURL = '/appointments/api';
        this.fallbackURL = '/api/appointments';
        this.currentView = 'month';
        this.currentDate = new Date();
        this.selectedClinic = null;
        this.appointments = [];
        
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadAppointments();
        this.renderCalendar();
    }

    setupEventListeners() {
        // Calendar navigation
        document.getElementById('prevBtn')?.addEventListener('click', () => this.navigateCalendar(-1));
        document.getElementById('nextBtn')?.addEventListener('click', () => this.navigateCalendar(1));
        document.getElementById('todayBtn')?.addEventListener('click', () => this.goToToday());
        
        // View switching
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchView(e.target.dataset.view));
        });
        
        // Clinic selection
        document.getElementById('clinicSelect')?.addEventListener('change', (e) => {
            this.selectedClinic = e.target.value;
            this.loadAppointments();
        });
        
        // New appointment button
        document.getElementById('newAppointmentBtn')?.addEventListener('click', () => this.showNewAppointmentModal());
        
        // Time slot clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('time-slot')) {
                this.handleTimeSlotClick(e.target);
            }
        });
        
        // Modal handlers
        this.setupModalHandlers();
    }

    setupModalHandlers() {
        // New appointment modal
        const newAppointmentModal = document.getElementById('newAppointmentModal');
        const newAppointmentForm = document.getElementById('newAppointmentForm');
        
        if (newAppointmentForm) {
            newAppointmentForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.createAppointment();
            });
        }
        
        // Close modal buttons
        document.querySelectorAll('.modal .close, .modal .btn-cancel').forEach(btn => {
            btn.addEventListener('click', () => this.closeModals());
        });
        
        // Click outside modal to close
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.closeModals();
                }
            });
        });
        
        // Escape key to close modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModals();
            }
        });
    }

    async loadAppointments() {
        try {
            const startDate = this.getViewStartDate();
            const endDate = this.getViewEndDate();
            
            const params = new URLSearchParams({
                start_date: startDate.toISOString().split('T')[0],
                end_date: endDate.toISOString().split('T')[0]
            });
            
            if (this.selectedClinic) {
                params.append('clinic_id', this.selectedClinic);
            }
            
            // Try blueprint endpoint first, then fallback
            let response;
            try {
                response = await fetch(`${this.baseURL}?${params}`);
            } catch (error) {
                console.log('Blueprint endpoint failed, trying fallback...');
                response = await fetch(`${this.fallbackURL}?${params}`);
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.appointments = data.appointments || [];
                this.renderCalendar();
                this.updateAppointmentsList();
            } else {
                throw new Error(data.error || 'Failed to load appointments');
            }
            
        } catch (error) {
            console.error('Error loading appointments:', error);
            this.showError('Failed to load appointments: ' + error.message);
        }
    }

    async createAppointment() {
        try {
            const form = document.getElementById('newAppointmentForm');
            const formData = new FormData(form);
            
            const appointmentData = {
                patient_name: formData.get('patient_name'),
                date: formData.get('date'),
                time: formData.get('time'),
                duration: parseInt(formData.get('duration')) || 30,
                type: formData.get('type') || 'checkup',
                priority: formData.get('priority') || 'normal',
                notes: formData.get('notes') || '',
                clinic_id: formData.get('clinic_id') || this.selectedClinic,
                patient_id: formData.get('patient_id') || null
            };
            
            // Validate required fields
            if (!appointmentData.patient_name || !appointmentData.date || !appointmentData.time) {
                this.showError('Please fill in all required fields');
                return;
            }
            
            // Try blueprint endpoint first, then fallback
            let response;
            try {
                response = await fetch(this.baseURL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(appointmentData)
                });
            } catch (error) {
                console.log('Blueprint endpoint failed, trying fallback...');
                response = await fetch(this.fallbackURL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(appointmentData)
                });
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess(data.message || 'Appointment created successfully');
                this.closeModals();
                this.loadAppointments(); // Reload appointments
                form.reset(); // Reset form
            } else {
                throw new Error(data.error || 'Failed to create appointment');
            }
            
        } catch (error) {
            console.error('Error creating appointment:', error);
            this.showError('Failed to create appointment: ' + error.message);
        }
    }

    async updateAppointment(appointmentId, updateData) {
        try {
            // Try blueprint endpoint first, then fallback
            let response;
            try {
                response = await fetch(`${this.baseURL}/${appointmentId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(updateData)
                });
            } catch (error) {
                console.log('Blueprint endpoint failed, trying fallback...');
                response = await fetch(`${this.fallbackURL}/${appointmentId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(updateData)
                });
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess(data.message || 'Appointment updated successfully');
                this.loadAppointments(); // Reload appointments
            } else {
                throw new Error(data.error || 'Failed to update appointment');
            }
            
        } catch (error) {
            console.error('Error updating appointment:', error);
            this.showError('Failed to update appointment: ' + error.message);
        }
    }

    async deleteAppointment(appointmentId) {
        if (!confirm('Are you sure you want to delete this appointment?')) {
            return;
        }
        
        try {
            // Try blueprint endpoint first, then fallback
            let response;
            try {
                response = await fetch(`${this.baseURL}/${appointmentId}`, {
                    method: 'DELETE'
                });
            } catch (error) {
                console.log('Blueprint endpoint failed, trying fallback...');
                response = await fetch(`${this.fallbackURL}/${appointmentId}`, {
                    method: 'DELETE'
                });
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess(data.message || 'Appointment deleted successfully');
                this.loadAppointments(); // Reload appointments
            } else {
                throw new Error(data.error || 'Failed to delete appointment');
            }
            
        } catch (error) {
            console.error('Error deleting appointment:', error);
            this.showError('Failed to delete appointment: ' + error.message);
        }
    }

    renderCalendar() {
        const calendarGrid = document.getElementById('calendarGrid');
        if (!calendarGrid) return;
        
        calendarGrid.innerHTML = '';
        
        switch (this.currentView) {
            case 'day':
                this.renderDayView(calendarGrid);
                break;
            case 'week':
                this.renderWeekView(calendarGrid);
                break;
            case 'month':
            default:
                this.renderMonthView(calendarGrid);
                break;
        }
        
        this.updateCalendarHeader();
    }

    renderMonthView(container) {
        const startDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), 1);
        const endDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() + 1, 0);
        
        // Get first day of week (Sunday = 0)
        const firstDay = startDate.getDay();
        
        // Create calendar grid
        const calendar = document.createElement('div');
        calendar.className = 'calendar-month';
        
        // Add day headers
        const daysOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        daysOfWeek.forEach(day => {
            const dayHeader = document.createElement('div');
            dayHeader.className = 'calendar-day-header';
            dayHeader.textContent = day;
            calendar.appendChild(dayHeader);
        });
        
        // Add empty cells for days before month starts
        for (let i = 0; i < firstDay; i++) {
            const emptyDay = document.createElement('div');
            emptyDay.className = 'calendar-day empty';
            calendar.appendChild(emptyDay);
        }
        
        // Add days of the month
        for (let day = 1; day <= endDate.getDate(); day++) {
            const dayElement = document.createElement('div');
            dayElement.className = 'calendar-day';
            
            const currentDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), day);
            const dateStr = currentDate.toISOString().split('T')[0];
            
            // Check if it's today
            const today = new Date();
            if (currentDate.toDateString() === today.toDateString()) {
                dayElement.classList.add('today');
            }
            
            dayElement.innerHTML = `
                <div class="day-number">${day}</div>
                <div class="day-appointments" id="day-${dateStr}"></div>
            `;
            
            // Add click handler for creating appointments
            dayElement.addEventListener('click', () => {
                this.showNewAppointmentModal(dateStr);
            });
            
            calendar.appendChild(dayElement);
            
            // Add appointments for this day
            this.renderDayAppointments(dateStr);
        }
        
        container.appendChild(calendar);
    }

    renderWeekView(container) {
        const startOfWeek = this.getStartOfWeek(this.currentDate);
        const calendar = document.createElement('div');
        calendar.className = 'calendar-week';
        
        // Time column
        const timeColumn = document.createElement('div');
        timeColumn.className = 'time-column';
        
        // Add time slots
        for (let hour = 8; hour < 18; hour++) {
            const timeSlot = document.createElement('div');
            timeSlot.className = 'time-slot-label';
            timeSlot.textContent = this.formatTime(hour, 0);
            timeColumn.appendChild(timeSlot);
        }
        
        calendar.appendChild(timeColumn);
        
        // Day columns
        for (let i = 0; i < 7; i++) {
            const currentDate = new Date(startOfWeek);
            currentDate.setDate(startOfWeek.getDate() + i);
            const dateStr = currentDate.toISOString().split('T')[0];
            
            const dayColumn = document.createElement('div');
            dayColumn.className = 'day-column';
            
            // Day header
            const dayHeader = document.createElement('div');
            dayHeader.className = 'day-header';
            dayHeader.innerHTML = `
                <div class="day-name">${currentDate.toLocaleDateString('en-US', { weekday: 'short' })}</div>
                <div class="day-number">${currentDate.getDate()}</div>
            `;
            dayColumn.appendChild(dayHeader);
            
            // Time slots for this day
            for (let hour = 8; hour < 18; hour++) {
                const timeSlot = document.createElement('div');
                timeSlot.className = 'time-slot';
                timeSlot.dataset.date = dateStr;
                timeSlot.dataset.time = this.formatTime(hour, 0);
                dayColumn.appendChild(timeSlot);
            }
            
            calendar.appendChild(dayColumn);
            
            // Add appointments for this day
            this.renderDayAppointments(dateStr);
        }
        
        container.appendChild(calendar);
    }

    renderDayView(container) {
        const dateStr = this.currentDate.toISOString().split('T')[0];
        
        const calendar = document.createElement('div');
        calendar.className = 'calendar-day-view';
        
        // Day header
        const dayHeader = document.createElement('div');
        dayHeader.className = 'day-view-header';
        dayHeader.innerHTML = `
            <h3>${this.currentDate.toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
            })}</h3>
        `;
        calendar.appendChild(dayHeader);
        
        // Time slots
        const timeSlotsContainer = document.createElement('div');
        timeSlotsContainer.className = 'time-slots-container';
        
        for (let hour = 8; hour < 18; hour++) {
            for (let minute = 0; minute < 60; minute += 30) {
                const timeSlot = document.createElement('div');
                timeSlot.className = 'time-slot detailed';
                timeSlot.dataset.date = dateStr;
                timeSlot.dataset.time = this.formatTime(hour, minute);
                
                timeSlot.innerHTML = `
                    <div class="time-label">${this.formatTime(hour, minute)}</div>
                    <div class="appointment-slot" id="slot-${dateStr}-${hour}-${minute}"></div>
                `;
                
                timeSlotsContainer.appendChild(timeSlot);
            }
        }
        
        calendar.appendChild(timeSlotsContainer);
        container.appendChild(calendar);
        
        // Add appointments for this day
        this.renderDayAppointments(dateStr);
    }

    renderDayAppointments(dateStr) {
        const dayAppointments = this.appointments.filter(apt => apt.date === dateStr);
        
        dayAppointments.forEach(appointment => {
            const appointmentElement = this.createAppointmentElement(appointment);
            
            // Find the appropriate container based on current view
            let container;
            if (this.currentView === 'month') {
                container = document.getElementById(`day-${dateStr}`);
            } else if (this.currentView === 'week') {
                const timeSlot = document.querySelector(
                    `.time-slot[data-date="${dateStr}"][data-time="${appointment.time}"]`
                );
                container = timeSlot;
            } else if (this.currentView === 'day') {
                const [hours, minutes] = appointment.time.split(':');
                container = document.getElementById(`slot-${dateStr}-${hours}-${minutes}`);
            }
            
            if (container) {
                container.appendChild(appointmentElement);
            }
        });
    }

    createAppointmentElement(appointment) {
        const element = document.createElement('div');
        element.className = `appointment appointment-${appointment.priority || 'normal'}`;
        element.dataset.appointmentId = appointment._id;
        
        element.innerHTML = `
            <div class="appointment-time">${appointment.time}</div>
            <div class="appointment-patient">${appointment.patient_name}</div>
            <div class="appointment-type">${appointment.type || 'Checkup'}</div>
            <div class="appointment-actions">
                <button class="btn-edit" onclick="appointmentsAPI.editAppointment('${appointment._id}')">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-delete" onclick="appointmentsAPI.deleteAppointment('${appointment._id}')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        // Add click handler for viewing details
        element.addEventListener('click', (e) => {
            if (!e.target.closest('.appointment-actions')) {
                this.showAppointmentDetails(appointment);
            }
        });
        
        return element;
    }

    updateAppointmentsList() {
        const appointmentsList = document.getElementById('appointmentsList');
        if (!appointmentsList) return;
        
        appointmentsList.innerHTML = '';
        
        if (this.appointments.length === 0) {
            appointmentsList.innerHTML = '<div class="no-appointments">No appointments found</div>';
            return;
        }
        
        // Sort appointments by date and time
        const sortedAppointments = [...this.appointments].sort((a, b) => {
            const dateCompare = a.date.localeCompare(b.date);
            if (dateCompare !== 0) return dateCompare;
            return a.time.localeCompare(b.time);
        });
        
        sortedAppointments.forEach(appointment => {
            const listItem = document.createElement('div');
            listItem.className = 'appointment-list-item';
            listItem.innerHTML = `
                <div class="appointment-info">
                    <div class="patient-name">${appointment.patient_name}</div>
                    <div class="appointment-datetime">
                        ${new Date(appointment.date).toLocaleDateString()} at ${appointment.time}
                    </div>
                    <div class="appointment-type">${appointment.type || 'Checkup'}</div>
                </div>
                <div class="appointment-status status-${appointment.status || 'scheduled'}">
                    ${appointment.status || 'Scheduled'}
                </div>
            `;
            
            listItem.addEventListener('click', () => {
                this.showAppointmentDetails(appointment);
            });
            
            appointmentsList.appendChild(listItem);
        });
    }

    // Utility methods
    navigateCalendar(direction) {
        switch (this.currentView) {
            case 'day':
                this.currentDate.setDate(this.currentDate.getDate() + direction);
                break;
            case 'week':
                this.currentDate.setDate(this.currentDate.getDate() + (direction * 7));
                break;
            case 'month':
                this.currentDate.setMonth(this.currentDate.getMonth() + direction);
                break;
        }
        this.renderCalendar();
        this.loadAppointments();
    }

    goToToday() {
        this.currentDate = new Date();
        this.renderCalendar();
        this.loadAppointments();
    }

    switchView(view) {
        this.currentView = view;
        
        // Update active button
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`.view-btn[data-view="${view}"]`)?.classList.add('active');
        
        this.renderCalendar();
    }

    updateCalendarHeader() {
        const headerElement = document.getElementById('currentPeriod');
        if (!headerElement) return;
        
        let headerText = '';
        switch (this.currentView) {
            case 'day':
                headerText = this.currentDate.toLocaleDateString('en-US', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                });
                break;
            case 'week':
                const startOfWeek = this.getStartOfWeek(this.currentDate);
                const endOfWeek = new Date(startOfWeek);
                endOfWeek.setDate(startOfWeek.getDate() + 6);
                headerText = `${startOfWeek.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${endOfWeek.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
                break;
            case 'month':
                headerText = this.currentDate.toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'long'
                });
                break;
        }
        
        headerElement.textContent = headerText;
    }

    getStartOfWeek(date) {
        const start = new Date(date);
        const day = start.getDay();
        const diff = start.getDate() - day;
        return new Date(start.setDate(diff));
    }

    getViewStartDate() {
        switch (this.currentView) {
            case 'day':
                return new Date(this.currentDate);
            case 'week':
                return this.getStartOfWeek(this.currentDate);
            case 'month':
                const start = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), 1);
                return this.getStartOfWeek(start);
            default:
                return new Date(this.currentDate);
        }
    }

    getViewEndDate() {
        switch (this.currentView) {
            case 'day':
                return new Date(this.currentDate);
            case 'week':
                const weekEnd = this.getStartOfWeek(this.currentDate);
                weekEnd.setDate(weekEnd.getDate() + 6);
                return weekEnd;
            case 'month':
                const monthEnd = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() + 1, 0);
                const weekEndOfMonth = new Date(monthEnd);
                weekEndOfMonth.setDate(monthEnd.getDate() + (6 - monthEnd.getDay()));
                return weekEndOfMonth;
            default:
                return new Date(this.currentDate);
        }
    }

    formatTime(hours, minutes) {
        const period = hours >= 12 ? 'PM' : 'AM';
        const displayHours = hours > 12 ? hours - 12 : (hours === 0 ? 12 : hours);
        return `${displayHours}:${minutes.toString().padStart(2, '0')} ${period}`;
    }

    // Modal methods
    showNewAppointmentModal(selectedDate = null) {
        const modal = document.getElementById('newAppointmentModal');
        if (!modal) return;
        
        // Pre-fill date if provided
        if (selectedDate) {
            const dateInput = document.getElementById('appointmentDate');
            if (dateInput) {
                dateInput.value = selectedDate;
            }
        }
        
        modal.style.display = 'block';
        document.body.classList.add('modal-open');
    }

    showAppointmentDetails(appointment) {
        // Create and show appointment details modal
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Appointment Details</h2>
                    <span class="close">&times;</span>
                </div>
                <div class="modal-body">
                    <div class="appointment-details">
                        <p><strong>Patient:</strong> ${appointment.patient_name}</p>
                        <p><strong>Date:</strong> ${new Date(appointment.date).toLocaleDateString()}</p>
                        <p><strong>Time:</strong> ${appointment.time}</p>
                        <p><strong>Duration:</strong> ${appointment.duration || 30} minutes</p>
                        <p><strong>Type:</strong> ${appointment.type || 'Checkup'}</p>
                        <p><strong>Priority:</strong> ${appointment.priority || 'Normal'}</p>
                        <p><strong>Status:</strong> ${appointment.status || 'Scheduled'}</p>
                        ${appointment.notes ? `<p><strong>Notes:</strong> ${appointment.notes}</p>` : ''}
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="appointmentsAPI.editAppointment('${appointment._id}')">Edit</button>
                    <button class="btn btn-danger" onclick="appointmentsAPI.deleteAppointment('${appointment._id}')">Delete</button>
                    <button class="btn btn-secondary" onclick="appointmentsAPI.closeModals()">Close</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        modal.style.display = 'block';
        document.body.classList.add('modal-open');
        
        // Add close handlers
        modal.querySelector('.close').addEventListener('click', () => this.closeModals());
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeModals();
            }
        });
    }

    editAppointment(appointmentId) {
        const appointment = this.appointments.find(apt => apt._id === appointmentId);
        if (!appointment) return;
        
        // Populate edit form with appointment data
        const modal = document.getElementById('newAppointmentModal');
        if (!modal) return;
        
        const form = document.getElementById('newAppointmentForm');
        if (!form) return;
        
        // Fill form fields
        form.querySelector('[name="patient_name"]').value = appointment.patient_name;
        form.querySelector('[name="date"]').value = appointment.date;
        form.querySelector('[name="time"]').value = appointment.time;
        form.querySelector('[name="duration"]').value = appointment.duration || 30;
        form.querySelector('[name="type"]').value = appointment.type || 'checkup';
        form.querySelector('[name="priority"]').value = appointment.priority || 'normal';
        form.querySelector('[name="notes"]').value = appointment.notes || '';
        
        if (appointment.patient_id) {
            form.querySelector('[name="patient_id"]').value = appointment.patient_id;
        }
        
        // Change form submission to update instead of create
        form.setAttribute('data-appointment-id', appointmentId);
        
        this.closeModals();
        this.showNewAppointmentModal();
    }

    handleTimeSlotClick(timeSlot) {
        const date = timeSlot.dataset.date;
        const time = timeSlot.dataset.time;
        
        if (date && time) {
            this.showNewAppointmentModal(date);
            
            // Pre-fill time if available
            const timeInput = document.getElementById('appointmentTime');
            if (timeInput) {
                timeInput.value = time;
            }
        }
    }

    closeModals() {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.style.display = 'none';
            if (modal.id !== 'newAppointmentModal') {
                modal.remove();
            }
        });
        document.body.classList.remove('modal-open');
        
        // Reset form
        const form = document.getElementById('newAppointmentForm');
        if (form) {
            form.reset();
            form.removeAttribute('data-appointment-id');
        }
    }

    // Notification methods
    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showError(message) {
        this.showNotification(message, 'error');
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-message">${message}</span>
                <button class="notification-close">&times;</button>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            notification.remove();
        }, 5000);
        
        // Manual close
        notification.querySelector('.notification-close').addEventListener('click', () => {
            notification.remove();
        });
        
        // Show notification
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
    }
}

// Initialize when DOM is loaded
let appointmentsAPI;
document.addEventListener('DOMContentLoaded', () => {
    appointmentsAPI = new AppointmentsAPI();
});

// Export for global access
window.appointmentsAPI = appointmentsAPI;