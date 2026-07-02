from odoo import models, fields

class HospitalStockMovement(models.Model):
    _name = "hospital.stock.movement"
    _description = "Stock Movement Audit Log"
    _order = "date desc, id desc"

    medicine_id = fields.Many2one(
        "hospital.medicine",
        string="Medicine",
        required=True,
        ondelete="cascade"
    )
    batch_id = fields.Many2one(
        "hospital.medicine.batch",
        string="Batch",
        required=True,
        ondelete="cascade"
    )
    date = fields.Datetime(
        string="Movement Date",
        default=fields.Datetime.now,
        required=True
    )
    qty = fields.Integer(
        string="Quantity (Delta)",
        required=True,
        help="Positive for stock additions, negative for stock reductions."
    )
    type = fields.Selection([
        ("purchase", "Purchase Receipt"),
        ("purchase_return", "Supplier Return"),
        ("patient_return", "Patient Return"),
        ("sale", "Counter Sale"),
        ("dispense", "Prescription Dispensing"),
        ("adjustment", "Stock Adjustment"),
        ("disposal", "Disposal (Expired)")
    ],
        string="Movement Type",
        required=True
    )
    reference = fields.Char(
        string="Source Reference",
        help="Document reference e.g. PO0001, Return No, Dispense No, etc."
    )
    user_id = fields.Many2one(
        "res.users",
        string="Performed By",
        default=lambda self: self.env.user,
        required=True
    )
