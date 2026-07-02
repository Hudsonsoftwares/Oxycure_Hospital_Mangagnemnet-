from odoo import models, fields, api

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
        default=0
    )
    instructions = fields.Char(
        string="Instructions",
        placeholder="e.g. After Food"
    )
    pharmacist_instructions = fields.Char(
        string="Pharmacist Instructions",
        compute="_compute_pharmacist_instructions"
    )

    def _compute_pharmacist_instructions(self):
        for record in self:
            req_line = self.env['hospital.pharmacy.request.line'].search([
                ('prescription_line_id', '=', record.id)
            ], limit=1)
            record.pharmacist_instructions = req_line.pharmacist_instructions if req_line else False
