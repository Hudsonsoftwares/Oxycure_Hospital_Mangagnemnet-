from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalPatientMedicineReturn(models.Model):
    _name = "hospital.patient.medicine.return"
    _description = "Patient Medicine Return"
    _order = "name desc"

    name = fields.Char(
        string="Return Number",
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
    medicine_id = fields.Many2one(
        "hospital.medicine",
        string="Medicine",
        required=True
    )
    batch_id = fields.Many2one(
        "hospital.medicine.batch",
        string="Batch",
        required=True,
        domain="[('medicine_id', '=', medicine_id)]"
    )
    qty = fields.Integer(
        string="Returned Quantity",
        required=True,
        default=1
    )
    reason = fields.Text(
        string="Reason for Return",
        required=True
    )
    refund_amount = fields.Float(
        string="Refund Amount",
        default=0.0
    )
    date = fields.Datetime(
        string="Return Date",
        default=fields.Datetime.now,
        required=True
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.patient.medicine.return") or "New"
        
        record = super(HospitalPatientMedicineReturn, self).create(vals)
        
        # Add stock back to batch
        batch = record.batch_id
        batch.write({
            "qty_remaining": batch.qty_remaining + record.qty
        })
        
        # Log stock movement
        self.env["hospital.stock.movement"].create({
            "medicine_id": record.medicine_id.id,
            "batch_id": batch.id,
            "qty": record.qty,
            "type": "patient_return",
            "reference": record.name
        })
        
        return record

    @api.onchange("batch_id")
    def _onchange_batch_id(self):
        if self.batch_id and self.medicine_id:
            # Set default refund amount based on batch selling price * quantity
            self.refund_amount = self.batch_id.selling_price * self.qty
