from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class HospitalPharmacySale(models.Model):
    _name = "hospital.pharmacy.sale"
    _description = "Pharmacy Counter Sale"
    _order = "name desc"

    name = fields.Char(
        string="Invoice / Sale Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient"
    )
    sale_date = fields.Datetime(
        string="Sale Date",
        default=fields.Datetime.now,
        required=True
    )
    state = fields.Selection([
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancelled", "Cancelled")
    ],
        string="Status",
        default="draft",
        required=True,
        readonly=True
    )
    line_ids = fields.One2many(
        "hospital.pharmacy.sale.line",
        "sale_id",
        string="Sale Lines"
    )
    amount_total = fields.Float(
        string="Total Amount",
        compute="_compute_amount_total",
        store=True
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.pharmacy.sale") or "New"
        return super(HospitalPharmacySale, self).create(vals)

    @api.depends("line_ids.subtotal")
    def _compute_amount_total(self):
        for record in self:
            record.amount_total = sum(record.line_ids.mapped("subtotal"))

    def action_post(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft sales can be posted."))
            if not record.line_ids:
                raise UserError(_("Please add lines before posting."))
            
            for line in record.line_ids:
                batch = line.batch_id
                if not batch:
                    raise ValidationError(_("Please select a batch for medicine %s") % line.medicine_id.name)
                
                if batch.qty_remaining < line.qty:
                    raise ValidationError(_("Insufficient stock in Batch %s for medicine %s. Available: %s, Requested: %s") % (
                        batch.name, line.medicine_id.name, batch.qty_remaining, line.qty
                    ))
                
                # Deduct stock
                batch.write({
                    "qty_remaining": batch.qty_remaining - line.qty
                })

                # Create stock movement log
                self.env["hospital.stock.movement"].create({
                    "medicine_id": line.medicine_id.id,
                    "batch_id": batch.id,
                    "qty": -line.qty,
                    "type": "sale",
                    "reference": record.name
                })
            
            record.write({"state": "posted"})

    def action_cancel(self):
        for record in self:
            if record.state == "posted":
                raise UserError(_("Cannot cancel a posted sale. Please process a Patient Return instead."))
            record.write({"state": "cancelled"})


class HospitalPharmacySaleLine(models.Model):
    _name = "hospital.pharmacy.sale.line"
    _description = "Pharmacy Sale Line"

    sale_id = fields.Many2one(
        "hospital.pharmacy.sale",
        string="Pharmacy Sale",
        ondelete="cascade",
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
        required=True
    )
    qty = fields.Integer(
        string="Quantity",
        required=True,
        default=1
    )
    price_unit = fields.Float(
        string="Unit Price",
        required=True
    )
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True
    )

    @api.depends("qty", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.price_unit

    @api.onchange("medicine_id")
    def _onchange_medicine_id(self):
        if self.medicine_id:
            # Auto-suggest batch with stock using FEFO (nearest expiry)
            today = fields.Date.today()
            batches = self.env["hospital.medicine.batch"].search([
                ("medicine_id", "=", self.medicine_id.id),
                ("qty_remaining", ">", 0),
                ("expiry_date", ">=", today)
            ], order="expiry_date asc, name asc", limit=1)
            
            if batches:
                self.batch_id = batches[0].id
                self.price_unit = batches[0].selling_price
            else:
                self.price_unit = self.medicine_id.price
            
            return {"domain": {"batch_id": [("medicine_id", "=", self.medicine_id.id), ("qty_remaining", ">", 0)]}}
        return {"domain": {"batch_id": []}}

    @api.onchange("batch_id")
    def _onchange_batch_id(self):
        if self.batch_id:
            self.price_unit = self.batch_id.selling_price
