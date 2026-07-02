from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalBilling(models.Model):
    _name = "hospital.billing"
    _description = "Hospital Billing / Invoice"
    _rec_name = "name"
    _order = "id desc"

    name = fields.Char(
        string="Invoice Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    op_id = fields.Many2one(
        "hospital.op",
        string="OP Visit",
        required=False,
        ondelete="cascade"
    )
    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Appointment",
        ondelete="set null"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        compute="_compute_patient_doctor",
        store=True,
        readonly=True
    )
    doctor_id = fields.Many2one(
        "hospital.doctor",
        string="Doctor",
        compute="_compute_patient_doctor",
        store=True,
        readonly=True
    )
    billing_date = fields.Date(
        string="Billing Date",
        default=fields.Date.today,
        required=True
    )
    payment_status = fields.Selection([
        ('draft', 'Draft / Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ],
        string="Status",
        default="draft",
        required=True
    )
    billing_type = fields.Selection([
        ('op', 'OP Consultation & Labs'),
        ('medicine', 'Pharmacy / Medicine')
    ],
        string="Billing Type",
        default="op",
        required=True
    )
    bill_line_ids = fields.One2many(
        "hospital.billing.line",
        "billing_id",
        string="Bill Lines"
    )
    amount_total = fields.Float(
        string="Total Amount",
        compute="_compute_amounts",
        store=True
    )

    @api.depends('op_id.patient_id', 'op_id.doctor_id', 'appointment_id.patient_id', 'appointment_id.doctor_id')
    def _compute_patient_doctor(self):
        for record in self:
            if record.op_id:
                record.patient_id = record.op_id.patient_id
                record.doctor_id = record.op_id.doctor_id
            elif record.appointment_id:
                record.patient_id = record.appointment_id.patient_id
                record.doctor_id = record.appointment_id.doctor_id
            else:
                record.patient_id = False
                record.doctor_id = False

    @api.depends('bill_line_ids.subtotal')
    def _compute_amounts(self):
        for record in self:
            record.amount_total = sum(line.subtotal for line in record.bill_line_ids)

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.billing") or "New"
        return super(HospitalBilling, self).create(vals)

    def action_pay_bill(self):
        for record in self:
            if record.payment_status == 'draft':
                record.write({'payment_status': 'paid'})

    def action_print_invoice(self):
        self.ensure_one()
        return self.env.ref('hospital_management.action_report_hospital_billing').report_action(self)

    def action_send_email(self):
        self.ensure_one()
        if not self.patient_id.email:
            raise ValidationError(_("The patient does not have an email address configured. Please update their profile first."))
        template = self.env.ref('hospital_management.email_template_hospital_billing', raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)
        return True

    def write(self, vals):
        res = super(HospitalBilling, self).write(vals)
        if 'payment_status' in vals and vals['payment_status'] == 'paid':
            for record in self:
                if record.billing_type == 'op':
                    if record.op_id:
                        record.op_id.write({'billing_completed': True})
                        for line in record.bill_line_ids:
                            if line.lab_line_id:
                                line.lab_line_id.write({'status': 'billed'})
                                existing = self.env['hospital.lab.processing'].search([
                                    ('request_line_id', '=', line.lab_line_id.id)
                                ])
                                if not existing:
                                    self.env['hospital.lab.processing'].create({
                                        'op_id': record.op_id.id,
                                        'test_id': line.lab_line_id.test_id.id,
                                        'request_line_id': line.lab_line_id.id,
                                        'status': 'pending',
                                    })
                    elif record.appointment_id:
                        existing_op = self.env['hospital.op'].search([
                            ('appointment_id', '=', record.appointment_id.id)
                        ], limit=1)
                        if not existing_op:
                            op = self.env['hospital.op'].with_context(no_sync_billing=True).create({
                                'appointment_id': record.appointment_id.id,
                                'patient_id': record.appointment_id.patient_id.id,
                                'doctor_id': record.appointment_id.doctor_id.id,
                                'visit_type': record.appointment_id.visit_type,
                                'token_number': record.appointment_id.token_number,
                                'chief_complaint': record.appointment_id.chief_complaint,
                                'status': 'checked_in',
                                'billing_completed': True,
                            })
                            # Use super to avoid triggering write logic recursively
                            super(HospitalBilling, record).write({'op_id': op.id})
                            record.appointment_id.write({'status': 'checked_in'})
                elif record.billing_type == 'medicine':
                    existing_request = self.env['hospital.pharmacy.request'].search([
                        ('billing_id', '=', record.id)
                    ], limit=1)
                    if not existing_request:
                        pharmacy_request = self.env['hospital.pharmacy.request'].create({
                            'op_id': record.op_id.id,
                            'billing_id': record.id,
                            'status': 'pending',
                        })
                        for line in record.bill_line_ids:
                            if line.prescription_line_id:
                                self.env['hospital.pharmacy.request.line'].create({
                                    'request_id': pharmacy_request.id,
                                    'medicine_id': line.prescription_line_id.medicine_id.id,
                                    'qty': line.qty,
                                    'dosage': line.prescription_line_id.dosage,
                                    'duration': line.prescription_line_id.duration,
                                    'instructions': line.prescription_line_id.instructions,
                                })
        return res


class HospitalBillingLine(models.Model):
    _name = "hospital.billing.line"
    _description = "Billing Line Item"

    billing_id = fields.Many2one(
        "hospital.billing",
        string="Billing Invoice",
        required=True,
        ondelete="cascade"
    )
    name = fields.Char(
        string="Description",
        required=True
    )
    price = fields.Float(
        string="Price / Fee",
        required=True
    )
    qty = fields.Integer(
        string="Quantity",
        default=1,
        required=True
    )
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True
    )
    lab_line_id = fields.Many2one(
        "hospital.lab.request.line",
        string="Lab Test Reference",
        ondelete="set null"
    )
    prescription_line_id = fields.Many2one(
        "hospital.prescription.line",
        string="Prescription Reference",
        ondelete="set null"
    )

    @api.depends('price', 'qty')
    def _compute_subtotal(self):
        for record in self:
            record.subtotal = record.price * record.qty
