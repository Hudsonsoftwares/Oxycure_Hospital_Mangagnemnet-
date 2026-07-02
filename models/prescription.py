from odoo import models, fields

class HospitalPrescriptionLine(models.Model):
    _name = "hospital.prescription.line"
    _description = "Prescription Line"

    op_id = fields.Many2one(
        "hospital.op",
        string="OP Visit",
        ondelete="cascade",
        required=True
    )
    medicine_id = fields.Many2one(
        "hospital.medicine",
        string="Medicine",
        required=True,
        domain="[('status', '=', 'active')]"
    )
    dosage = fields.Char(
        string="Dosage",
        required=True,
        placeholder="e.g. 1-0-1"
    )
    duration = fields.Char(
        string="Duration",
        required=True,
        placeholder="e.g. 5 days"
    )
    qty = fields.Integer(
        string="Qty",
        default=1,
        required=True
    )
    instructions = fields.Char(
        string="Instructions",
        placeholder="e.g. After Food"
    )
