from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalAppointment(models.Model):
    _name = "hospital.appointment"
    _description = "Hospital Appointment"
    _rec_name = "appointment_no"
    _order = "appointment_date desc, appointment_time desc"

    appointment_no = fields.Char(
        string="Appointment No",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )

    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        required=True
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

    appointment_date = fields.Date(
        string="Appointment Date",
        default=fields.Date.today,
        required=True
    )

    appointment_time = fields.Datetime(
        string="Appointment Time",
        default=fields.Datetime.now,
        required=True
    )

    visit_type = fields.Selection([
        ('new', 'New'),
        ('follow_up', 'Follow-up'),
        ('emergency', 'Emergency')
    ],
        string="Visit Type",
        default="new",
        required=True
    )

    status = fields.Selection([
        ('booked', 'Booked'),
        ('checked_in', 'Checked In'),
        ('consultation', 'In Consultation'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show')
    ],
        string="Status",
        default="booked",
        required=True
    )

    token_number = fields.Integer(
        string="Token Number"
    )

    chief_complaint = fields.Text(
        string="Chief Complaint"
    )

    notes = fields.Text(
        string="Notes"
    )

    @api.model
    def create(self, vals):
        if vals.get("appointment_no", "New") == "New":
            vals["appointment_no"] = self.env["ir.sequence"].next_by_code(
                "hospital.appointment"
            ) or "New"

        # Auto-generate Token Number per doctor and appointment date
        doctor_id = vals.get("doctor_id")
        appointment_date = vals.get("appointment_date") or fields.Date.today()
        if doctor_id and not vals.get("token_number"):
            domain = [
                ('doctor_id', '=', doctor_id),
                ('appointment_date', '=', appointment_date)
            ]
            last_appointment = self.search(domain, order="token_number desc", limit=1)
            next_token = (last_appointment.token_number or 0) + 1
            vals["token_number"] = next_token

        record = super().create(vals)
        if record.doctor_id:
            bill = self.env['hospital.billing'].create({
                'appointment_id': record.id,
                'billing_type': 'op',
                'payment_status': 'draft',
            })
            self.env['hospital.billing.line'].create({
                'billing_id': bill.id,
                'name': f"Doctor Consultation Fee - {record.doctor_id.name}",
                'price': record.doctor_id.consultation_fee or 0.0,
                'qty': 1,
            })
        return record

    def write(self, vals):
        res = super(HospitalAppointment, self).write(vals)
        if 'doctor_id' in vals:
            for record in self:
                draft_bill = self.env['hospital.billing'].search([
                    ('appointment_id', '=', record.id),
                    ('payment_status', '=', 'draft'),
                    ('billing_type', '=', 'op')
                ], limit=1)
                if draft_bill:
                    draft_bill.bill_line_ids.unlink()
                    if record.doctor_id:
                        self.env['hospital.billing.line'].create({
                            'billing_id': draft_bill.id,
                            'name': f"Doctor Consultation Fee - {record.doctor_id.name}",
                            'price': record.doctor_id.consultation_fee or 0.0,
                            'qty': 1,
                        })
        return res

    # ==========================
    # Validations
    # ==========================
    @api.constrains('appointment_date')
    def _check_appointment_date(self):
        for record in self:
            if record.appointment_date and record.status == 'booked':
                if record.appointment_date < fields.Date.today():
                    raise ValidationError(_("The appointment date cannot be set in the past for new bookings."))

    @api.constrains('doctor_id', 'patient_id')
    def _check_entities_status(self):
        for record in self:
            if record.doctor_id and record.doctor_id.status == 'inactive':
                raise ValidationError(_("Cannot book an appointment with an inactive doctor."))
            if record.patient_id and record.patient_id.status == 'deceased':
                raise ValidationError(_("Cannot book an appointment for a deceased patient."))

    @api.constrains('token_number')
    def _check_token_number(self):
        for record in self:
            if record.token_number and record.token_number <= 0:
                raise ValidationError(_("Token number must be a positive integer."))
