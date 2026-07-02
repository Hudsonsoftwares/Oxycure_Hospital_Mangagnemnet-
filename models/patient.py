import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalPatient(models.Model):
    _name = "hospital.patient"
    _description = "Hospital Patient"
    _rec_name = "name"

    _sql_constraints = [
        ('patient_id_unique', 'unique(patient_id)', 'The Patient ID must be unique!'),
    ]

    # ==========================
    # Patient Identification
    # ==========================

    patient_id = fields.Char(
        string="UHID / Patient ID",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )

    name = fields.Char(
        string="Patient Name",
        required=True
    )

    image_1920 = fields.Image(
        string="Photo"
    )

    # ==========================
    # Personal Information
    # ==========================

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

    
    nationality = fields.Char(
        string="Nationality"
    )

   

    # ==========================
    # Contact Information
    # ==========================

    phone = fields.Char(
        string="Phone Number"
    )

    mobile = fields.Char(
        string="Mobile"
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
    # Medical Information
    # ==========================

    allergies = fields.Text(
        string="Allergies"
    )

    chronic_diseases = fields.Text(
        string="Chronic Diseases"
    )

    current_medications = fields.Text(
        string="Current Medications"
    )

    medical_remarks = fields.Text(
        string="Medical Remarks"
    )

    # ==========================
    # Emergency Contact
    # ==========================

    emergency_contact_name = fields.Char(
        string="Emergency Contact Name"
    )

    emergency_contact_number = fields.Char(
        string="Emergency Contact Number"
    )

    relationship = fields.Selection([
        ('father', 'Father'),
        ('mother', 'Mother'),
        ('spouse', 'Spouse'),
        ('brother', 'Brother'),
        ('sister', 'Sister'),
        ('guardian', 'Guardian'),
        ('friend', 'Friend'),
        ('other', 'Other')
    ], string="Relationship")

    op_ids = fields.One2many(
        "hospital.op",
        "patient_id",
        string="OP Visits"
    )

    # ==========================
    # Registration
    # ==========================

    registration_date = fields.Date(
        string="Registration Date",
        default=fields.Date.today
    )

    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('deceased', 'Deceased')
    ],
        string="Patient Status",
        default="active"
    )

    notes = fields.Text(
        string="Notes"
    )

    @api.model
    def create(self, vals):
        if vals.get("patient_id", "New") == "New":
            vals["patient_id"] = self.env["ir.sequence"].next_by_code(
                "hospital.patient"
            ) or "New"
        return super().create(vals)

    @api.onchange('dob')
    def _onchange_dob(self):
        if self.dob:
            today = fields.Date.today()
            self.age = today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))
        else:
            self.age = 0

    @api.constrains('dob')
    def _check_dob(self):
        for record in self:
            if record.dob and record.dob > fields.Date.today():
                raise ValidationError(_("The patient's date of birth cannot be in the future."))

    @api.constrains('age')
    def _check_age(self):
        for record in self:
            if record.age < 0:
                raise ValidationError(_("Age cannot be negative."))
            if record.age > 125:
                raise ValidationError(_("Age must be less than 125 years."))

    @api.constrains('email')
    def _check_email(self):
        for record in self:
            if record.email:
                email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
                if not re.match(email_regex, record.email):
                    raise ValidationError(_("Please enter a valid email address."))

    @api.constrains('phone', 'mobile', 'emergency_contact_number')
    def _check_phone_numbers(self):
        phone_regex = r"^\+?[\d\s\-\(\)]+$"
        for record in self:
            for field_name in ['phone', 'mobile', 'emergency_contact_number']:
                val = getattr(record, field_name)
                if val:
                    if not re.match(phone_regex, val):
                        raise ValidationError(_("Invalid characters in %s. Only numbers and +, -, (), spaces are allowed.") % self._fields[field_name].string)