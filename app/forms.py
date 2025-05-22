from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, TimeField, TextAreaField, HiddenField, FloatField
from wtforms.fields import DateTimeLocalField
from wtforms.validators import DataRequired, Optional

class EventForm(FlaskForm):
    """Form for creating and editing events"""

    # Basic event details
    event_type = SelectField(
        'Event Type',
        validators=[DataRequired()],
        choices=[
            ('', 'Select a type'),
            ('meal', 'Meal'),
            ('travel', 'Travel'),
            ('hygiene', 'Hygiene'),
            ('work', 'Work'),
            ('social', 'Social'),
            ('exercise', 'Exercise'),
            ('other', 'Other')
        ]
    )

    title = StringField('Title', validators=[DataRequired()])
    start_time = DateTimeLocalField('Start Time', validators=[DataRequired()])
    end_time = DateTimeLocalField('End Time', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])

    # Location fields
    location_id = SelectField('Location', coerce=str, validators=[DataRequired()])

    # New location fields (used when adding a new location)
    new_location_lat = HiddenField()
    new_location_lon = HiddenField()
    place_name = StringField('Location Name')

    def __init__(self, *args, **kwargs):
        super(EventForm, self).__init__(*args, **kwargs)
        # Location choices will be set dynamically in the route
        # The form starts with just the "Add New Location" option
        self.location_id.choices = [('new', '-- Add New Location --')]

    def validate(self, extra_validators=None):
        """Custom validation to handle location fields"""
        if not super(EventForm, self).validate(extra_validators):
            return False

        # If "Add New Location" is selected, validate the new location fields
        if self.location_id.data == 'new':
            if not self.place_name.data:
                self.place_name.errors = ['Location name is required when adding a new location']
                return False

            if not self.new_location_lat.data or not self.new_location_lon.data:
                self.location_id.errors = ['Please select a location on the map']
                return False

        return True