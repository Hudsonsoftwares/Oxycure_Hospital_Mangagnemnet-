from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalExpiredDisposal(models.Model):
    _name = "hospital.expired.disposal"
    _description = "Expired Medicine Disposal"
    _order = "name desc"

    name = fields.Char(
        string="Disposal Number",
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
    qty = fields.Integer(
        string="Disposed Quantity",
        required=True,
        default=1
    )
    disposed_by_id = fields.Many2one(
        "res.users",
        string="Disposed By",
        default=lambda self: self.env.user,
        required=True
    )
    reason = fields.Text(
        string="Reason for Disposal",
        required=True
    )
    date = fields.Datetime(
        string="Disposal Date",
        default=fields.Datetime.now,
        required=True
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.expired.disposal") or "New"
        
        record = super(HospitalExpiredDisposal, self).create(vals)
        
        # Validation & Deduction
        batch = record.batch_id
        if batch.qty_remaining < record.qty:
            raise ValidationError(_("Insufficient stock in Batch %s for disposal. Available: %s, Requested: %s") % (
                batch.name, batch.qty_remaining, record.qty
            ))
        
        # Deduct stock
        batch.write({
            "qty_remaining": batch.qty_remaining - record.qty
        })
        
        # Log stock movement
        self.env["hospital.stock.movement"].create({
            "medicine_id": record.medicine_id.id,
            "batch_id": batch.id,
            "qty": -record.qty,
            "type": "disposal",
            "reference": record.name
        })
        
        return record

    @api.onchange("medicine_id")
    def _onchange_medicine_id(self):
        # Auto-suggest expired or near expired batches if any
        if self.medicine_id:
            today = fields.Date.today()
            expired_batches = self.env["hospital.medicine.batch"].search([
                ("medicine_id", "=", self.medicine_id.id),
                ("qty_remaining", ">", 0),
                ("expiry_date", "<=", today)
            ])
            if expired_batches:
                self.batch_id = expired_batches[0].id
                self.qty = expired_batches[0].qty_remaining
