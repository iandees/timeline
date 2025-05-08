from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, jsonify, request, flash
from flask_login import login_required, current_user, logout_user, login_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .model import Event, User, Location

# Create blueprint
main_bp = Blueprint('main', __name__)

# Home route
@main_bp.route('/')
def index():
    return render_template('index.html')

# User authentication routes
@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form

        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password', 'danger')
            return render_template('login.html')

        login_user(user, remember=remember)
        flash('Logged in successfully!', 'success')

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('main.timeline'))

    return render_template('login.html')


@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Form validation
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')

        # Check if username or email already exists
        username_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()

        if username_exists:
            flash('Username already taken', 'danger')
            return render_template('register.html')

        if email_exists:
            flash('Email already registered', 'danger')
            return render_template('register.html')

        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )

        # Add to database
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('main.login'))

    return render_template('register.html')

@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

# Timeline routes
@main_bp.route('/timeline')
@login_required
def timeline():
    # Get date from query parameter or use today's date
    date_str = request.args.get('date')

    try:
        if date_str:
            # Parse the date string from the URL parameter
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            # Default to today's date
            current_date = datetime.now().date()
    except ValueError:
        # Handle invalid date format
        current_date = datetime.now().date()

    # Calculate yesterday and tomorrow for navigation
    yesterday = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow = (current_date + timedelta(days=1)).strftime('%Y-%m-%d')

    # Format the current date for display
    current_date_formatted = current_date.strftime('%A, %B %d, %Y')

    # Get events for the selected date
    start_of_day = datetime.combine(current_date, datetime.min.time())
    end_of_day = datetime.combine(current_date, datetime.max.time())

    events = Event.query.filter_by(user_id=current_user.id) \
        .filter(Event.start_time >= start_of_day) \
        .filter(Event.start_time <= end_of_day) \
        .order_by(Event.start_time).all()

    return render_template('timeline.html',
                           events=events,
                           yesterday=yesterday,
                           tomorrow=tomorrow,
                           current_date=current_date.strftime('%Y-%m-%d'),
                           current_date_formatted=current_date_formatted)


@main_bp.route('/add_event', methods=['GET', 'POST'])
@login_required
def add_event():
    # Format today's date for the form
    today_date = datetime.now().strftime('%Y-%m-%d')

    # Get user's locations for the dropdown
    user_locations = Location.query.filter_by(user_id=current_user.id).all()

    if request.method == 'POST':
        # Extract form data
        event_type = request.form.get('event_type')
        title = request.form.get('title')
        date_str = request.form.get('date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        location_id = request.form.get('location_id')
        notes = request.form.get('notes')

        # Handle new location creation
        if location_id == 'new':
            place_name = request.form.get('place_name')
            latitude = request.form.get('latitude')
            longitude = request.form.get('longitude')

            # Validate new location data
            if place_name and latitude and longitude:
                # Create new location
                new_location = Location(
                    user_id=current_user.id,
                    place_name=place_name,
                    latitude=float(latitude),
                    longitude=float(longitude)
                )
                db.session.add(new_location)
                db.session.flush()  # This assigns an ID to new_location

                # Use the new location for this event
                location_id = new_location.id
            else:
                # If new location data is incomplete, don't assign a location
                location_id = None

        # Combine date and time strings
        start_datetime = datetime.strptime(f"{date_str} {start_time_str}", '%Y-%m-%d %H:%M')

        # Handle optional end time
        end_datetime = None
        if end_time_str:
            end_datetime = datetime.strptime(f"{date_str} {end_time_str}", '%Y-%m-%d %H:%M')

        # Create new event
        new_event = Event(
            user_id=current_user.id,
            event_type=event_type,
            title=title,
            start_time=start_datetime,
            end_time=end_datetime,
            notes=notes
        )

        # Set location if provided
        if location_id and location_id != 'new':
            new_event.location_id = location_id

        # Add to database
        db.session.add(new_event)
        db.session.commit()

        flash('Event added successfully!', 'success')

        # Redirect to the timeline for the event's date
        return redirect(url_for('main.timeline', date=date_str))

    return render_template('add_event.html',
                          today_date=today_date,
                          locations=user_locations)

@main_bp.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    # Get the event or return 404 if not found
    event = Event.query.filter_by(id=event_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # Extract form data
        event_type = request.form.get('event_type')
        title = request.form.get('title')
        date_str = request.form.get('date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        location = request.form.get('location')
        notes = request.form.get('notes')

        # Update event data
        event.event_type = event_type
        event.title = title

        # Combine date and time strings
        event.start_time = datetime.strptime(f"{date_str} {start_time_str}", '%Y-%m-%d %H:%M')

        # Handle optional end time
        if end_time_str:
            event.end_time = datetime.strptime(f"{date_str} {end_time_str}", '%Y-%m-%d %H:%M')
        else:
            event.end_time = None

        # Update notes
        event.notes = notes

        # Handle location if provided
        # This is simplified - you'd typically handle location differently
        if location:
            if event.location:
                event.location.place_name = location
            else:
                new_location = Location(
                    latitude=0.0,
                    longitude=0.0,
                    place_name=location,
                    user_id=current_user.id
                )
                db.session.add(new_location)
                db.session.flush()
                event.location_id = new_location.id

        # Save changes
        db.session.commit()
        flash('Event updated successfully!', 'success')

        # Redirect to the timeline for the event's date
        return redirect(url_for('main.timeline', date=date_str))

    # Format the date and times for the form
    event_date = event.start_time.strftime('%Y-%m-%d')
    event_start_time = event.start_time.strftime('%H:%M')
    event_end_time = event.end_time.strftime('%H:%M') if event.end_time else None

    # Get location name if it exists
    location_name = event.location.place_name if event.location else None

    return render_template('edit_event.html',
                           event=event,
                           event_date=event_date,
                           event_start_time=event_start_time,
                           event_end_time=event_end_time,
                           location_name=location_name)


@main_bp.route('/delete_event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def delete_event(event_id):
    # Get the event or return 404 if not found
    event = Event.query.filter_by(id=event_id, user_id=current_user.id).first_or_404()

    # Store the event date for redirection after deletion
    event_date = event.start_time.strftime('%Y-%m-%d')

    if request.method == 'POST':
        # User confirmed deletion - remove the event
        db.session.delete(event)
        db.session.commit()

        flash('Event deleted successfully!', 'success')
        return redirect(url_for('main.timeline', date=event_date))

    # Format times for display in confirmation page
    event_date = event.start_time.strftime('%Y-%m-%d')
    event_start_time = event.start_time.strftime('%H:%M')
    event_end_time = event.end_time.strftime('%H:%M') if event.end_time else None

    # Show confirmation page
    return render_template('delete_event_confirm.html',
                           event=event,
                           event_date=event_date,
                           event_start_time=event_start_time,
                           event_end_time=event_end_time)

# Locations routes
@main_bp.route('/locations', methods=['GET'])
@login_required
def locations():
    # Get all locations for the current user
    user_locations = Location.query.filter_by(user_id=current_user.id).all()
    return render_template('locations.html', locations=user_locations)


@main_bp.route('/locations/add', methods=['GET', 'POST'])
@login_required
def add_location():
    if request.method == 'POST':
        place_name = request.form.get('place_name')
        latitude = float(request.form.get('latitude'))
        longitude = float(request.form.get('longitude'))

        new_location = Location(
            user_id=current_user.id,
            place_name=place_name,
            latitude=latitude,
            longitude=longitude
        )

        db.session.add(new_location)
        db.session.commit()

        flash('Location added successfully!', 'success')
        return redirect(url_for('main.locations'))

    # Default to a central map position
    default_lat = 0
    default_lon = 0

    return render_template('location_form.html',
                           location=None,
                           latitude=default_lat,
                           longitude=default_lon,
                           title="Add New Location")


@main_bp.route('/locations/edit/<int:location_id>', methods=['GET', 'POST'])
@login_required
def edit_location(location_id):
    location = Location.query.filter_by(id=location_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        location.place_name = request.form.get('place_name')
        location.latitude = float(request.form.get('latitude'))
        location.longitude = float(request.form.get('longitude'))

        db.session.commit()
        flash('Location updated successfully!', 'success')
        return redirect(url_for('main.locations'))

    return render_template('location_form.html',
                           location=location,
                           latitude=location.latitude,
                           longitude=location.longitude,
                           title="Edit Location")


@main_bp.route('/locations/delete/<int:location_id>', methods=['GET', 'POST'])
@login_required
def delete_location(location_id):
    location = Location.query.filter_by(id=location_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # Check if location is used by any events
        if location.events:
            flash('Cannot delete location that is used by events.', 'danger')
            return redirect(url_for('main.locations'))

        db.session.delete(location)
        db.session.commit()
        flash('Location deleted successfully!', 'success')
        return redirect(url_for('main.locations'))

    return render_template('delete_location_confirm.html', location=location)

# API routes for mobile/AJAX access
@main_bp.route('/api/events', methods=['GET'])
@login_required
def get_events():
    events = Event.query.filter_by(user_id=current_user.id).order_by(Event.start_time.desc()).all()

    # Convert to JSON representation
    result = []
    for event in events:
        event_data = {
            'id': event.id,
            'type': event.event_type,
            'title': event.title,
            'start_time': event.start_time.isoformat(),
            'end_time': event.end_time.isoformat() if event.end_time else None
        }
        result.append(event_data)

    return jsonify(result)

@main_bp.route('/api/location', methods=['POST'])
@login_required
def log_location():
    # Placeholder for location logging API endpoint
    return jsonify({'status': 'success'})