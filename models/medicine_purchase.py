from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HospitalMedicinePurchase(models.Model):
    _name = "hospital.medicine.purchase"
    _description = "Medicine Purchase Order"
    _order = "name desc"

    name = fields.Char(
        string="Purchase Order",
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
    purchase_date = fields.Date(
        string="Purchase Date",
        default=fields.Date.context_today,
        required=True
    )
    state = fields.Selection([
        ("draft", "Draft"),
        ("received", "Received"),
        ("cancelled", "Cancelled")
    ],
        string="Status",
        default="draft",
        required=True,
        readonly=True
    )
    line_ids = fields.One2many(
        "hospital.medicine.purchase.line",
        "purchase_id",
        string="Purchase Lines"
    )
    amount_total = fields.Float(
        string="Total Amount",
        compute="_compute_amount_total",
        store=True
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.medicine.purchase") or "New"
        return super(HospitalMedicinePurchase, self).create(vals)

    @api.depends("line_ids.subtotal")
    def _compute_amount_total(self):
        for record in self:
            record.amount_total = sum(record.line_ids.mapped("subtotal"))

    def action_receive(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft purchase orders can be received."))
            if not record.line_ids:
                raise UserError(_("Please add lines to receive."))
            
            for line in record.line_ids:
                # Find or create batch
                batch = self.env["hospital.medicine.batch"].search([
                    ("name", "=", line.batch_number),
                    ("medicine_id", "=", line.medicine_id.id)
                ], limit=1)
                
                if batch:
                    batch.write({
                        "qty_original": batch.qty_original + line.qty,
                        "qty_remaining": batch.qty_remaining + line.qty,
                        "purchase_price": line.purchase_price,
                        "selling_price": line.selling_price,
                        "expiry_date": line.expiry_date,
                        "manufacturing_date": line.manufacturing_date
                    })
                else:
                    batch = self.env["hospital.medicine.batch"].create({
                        "name": line.batch_number,
                        "medicine_id": line.medicine_id.id,
                        "expiry_date": line.expiry_date,
                        "manufacturing_date": line.manufacturing_date,
                        "qty_original": line.qty,
                        "qty_remaining": line.qty,
                        "purchase_price": line.purchase_price,
                        "selling_price": line.selling_price
                    })

                # Create stock movement log
                self.env["hospital.stock.movement"].create({
                    "medicine_id": line.medicine_id.id,
                    "batch_id": batch.id,
                    "qty": line.qty,
                    "type": "purchase",
                    "reference": record.name
                })
            
            record.write({"state": "received"})

    def action_cancel(self):
        for record in self:
            if record.state == "received":
                raise UserError(_("Cannot cancel a purchase order that has already been received."))
            record.write({"state": "cancelled"})


class HospitalMedicinePurchaseLine(models.Model):
    _name = "hospital.medicine.purchase.line"
    _description = "Purchase Order Line"

    purchase_id = fields.Many2one(
        "hospital.medicine.purchase",
        string="Purchase Order",
        ondelete="cascade",
        required=True
    )
    medicine_id = fields.Many2one(
        "hospital.medicine",
        string="Medicine",
        required=True
    )
    qty = fields.Integer(
        string="Quantity",
        required=True,
        default=1
    )
    purchase_price = fields.Float(
        string="Purchase Price",
        required=True
    )
    selling_price = fields.Float(
        string="Selling Price",
        required=True
    )
    batch_number = fields.Char(
        string="Batch Number",
        required=True
    )
    manufacturing_date = fields.Date(
        string="Manufacturing Date"
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        required=True
    )
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True
    )

    @api.depends("qty", "purchase_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.purchase_price

    @api.onchange("medicine_id")
    def _onchange_medicine_id(self):
        if self.medicine_id:
            self.purchase_price = self.medicine_id.purchase_price
            self.selling_price = self.medicine_id.price
