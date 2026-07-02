from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalMedicinePurchaseReturn(models.Model):
    _name = "hospital.medicine.purchase.return"
    _description = "Medicine Purchase Return"
    _order = "name desc"

    name = fields.Char(
        string="Return Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    supplier_id = fields.Many2one(
        "hospital.medicine.supplier",
        string="Supplier",
        required=True
    )
    purchase_id = fields.Many2one(
        "hospital.medicine.purchase",
        string="Purchase Order",
        domain="[('supplier_id', '=', supplier_id), ('state', '=', 'received')]"
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
    date = fields.Datetime(
        string="Return Date",
        default=fields.Datetime.now,
        required=True
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.medicine.purchase.return") or "New"
        
        record = super(HospitalMedicinePurchaseReturn, self).create(vals)
        
        # Validation & Deduction
        batch = record.batch_id
        if batch.qty_remaining < record.qty:
            raise ValidationError(_("Insufficient stock in Batch %s for this return. Available: %s, Requested: %s") % (
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
            "type": "purchase_return",
            "reference": record.name
        })
        
        return record

    @api.onchange("purchase_id")
    def _onchange_purchase_id(self):
        if self.purchase_id:
            # Domain filter for medicine
            medicines = self.purchase_id.line_ids.mapped("medicine_id")
            return {"domain": {"medicine_id": [("id", "in", medicines.ids)]}}
        return {"domain": {"medicine_id": []}}
