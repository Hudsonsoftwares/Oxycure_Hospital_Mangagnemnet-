from odoo import models, fields, api

class HospitalLabRequest(models.Model):
    _name = "hospital.lab.request"
    _description = "Laboratory Request"
    _rec_name = "name"
    _order = "id desc"

    name = fields.Char(
        string="Request Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    op_id = fields.Many2one(
        "hospital.op",
        string="OP Visit",
        required=True,
        ondelete="cascade"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        related="op_id.patient_id",
        store=True,
        string="Patient",
        readonly=True
    )
    patient_gender = fields.Selection(
        related="patient_id.gender",
        string="Gender",
        readonly=True
    )
    patient_age = fields.Integer(
        related="patient_id.age",
        string="Age",
        readonly=True
    )
    patient_blood_group = fields.Selection(
        related="patient_id.blood_group",
        string="Blood Group",
        readonly=True
    )
    doctor_id = fields.Many2one(
        "hospital.doctor",
        related="op_id.doctor_id",
        store=True,
        string="Doctor",
        readonly=True
    )
    request_datetime = fields.Datetime(
        string="Request Date & Time",
        default=fields.Datetime.now,
        required=True
    )
    line_ids = fields.One2many(
        "hospital.lab.request.line",
        "request_id",
        string="Requested Tests"
    )
    status = fields.Selection([
        ('requested', 'Requested'),
        ('billed', 'Billed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ],
        string="Status",
        default="requested",
        compute="_compute_status",
        store=True
    )

    @api.depends('line_ids.status')
    def _compute_status(self):
        for record in self:
            if not record.line_ids:
                record.status = 'requested'
            elif all(line.status == 'completed' for line in record.line_ids):
                record.status = 'completed'
            elif all(line.status == 'cancelled' for line in record.line_ids):
                record.status = 'cancelled'
            elif any(line.status == 'billed' for line in record.line_ids):
                record.status = 'billed'
            else:
                record.status = 'requested'

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.lab.request") or "New"
        return super(HospitalLabRequest, self).create(vals)


class HospitalLabRequestLine(models.Model):
    _name = "hospital.lab.request.line"
    _description = "Laboratory Request Line"

    op_id = fields.Many2one(
        "hospital.op",
        string="OP Visit",
        ondelete="cascade",
        required=True
    )
    request_id = fields.Many2one(
        "hospital.lab.request",
        string="Lab Request",
        ondelete="cascade"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        related="op_id.patient_id",
        store=True,
        string="Patient",
        readonly=True
    )
    test_id = fields.Many2one(
        "hospital.lab.test",
        string="Lab Test / Service",
        required=True,
        domain="[('status', '=', 'active')]"
    )
    notes = fields.Char(
        string="Instructions"
    )
    status = fields.Selection([
        ('requested', 'Requested'),
        ('billed', 'Billed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ],
        string="Status",
        default="requested",
        required=True
    )
    result_pdf = fields.Binary(
        string="Lab Report PDF",
        readonly=True
    )
    result_pdf_name = fields.Char(
        string="PDF Filename",
        readonly=True
    )
    ai_summary = fields.Text(
        string="AI Summary",
        readonly=True
    )
