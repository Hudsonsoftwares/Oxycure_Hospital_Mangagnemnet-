import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalDoctor(models.Model):
    _name = "hospital.doctor"
    _description = "Hospital Doctor"
    _rec_name = "name"

    # ==========================
    # Doctor Information
    # ==========================
    doctor_id = fields.Char(
        string="Doctor ID",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    name = fields.Char(
        string="Doctor Name",
        required=True
    )
    image_1920 = fields.Image(
        string="Photo"
    )
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string="Gender", required=True)
    dob = fields.Date(
        string="Date of Birth"
    )
    age = fields.Integer(
        string="Age"
    )
    blood_group = fields.Selection([
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
        ('O+', 'O+'),
        ('O-', 'O-')
    ], string="Blood Group")
    marital_status = fields.Selection([
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed')
    ], string="Marital Status")

    # ==========================
    # Professional Information
    # ==========================
    department_id = fields.Many2one(
        "hospital.department",
        string="Department"
    )
    qualification = fields.Char(
        string="Qualification"
    )
    specialization = fields.Char(
        string="Specialization"
    )
    medical_registration_no = fields.Char(
        string="Medical Registration No"
    )
    experience = fields.Integer(
        string="Experience (Years)"
    )
    consultation_fee = fields.Float(
        string="Consultation Fee"
    )
    joining_date = fields.Date(
        string="Joining Date"
    )
    signature = fields.Image(
        string="Doctor Signature",
        help="Upload doctor's signature image to display on certificates and letters"
    )
    user_id = fields.Many2one(
        "res.users",
        string="Odoo User",
        help="Linked Odoo user account for this doctor"
    )

    # ==========================
    # Contact Details
    # ==========================
    mobile = fields.Char(
        string="Mobile"
    )
    phone = fields.Char(
        string="Phone"
    )
    email = fields.Char(
        string="Email"
    )
    address = fields.Text(
        string="Address"
    )
    city = fields.Char(
        string="City"
    )
    state = fields.Char(
        string="State"
    )
    zip = fields.Char(
        string="ZIP Code"
    )
    country_id = fields.Many2one(
        "res.country",
        string="Country"
    )

    # ==========================
    # Availability
    # ==========================
    consultation_days = fields.Char(
        string="Consultation Days",
        placeholder="e.g. Monday - Saturday"
    )
    consultation_time = fields.Char(
        string="Consultation Time",
        placeholder="e.g. 09:00 AM - 05:00 PM"
    )
    room_number = fields.Char(
        string="Room Number"
    )

    # ==========================
    # Status and Notes
    # ==========================
    status = fields.Selection([
        ('available', 'Available'),
        ('on_leave', 'On Leave'),
        ('inactive', 'Inactive')
    ], string="Status", default="available", required=True)
    notes = fields.Text(
        string="Notes"
    )

    # ==========================
    # Auto Sequence / Actions
    # ==========================
    @api.model
    def create(self, vals):
        if vals.get("doctor_id", "New") == "New":
            vals["doctor_id"] = self.env["ir.sequence"].next_by_code(
                "hospital.doctor"
            ) or "New"
        return super().create(vals)

    @api.onchange('dob')
    def _onchange_dob(self):
        if self.dob:
            today = fields.Date.today()
            self.age = today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))
        else:
            self.age = 0

    # ==========================
    # Validations
    # ==========================
    @api.constrains('dob')
    def _check_dob(self):
        for record in self:
            if record.dob and record.dob > fields.Date.today():
                raise ValidationError(_("The doctor's date of birth cannot be in the future."))

    @api.constrains('age')
    def _check_age(self):
        for record in self:
            if record.dob and record.age < 18:
                raise ValidationError(_("A practicing doctor must be at least 18 years old."))
            if record.age < 0:
                raise ValidationError(_("Age cannot be negative."))
            if record.age > 120:
                raise ValidationError(_("Age is invalid (maximum 120 years)."))

    @api.constrains('experience')
    def _check_experience(self):
        for record in self:
            if record.experience < 0:
                raise ValidationError(_("Experience cannot be negative."))
            if record.experience > 80:
                raise ValidationError(_("Experience is invalid (maximum 80 years)."))

    @api.constrains('consultation_fee')
    def _check_consultation_fee(self):
        for record in self:
            if record.consultation_fee < 0.0:
                raise ValidationError(_("Consultation fee cannot be negative."))

    @api.constrains('joining_date', 'dob')
    def _check_joining_date(self):
        for record in self:
            if record.joining_date:
                if record.joining_date > fields.Date.today():
                    raise ValidationError(_("Joining date cannot be in the future."))
                if record.dob and record.joining_date < record.dob:
                    raise ValidationError(_("Joining date cannot be before the date of birth."))

    @api.constrains('email')
    def _check_email(self):
        for record in self:
            if record.email:
                email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
                if not re.match(email_regex, record.email):
                    raise ValidationError(_("Please enter a valid email address."))

    @api.constrains('mobile', 'phone')
    def _check_phones(self):
        phone_regex = r"^\+?[\d\s\-\(\)]+$"
        for record in self:
            for field_name in ['mobile', 'phone']:
                val = getattr(record, field_name)
                if val:
                    if not re.match(phone_regex, val):
                        raise ValidationError(_("Invalid characters in %s. Only numbers and +, -, (), spaces are allowed.") % self._fields[field_name].string)
