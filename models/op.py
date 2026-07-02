import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalOp(models.Model):
    _name = "hospital.op"
    _description = "Outpatient Registration"
    _rec_name = "op_number"
    _order = "registration_datetime desc"

    # ==========================
    # OP Information
    # ==========================
    op_number = fields.Char(
        string="OP Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Appointment"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        required=True
    )
    uhid = fields.Char(
        related="patient_id.patient_id",
        store=True,
        string="UHID",
        readonly=True
    )
    doctor_id = fields.Many2one(
        "hospital.doctor",
        string="Doctor",
        required=True
    )
    department_id = fields.Many2one(
        "hospital.department",
        related="doctor_id.department_id",
        store=True,
        string="Department",
        readonly=True
    )
    registration_datetime = fields.Datetime(
        string="Registration Date & Time",
        default=fields.Datetime.now,
        required=True
    )
    token_number = fields.Integer(
        string="Token Number"
    )
    visit_type = fields.Selection([
        ('new', 'New'),
        ('follow_up', 'Follow-up'),
        ('emergency', 'Emergency')
    ], string="Visit Type", default="new", required=True)
    
    status = fields.Selection([
        ('waiting', 'Waiting'),
        ('checked_in', 'Checked In'),
        ('consultation', 'In Consultation'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string="Status", default="waiting", required=True)

    # ==========================
    # Triage & Vitals
    # ==========================
    triage_nurse_id = fields.Many2one(
        "res.users",
        string="Triage Nurse",
        default=lambda self: self.env.user
    )
    triage_datetime = fields.Datetime(
        string="Triage Time"
    )
    priority = fields.Selection([
        ('emergency', 'Emergency 🔴'),
        ('urgent', 'Urgent 🟠'),
        ('semi_urgent', 'Semi-Urgent 🟡'),
        ('normal', 'Normal 🟢')
    ], string="Priority", default="normal", required=True)
    
    height = fields.Float(
        string="Height (cm)"
    )
    weight = fields.Float(
        string="Weight (kg)"
    )
    bmi = fields.Float(
        string="BMI",
        compute="_compute_bmi",
        store=True
    )
    temperature = fields.Float(
        string="Temperature (°C)"
    )
    blood_pressure = fields.Char(
        string="Blood Pressure",
        placeholder="e.g. 120/80"
    )
    pulse_rate = fields.Integer(
        string="Pulse Rate (bpm)"
    )
    respiratory_rate = fields.Integer(
        string="Respiratory Rate"
    )
    spo2 = fields.Integer(
        string="SpO₂ (%)"
    )
    pain_score = fields.Integer(
        string="Pain Score (0-10)"
    )

    # ==========================
    # Clinical Assessment
    # ==========================
    chief_complaint = fields.Text(
        string="Chief Complaint"
    )
    present_illness = fields.Text(
        string="Present Illness"
    )
    past_history = fields.Text(
        string="Past Medical History"
    )
    allergies = fields.Text(
        related="patient_id.allergies",
        string="Allergies",
        readonly=True
    )
    current_medications = fields.Text(
        related="patient_id.current_medications",
        string="Current Medications",
        readonly=True
    )
    nurse_notes = fields.Text(
        string="Nurse Notes"
    )

    # ==========================
    # Doctor Consultation
    # ==========================
    diagnosis = fields.Text(
        string="Diagnosis"
    )
    clinical_notes = fields.Text(
        string="Clinical Notes"
    )
    follow_up_date = fields.Date(
        string="Follow-up Date"
    )
    follow_up_required = fields.Boolean(
        string="Follow-up Required"
    )

    # ==========================
    # Actions / Milestones
    # ==========================
    prescription_line_ids = fields.One2many(
        "hospital.prescription.line",
        "op_id",
        string="Prescription Lines"
    )

    prescription_created = fields.Boolean(
        string="Prescription Created",
        compute="_compute_prescription_created",
        store=True
    )
    lab_request_line_ids = fields.One2many(
        "hospital.lab.request.line",
        "op_id",
        string="Laboratory Requests"
    )

    lab_request_created = fields.Boolean(
        string="Lab Request Created",
        compute="_compute_lab_request_created",
        store=True
    )
    scan_request_created = fields.Boolean(
        string="Scan Request Created"
    )
    pharmacy_completed = fields.Boolean(
        string="Pharmacy Completed"
    )
    billing_completed = fields.Boolean(
        string="Billing Completed"
    )

    # ==========================
    # Internal Notes
    # ==========================
    notes = fields.Text(
        string="Internal Notes"
    )

    # ==========================
    # Computes & Onchanges
    # ==========================
    @api.depends('height', 'weight')
    def _compute_bmi(self):
        for record in self:
            if record.height > 0.0 and record.weight > 0.0:
                height_m = record.height / 100.0
                record.bmi = record.weight / (height_m ** 2)
            else:
                record.bmi = 0.0

    @api.depends('prescription_line_ids')
    def _compute_prescription_created(self):
        for record in self:
            record.prescription_created = bool(record.prescription_line_ids)

    @api.depends('lab_request_line_ids')
    def _compute_lab_request_created(self):
        for record in self:
            record.lab_request_created = bool(record.lab_request_line_ids)

    @api.onchange('appointment_id')
    def _onchange_appointment_id(self):
        if self.appointment_id:
            self.patient_id = self.appointment_id.patient_id
            self.doctor_id = self.appointment_id.doctor_id
            self.visit_type = self.appointment_id.visit_type
            self.token_number = self.appointment_id.token_number
            self.chief_complaint = self.appointment_id.chief_complaint

    @api.onchange('height', 'weight', 'priority', 'temperature', 'blood_pressure', 'pulse_rate', 'respiratory_rate', 'spo2', 'pain_score')
    def _onchange_vitals(self):
        if not self.triage_datetime:
            self.triage_datetime = fields.Datetime.now()

    # ==========================
    # Actions / CRUD
    # ==========================
    @api.model
    def create(self, vals):
        if vals.get("op_number", "New") == "New":
            vals["op_number"] = self.env["ir.sequence"].next_by_code("hospital.op") or "New"

        # Auto-token assignment for walk-in OP visits
        doctor_id = vals.get("doctor_id")
        reg_dt_val = vals.get("registration_datetime") or fields.Datetime.now()
        if isinstance(reg_dt_val, str):
            reg_date = fields.Datetime.to_datetime(reg_dt_val).date()
        else:
            reg_date = reg_dt_val.date()

        if doctor_id and not vals.get("token_number"):
            # Count other OP visits for this doctor today
            start_date = fields.Datetime.to_string(fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
            end_date = fields.Datetime.to_string(fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999))
            domain = [
                ('doctor_id', '=', doctor_id),
                ('registration_datetime', '>=', start_date),
                ('registration_datetime', '<=', end_date)
            ]
            last_op = self.search(domain, order="token_number desc", limit=1)
            vals["token_number"] = (last_op.token_number or 0) + 1

        record = super().create(vals)
        record._sync_lab_request()
        record._sync_billing_invoice()
        record._sync_medicine_billing()
        if record.billing_completed:
            for request in record.lab_request_line_ids:
                if request.status == 'requested':
                    request.write({'status': 'billed'})
                self.env['hospital.lab.processing'].create({
                    'op_id': record.id,
                    'test_id': request.test_id.id,
                    'request_line_id': request.id,
                    'status': 'pending',
                })
        return record

    def _sync_lab_request(self):
        for record in self:
            if record.lab_request_line_ids:
                lab_request = self.env['hospital.lab.request'].search([
                    ('op_id', '=', record.id)
                ], limit=1)
                if not lab_request:
                    lab_request = self.env['hospital.lab.request'].create({
                        'op_id': record.id,
                    })
                record.lab_request_line_ids.write({'request_id': lab_request.id})
            else:
                lab_request = self.env['hospital.lab.request'].search([
                    ('op_id', '=', record.id)
                ])
                if lab_request:
                    lab_request.unlink()

    def _sync_billing_invoice(self):
        if self.env.context.get('no_sync_billing'):
            return
        for record in self:
            bill = self.env['hospital.billing'].search([
                ('op_id', '=', record.id),
                ('payment_status', '=', 'draft'),
                ('billing_type', '=', 'op')
            ], limit=1)

            paid_bill = self.env['hospital.billing'].search([
                ('op_id', '=', record.id),
                ('payment_status', '=', 'paid'),
                ('billing_type', '=', 'op')
            ], limit=1)

            if paid_bill:
                continue

            lines_data = []

            if record.doctor_id and record.doctor_id.consultation_fee > 0.0:
                lines_data.append({
                    'name': f"Doctor Consultation Fee - {record.doctor_id.name}",
                    'price': record.doctor_id.consultation_fee,
                    'qty': 1,
                })

            for request_line in record.lab_request_line_ids:
                lines_data.append({
                    'name': f"Lab Test: {request_line.test_id.name}",
                    'price': request_line.test_id.price or 0.0,
                    'qty': 1,
                    'lab_line_id': request_line.id,
                })

            if not lines_data:
                if bill:
                    bill.unlink()
                continue

            if not bill:
                bill = self.env['hospital.billing'].create({
                    'op_id': record.id,
                    'billing_type': 'op',
                })

            bill.bill_line_ids.unlink()

            for line_val in lines_data:
                line_val['billing_id'] = bill.id
                self.env['hospital.billing.line'].create(line_val)

    def _sync_medicine_billing(self):
        for record in self:
            if record.status == 'completed' and record.prescription_line_ids:
                med_bill = self.env['hospital.billing'].search([
                    ('op_id', '=', record.id),
                    ('billing_type', '=', 'medicine')
                ], limit=1)
                if not med_bill:
                    med_bill = self.env['hospital.billing'].create({
                        'op_id': record.id,
                        'billing_type': 'medicine',
                        'payment_status': 'draft',
                    })
                
                if med_bill.payment_status == 'draft':
                    med_bill.bill_line_ids.unlink()
                    for line in record.prescription_line_ids:
                        self.env['hospital.billing.line'].create({
                            'billing_id': med_bill.id,
                            'name': f"Medicine: {line.medicine_id.name}",
                            'price': line.medicine_id.price or 0.0,
                            'qty': line.qty,
                            'prescription_line_id': line.id,
                        })

    def write(self, vals):
        res = super(HospitalOp, self).write(vals)
        self._sync_lab_request()
        self._sync_billing_invoice()
        self._sync_medicine_billing()
        for record in self:
            if record.billing_completed:
                for request in record.lab_request_line_ids:
                    if request.status == 'requested':
                        request.write({'status': 'billed'})
                    existing = self.env['hospital.lab.processing'].search([
                        ('request_line_id', '=', request.id)
                    ])
                    if not existing:
                        self.env['hospital.lab.processing'].create({
                            'op_id': record.id,
                            'test_id': request.test_id.id,
                            'request_line_id': request.id,
                            'status': 'pending',
                        })
        return res

    # ==========================
    # Validations
    # ==========================
    @api.constrains('doctor_id', 'patient_id')
    def _check_entities_status(self):
        for record in self:
            if record.doctor_id and record.doctor_id.status == 'inactive':
                raise ValidationError(_("Cannot register an OP visit with an inactive doctor."))
            if record.patient_id and record.patient_id.status == 'deceased':
                raise ValidationError(_("Cannot register an OP visit for a deceased patient."))

    @api.constrains('height', 'weight')
    def _check_height_weight(self):
        for record in self:
            if record.height < 0.0:
                raise ValidationError(_("Height cannot be negative."))
            if record.weight < 0.0:
                raise ValidationError(_("Weight cannot be negative."))

    @api.constrains('temperature')
    def _check_temperature(self):
        for record in self:
            if record.temperature:
                if record.temperature < 30.0 or record.temperature > 45.0:
                    raise ValidationError(_("Temperature is out of realistic range (30.0°C to 45.0°C)."))

    @api.constrains('pulse_rate', 'respiratory_rate')
    def _check_rates(self):
        for record in self:
            if record.pulse_rate < 0:
                raise ValidationError(_("Pulse rate cannot be negative."))
            if record.respiratory_rate < 0:
                raise ValidationError(_("Respiratory rate cannot be negative."))

    @api.constrains('spo2')
    def _check_spo2(self):
        for record in self:
            if record.spo2:
                if record.spo2 < 0 or record.spo2 > 100:
                    raise ValidationError(_("SpO₂ percentage must be between 0 and 100."))

    @api.constrains('pain_score')
    def _check_pain_score(self):
        for record in self:
            if record.pain_score:
                if record.pain_score < 0 or record.pain_score > 10:
                    raise ValidationError(_("Pain score must be between 0 and 10."))

    @api.constrains('blood_pressure')
    def _check_blood_pressure(self):
        bp_regex = r"^\d{2,3}/\d{2,3}$"
        for record in self:
            if record.blood_pressure:
                if not re.match(bp_regex, record.blood_pressure):
                    raise ValidationError(_("Blood pressure must be in Systolic/Diastolic format (e.g. 120/80)."))

    @api.constrains('follow_up_date')
    def _check_follow_up_date(self):
        for record in self:
            if record.follow_up_date and record.follow_up_date < fields.Date.today():
                raise ValidationError(_("Follow-up date cannot be in the past."))

    @api.constrains('doctor_id', 'registration_datetime')
    def _check_daily_op_limit(self):
        for record in self:
            if record.doctor_id and record.registration_datetime:
                reg_datetime = fields.Datetime.to_datetime(record.registration_datetime)
                start_date = reg_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = reg_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                op_count = self.search_count([
                    ('doctor_id', '=', record.doctor_id.id),
                    ('registration_datetime', '>=', fields.Datetime.to_string(start_date)),
                    ('registration_datetime', '<=', fields.Datetime.to_string(end_date)),
                    ('id', '!=', record.id)
                ])
                if op_count >= 70:
                    raise ValidationError(_("Doctor %s has reached the daily limit of 70 OP visits for this date.") % record.doctor_id.name)

