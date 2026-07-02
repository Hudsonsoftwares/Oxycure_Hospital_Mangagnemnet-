from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalMedicineBatch(models.Model):
    _name = "hospital.medicine.batch"
    _description = "Medicine Batch"
    _order = "expiry_date, name"

    name = fields.Char(
        string="Batch Number",
        required=True
    )
    medicine_id = fields.Many2one(
        "hospital.medicine",
        string="Medicine",
        required=True,
        ondelete="cascade"
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        required=True
    )
    manufacturing_date = fields.Date(
        string="Manufacturing Date"
    )
    qty_original = fields.Integer(
        string="Original Quantity",
        default=0
    )
    qty_remaining = fields.Integer(
        string="Remaining Quantity",
        default=0
    )
    purchase_price = fields.Float(
        string="Purchase Price",
        default=0.0
    )
    selling_price = fields.Float(
        string="Selling Price",
        default=0.0
    )

    _sql_constraints = [
        ("qty_remaining_non_negative", "CHECK(qty_remaining >= 0)", "The remaining quantity of a batch cannot be negative!"),
        ("batch_unique_per_medicine", "unique(name, medicine_id)", "The batch number must be unique per medicine!")
    ]

    @api.constrains("expiry_date", "manufacturing_date")
    def _check_dates(self):
        for record in self:
            if record.manufacturing_date and record.expiry_date and record.manufacturing_date > record.expiry_date:
                raise ValidationError(_("The expiry date must be after the manufacturing date!"))
