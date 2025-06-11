import gpxpy
import os
import pytz
import requests
from datetime import datetime, time, timedelta
from flask import Blueprint, render_template, redirect, url_for, jsonify, request, session, flash, current_app
from flask_login import login_required, current_user, logout_user, login_user
from gpxpy.geo import haversine_distance
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from . import db
from .model import Event, User, Location, GPSPosition, APIKey
from .forms import CheckInForm, EventForm

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

        # Save the user's timezone in the session
        session['timezone'] = request.form.get('timezone')

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


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Validate input
        if not current_password or not new_password or not confirm_password:
            flash('All fields are required', 'danger')
        elif not check_password_hash(current_user.password_hash, current_password):
            flash('Current password is incorrect', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match', 'danger')
        elif len(new_password) < 8:
            flash('Password must be at least 8 characters long', 'danger')
        else:
            # Update password
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Password updated successfully', 'success')
            return redirect(url_for('main.user_settings'))

    return render_template('user_settings.html')


@main_bp.route('/settings/api-keys', methods=['GET', 'POST'])
@login_required
def api_keys():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create':
            key_name = request.form.get('key_name')
            if not key_name:
                flash('Key name is required', 'danger')
            else:
                new_key = APIKey(
                    user_id=current_user.id,
                    name=key_name,
                    key=APIKey.generate_key()
                )
                db.session.add(new_key)
                db.session.commit()

                # Show the key only once
                flash(f'API key created: {new_key.key}', 'success')
                flash('Save this key now - it won\'t be shown again!', 'warning')

        elif action == 'delete':
            key_id = request.form.get('key_id')
            key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first()

            if key:
                db.session.delete(key)
                db.session.commit()
                flash('API key deleted', 'success')

    api_keys = APIKey.query.filter_by(user_id=current_user.id).all()
    return render_template('api_keys.html', api_keys=api_keys)


# Timeline routes
@main_bp.route('/timeline')
@login_required
def timeline():
    # Get date from query parameter or use today's date
    date_str = request.args.get('date')

    user_tz = get_user_timezone()

    try:
        if date_str:
            # Parse the date string from the URL parameter
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            # Default to today's date
            current_date = datetime.now(user_tz).date()
    except ValueError:
        # Handle invalid date format
        current_date = datetime.now(user_tz).date()

    # Calculate yesterday and tomorrow for navigation
    yesterday = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow = (current_date + timedelta(days=1)).strftime('%Y-%m-%d')

    # Format the current date for display
    current_date_formatted = current_date.strftime('%A, %B %d, %Y')

    # Get events for the selected date
    start_of_day_utc = user_tz.localize(datetime.combine(current_date, datetime.min.time())).astimezone(pytz.UTC)
    end_of_day_utc = user_tz.localize(datetime.combine(current_date, datetime.max.time())).astimezone(pytz.UTC)

    events_utc = Event.query.filter_by(user_id=current_user.id) \
        .filter(Event.start_time >= start_of_day_utc) \
        .filter(Event.start_time <= end_of_day_utc) \
        .order_by(Event.start_time).all()

    # Convert event times to user's local timezone
    events_local = []
    for event in events_utc:
        event.start_time = event.start_time.replace(tzinfo=pytz.UTC).astimezone(user_tz)
        if event.end_time:
            event.end_time = event.end_time.replace(tzinfo=pytz.UTC).astimezone(user_tz)
        events_local.append(event)

    return render_template('timeline.html',
                           events=events_local,
                           yesterday=yesterday,
                           tomorrow=tomorrow,
                           current_date=current_date.strftime('%Y-%m-%d'),
                           current_date_formatted=current_date_formatted)


@main_bp.route('/add_event', methods=['GET', 'POST'])
@login_required
def add_event():
    form = EventForm()

    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    user_tz = get_user_timezone()

    try:
        current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = datetime.now(user_tz).date()

    # If location coordinates are provided, try to estimate start time and find nearby locations
    if lat and lon:
        try:
            lat = float(lat)
            lon = float(lon)
        except ValueError:
            flash('Invalid latitude or longitude', 'danger')
            return redirect(url_for('main.add_event'))

        # Convert to UTC for database query
        start_of_day = user_tz.localize(datetime.combine(current_date, time.min)).astimezone(pytz.UTC)
        end_of_day = user_tz.localize(datetime.combine(current_date, time.max)).astimezone(pytz.UTC)

        # Find GPS points near the clicked location (within ~100 meters)
        nearby_points = GPSPosition.query.filter(
            GPSPosition.user_id == current_user.id,
            GPSPosition.timestamp >= start_of_day,
            GPSPosition.timestamp <= end_of_day,
            # Approximate distance filter (0.001 degree is roughly 100m)
            GPSPosition.latitude.between(lat - 0.001, lat + 0.001),
            GPSPosition.longitude.between(lon - 0.001, lon + 0.001)
        ).order_by(GPSPosition.timestamp).all()

        # If there are nearby points, use the timestamp from the first one
        if nearby_points:
            # Convert UTC time to user's local timezone
            local_time = nearby_points[0].timestamp.replace(tzinfo=pytz.UTC).astimezone(user_tz)
            # Set the form default time
            form.start_time.data = local_time

        # Find locations near the clicked point, sorted by distance
        locations = Location.query.filter_by(user_id=current_user.id).all()

        # Sort locations by distance to clicked point
        for location in locations:
            location.distance = haversine_distance(
                lat, lon,
                location.latitude, location.longitude,
            )

        # Sort locations by distance from closest to furthest
        sorted_locations = sorted(locations, key=lambda x: x.distance)

        # Populate the select field with sorted locations
        form.location_id.choices = [
            ('new', '-- Add New Location --'),
            *[(str(l.id), l.place_name + f" ({l.distance:0.1f}m)") for l in sorted_locations]
        ]

        # Set the hidden fields for new location
        form.new_location_lat.data = lat
        form.new_location_lon.data = lon

    if not current_date:
        current_date = datetime.now().strftime('%Y-%m-%d')

    # Fill in the location selector if not already populated
    if len(form.location_id.choices) == 1:
        form.location_id.choices.extend(
            (str(l.id), l.place_name) for l in Location.query.filter_by(user_id=current_user.id).all()
        )

    if form.validate_on_submit():
        location_id = form.location_id.data

        # Handle new location creation
        if location_id == 'new':
            place_name = form.place_name.data
            latitude = form.new_location_lat.data
            longitude = form.new_location_lon.data

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
        start_datetime_local = form.start_time.data
        start_datetime = get_user_timezone().localize(start_datetime_local).astimezone(pytz.UTC)

        # Handle optional end time
        end_datetime = None
        if form.end_time.data:
            end_datetime_local = form.end_time.data
            end_datetime = get_user_timezone().localize(end_datetime_local).astimezone(pytz.UTC)

        # Create new event
        new_event = Event(
            user_id=current_user.id,
            event_type=form.event_type.data,
            title=form.title.data,
            start_time=start_datetime,
            end_time=end_datetime,
            notes=form.notes.data,
        )

        # Set location if provided
        if location_id and location_id != 'new':
            new_event.location_id = location_id

        # Add to database
        db.session.add(new_event)
        db.session.commit()

        # Go back to the timeline for the event's date
        date_str = start_datetime_local.strftime('%Y-%m-%d')

        flash('Event added successfully!', 'success')

        # Redirect to the timeline for the event's date
        return redirect(url_for('main.timeline', date=date_str))

    return render_template('add_event.html',
                           form=form,
                           date=current_date)


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
        category = request.form.get('category', '')
        address = request.form.get('address', '')

        new_location = Location(
            user_id=current_user.id,
            place_name=place_name,
            latitude=latitude,
            longitude=longitude,
            category=category,
            address=address,
            source='user',
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


@main_bp.route('/gps/import', methods=['GET', 'POST'])
@login_required
def import_gpx():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'gpx_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)

        files = request.files.getlist('gpx_file')  # Get a list of files
        total_points_added = 0
        files_processed = 0
        errors = []

        for file in files:
            if file.filename == '':
                flash('No selected file', 'danger')
                continue  # Skip to the next file

            if file and file.filename.endswith('.gpx'):
                filename = secure_filename(file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

                try:
                    file.save(file_path)

                    # Process the GPX file
                    with open(file_path, 'r') as gpx_file_content:
                        gpx = gpxpy.parse(gpx_file_content)

                    points_added_this_file = 0
                    for track in gpx.tracks:
                        for segment in track.segments:
                            for point in segment.points:
                                # Create GPS position for each point
                                position = GPSPosition(
                                    user_id=current_user.id,
                                    timestamp=point.time,
                                    latitude=point.latitude,
                                    longitude=point.longitude,
                                    altitude=point.elevation,
                                    speed=point.speed,
                                    source='gpx_import'
                                )
                                db.session.add(position)
                                points_added_this_file += 1

                    db.session.commit()
                    total_points_added += points_added_this_file
                    files_processed += 1

                except Exception as e:
                    db.session.rollback()  # Rollback changes for the current file if an error occurs
                    errors.append(f"Error processing file {filename}: {str(e)}")

                finally:
                    # Remove the file after processing
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                errors.append(f"Invalid file type: {file.filename}. Only .gpx files are allowed.")

        if files_processed > 0:
            flash(f'Successfully imported {total_points_added} GPS points from {files_processed} file(s).', 'success')

        for error in errors:
            flash(error, 'danger')

        return redirect(url_for('main.gps_data'))

    return render_template('import_gpx.html')


@main_bp.route('/gps/data')
@login_required
def gps_data():
    # Get date from query parameter or use today's date
    date_str = request.args.get('date')

    user_tz = get_user_timezone()

    try:
        if date_str:
            # Parse the date string from the URL parameter
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            # Default to today's date
            current_date = datetime.now(user_tz).date()
    except ValueError:
        # Handle invalid date format
        current_date = datetime.now(user_tz).date()

    # Calculate yesterday and tomorrow for navigation
    yesterday = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow = (current_date + timedelta(days=1)).strftime('%Y-%m-%d')

    # Format the current date for display
    current_date_formatted = current_date.strftime('%A, %B %d, %Y')

    # Get GPS data statistics for the selected day
    start_of_day = user_tz.localize(datetime.combine(current_date, datetime.min.time())).astimezone(pytz.UTC)
    end_of_day = user_tz.localize(datetime.combine(current_date, datetime.max.time())).astimezone(pytz.UTC)

    gps_count = GPSPosition.query.filter_by(user_id=current_user.id) \
        .filter(GPSPosition.timestamp >= start_of_day) \
        .filter(GPSPosition.timestamp <= end_of_day) \
        .count()

    return render_template('gps_data.html',
                           gps_count=gps_count,
                           yesterday=yesterday,
                           tomorrow=tomorrow,
                           current_date=current_date.strftime('%Y-%m-%d'),
                           current_date_formatted=current_date_formatted)


# API routes for mobile/AJAX access
@main_bp.route('/api/set_timezone', methods=['POST'])
@login_required
def set_timezone():
    data = request.get_json()
    timezone = data.get('timezone')

    if timezone:
        session['timezone'] = timezone
        return jsonify({'status': 'success'})

    return jsonify({'status': 'error', 'message': 'No timezone provided'}), 400


def get_user_timezone():
    """Helper function to get timezone from session or default to UTC"""
    return pytz.timezone(session.get('timezone') or 'UTC')


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


@main_bp.route('/api/gps/positions', methods=['GET'])
@login_required
def get_gps_positions():
    date = request.args.get('date')
    user_tz = get_user_timezone()

    try:
        # Parse date and create start/end datetime objects
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        # Convert start and end times from the user's timezone to UTC
        start_datetime = user_tz.localize(datetime.combine(date_obj, time.min)).astimezone(pytz.UTC)
        end_datetime = user_tz.localize(datetime.combine(date_obj, time.max)).astimezone(pytz.UTC)
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Query positions for the specified day
    positions = GPSPosition.query.filter(
        GPSPosition.user_id == current_user.id,
        GPSPosition.timestamp >= start_datetime,
        GPSPosition.timestamp <= end_datetime
    ).order_by(GPSPosition.timestamp).all()

    # Convert to GeoJSON for mapping
    features = []
    for pos in positions:
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [pos.longitude, pos.latitude]
            },
            'properties': {
                'id': pos.id,
                'timestamp': pos.timestamp.isoformat() + 'Z',
                'altitude': pos.altitude,
                'accuracy': pos.accuracy,
                'speed': pos.speed,
                'source': pos.source
            }
        })

    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    return jsonify(geojson)


@main_bp.route('/api/gps/log', methods=['POST'])
def log_gps_position():
    # Get API key from header or query parameter
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')

    if not api_key:
        return jsonify({'error': 'API key required'}), 401

    # Validate API key
    key_record = APIKey.query.filter_by(key=api_key).first()
    if not key_record:
        return jsonify({'error': 'Invalid API key'}), 401

    # Update last used timestamp
    key_record.last_used = datetime.now(pytz.UTC)

    # GPSLogger typically sends data as URL parameters
    latitude = request.args.get('lat')
    longitude = request.args.get('lon')
    timestamp_str = request.args.get('time')  # ISO format
    altitude = request.args.get('alt')
    accuracy = request.args.get('acc')
    speed = request.args.get('spd')
    bearing = request.args.get('bearing')

    # Validate required fields
    if not all([latitude, longitude, timestamp_str]):
        return jsonify({'error': 'Missing required parameters'}), 400

    try:
        # Parse timestamp
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Create GPS position
        position = GPSPosition(
            user_id=key_record.user_id,
            timestamp=timestamp,
            latitude=float(latitude),
            longitude=float(longitude),
            altitude=float(altitude) if altitude else None,
            accuracy=float(accuracy) if accuracy else None,
            speed=float(speed) if speed else None,
            bearing=float(bearing) if bearing else None,
            provider=request.args.get('provider', 'unknown'),
            source='gpslogger'
        )

        db.session.add(position)
        db.session.commit()

        return jsonify({'status': 'success'}), 200

    except (ValueError, TypeError) as e:
        current_app.logger.error(f"Error logging GPS position: {str(e)}")
        return jsonify({'error': str(e)}), 400


@main_bp.route('/checkin', methods=['GET', 'POST'])
@login_required
def checkin():
    form = CheckInForm()

    # Get user's current position (from query params or geolocation JS)
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    # Initialize empty lists for results
    combined_locations = []
    max_distance_km = 1

    if lat and lon:
        # Convert to float
        try:
            lat = float(lat)
            lon = float(lon)

            # Get user's locations
            user_locations = Location.query.filter_by(user_id=current_user.id).all()

            foursquare_venues_to_ignore = set([
                loc.source_id for loc in user_locations if loc.source == 'foursquare'
            ])

            # Process user locations
            for location in user_locations:
                # Calculate distance
                distance = haversine_distance(lat, lon, location.latitude, location.longitude)
                distance_km = distance / 1000

                # Skip locations beyond 10km
                if distance_km > max_distance_km:
                    continue

                # Add distance to location object
                location.distance = distance
                location.distance_km = distance_km
                location.distance_m = distance
                location.source = 'user'

                combined_locations.append(location)

            # Get Foursquare locations
            foursquare_venues = get_foursquare_venues(lat, lon, radius=max_distance_km * 1000, limit=50)

            # Process Foursquare venues
            for venue in foursquare_venues:
                # Skip venues already in user's locations
                if venue['id'] in foursquare_venues_to_ignore:
                    continue

                # Calculate distance
                distance = haversine_distance(lat, lon, venue['lat'], venue['lon'])
                distance_km = distance / 1000

                # Skip locations beyond 10km (should be filtered by API, but double-check)
                if distance_km > max_distance_km:
                    continue

                # Create a location-like object
                venue_obj = type('FoursquareVenue', (), {
                    'id': venue['id'],
                    'place_name': venue['name'],
                    'category': venue['category'],
                    'latitude': venue['lat'],
                    'longitude': venue['lon'],
                    'address': venue['address'],
                    'distance': distance,
                    'distance_km': distance_km,
                    'distance_m': distance,
                    'source': 'foursquare'
                })

                combined_locations.append(venue_obj)

            # Sort all locations by distance
            combined_locations.sort(key=lambda x: x.distance)

        except ValueError:
            flash('Invalid coordinates provided', 'danger')

    # Handle form submission for check-in
    if form.validate_on_submit():
        # Get current time in user's timezone
        user_tz = get_user_timezone()
        current_time = datetime.now(user_tz)

        if form.location_type.data == 'user':
            # Check in to existing user location
            location = Location.query.get(form.location_id.data)
            if not location or location.user_id != current_user.id:
                flash('Invalid location', 'danger')
                return redirect(url_for('main.checkin'))

            # Create event with this location
            event = Event(
                user_id=current_user.id,
                title=form.title.data or f"Checked in at {location.place_name}",  # Use custom title if provided
                event_type=form.event_type.data,
                start_time=current_time,
                location_id=location.id,
                notes=form.notes.data,
            )
            db.session.add(event)
            db.session.commit()

            flash(f'Checked in at {location.place_name}!', 'success')
            return redirect(url_for('main.timeline'))

        elif form.location_type.data == 'foursquare':
            # Create new location from Foursquare data
            place_name = form.place_name.data
            fs_lat = float(form.fs_lat.data)
            fs_lon = float(form.fs_lon.data)
            fs_category = form.fs_category.data
            fs_id = form.fs_id.data

            # Create new location
            new_location = Location(
                user_id=current_user.id,
                place_name=place_name,
                latitude=fs_lat,
                longitude=fs_lon,
                category=fs_category,
                source='foursquare',
                source_id=fs_id,
            )
            db.session.add(new_location)
            db.session.flush()  # Get ID without committing

            # Create event with this location
            event = Event(
                user_id=current_user.id,
                title=form.title.data or f"Checked in at {place_name}",  # Use custom title if provided
                event_type=form.event_type.data,
                start_time=current_time,
                location_id=new_location.id,
                notes=form.notes.data,
            )
            db.session.add(event)
            db.session.commit()

            flash(f'Checked in at {place_name}!', 'success')
            return redirect(url_for('main.timeline'))

    return render_template('checkin.html',
                           form=form,
                           locations=combined_locations,
                           lat=lat,
                           lon=lon)


def get_foursquare_venues(lat, lon, radius=1000, limit=10):
    """Fetch nearby venues from Foursquare API"""
    api_key = current_app.config.get('FOURSQUARE_API_KEY')
    if not api_key:
        return []

    # API endpoint
    url = "https://api.foursquare.com/v3/places/search"

    # Parameters
    params = {
        'll': f"{lat},{lon}",
        'radius': int(radius),
        'limit': limit,
        'sort': 'distance',
    }

    # Headers
    headers = {
        "Accept": "application/json",
        "Authorization": api_key
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        print(response.request.url)
        print(response.status_code)
        if response.status_code != 200:
            return []


        data = response.json()
        results = []

        # Format results to match our needs
        for venue in data.get('results', []):
            if 'geocodes' not in venue or 'main' not in venue['geocodes']:
                continue

            # Get category
            category = venue.get('categories', [{}])[0].get('name', 'Uncategorized') if venue.get(
                'categories') else 'Uncategorized'

            results.append({
                'id': venue.get('fsq_id'),
                'name': venue.get('name'),
                'category': category,
                'lat': venue['geocodes']['main']['latitude'],
                'lon': venue['geocodes']['main']['longitude'],
                'address': venue.get('location', {}).get('formatted_address', '')
            })

        return results
    except Exception as e:
        current_app.logger.error(f"Foursquare API error: {str(e)}")
        return []
