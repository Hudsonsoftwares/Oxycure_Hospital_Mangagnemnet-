from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalStockAdjustment(models.Model):
    _name = "hospital.stock.adjustment"
    _description = "Stock Adjustment"
    _order = "name desc"

    name = fields.Char(
        string="Adjustment Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
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
    old_qty = fields.Integer(
        string="System Quantity",
        readonly=True
    )
    new_qty = fields.Integer(
        string="Physical Quantity",
        required=True
    )
    reason = fields.Text(
        string="Reason for Adjustment",
        required=True
    )
    date = fields.Datetime(
        string="Adjustment Date",
        default=fields.Datetime.now,
        required=True
    )

    @api.onchange("batch_id")
    def _onchange_batch_id(self):
        if self.batch_id:
            self.old_qty = self.batch_id.qty_remaining

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.stock.adjustment") or "New"
        
        # Populate old_qty if not set
        batch_id = vals.get("batch_id")
        if batch_id and not vals.get("old_qty"):
            batch = self.env["hospital.medicine.batch"].browse(batch_id)
            vals["old_qty"] = batch.qty_remaining

        if vals.get("new_qty", 0) < 0:
            raise ValidationError(_("Physical quantity cannot be negative!"))

        record = super(HospitalStockAdjustment, self).create(vals)
        
        # Update batch stock
        delta = record.new_qty - record.old_qty
        record.batch_id.write({
            "qty_remaining": record.new_qty
        })
        
        # Log stock movement
        self.env["hospital.stock.movement"].create({
            "medicine_id": record.medicine_id.id,
            "batch_id": record.batch_id.id,
            "qty": delta,
            "type": "adjustment",
            "reference": record.name
        })
        
        return record
