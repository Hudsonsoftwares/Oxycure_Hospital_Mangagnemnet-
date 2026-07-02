from odoo import models, fields, api

class HospitalMedicine(models.Model):
    _name = "hospital.medicine"
    _description = "Hospital Medicine Master"
    _order = "name"

    name = fields.Char(
        string="Medicine Name",
        required=True
    )
    code = fields.Char(
        string="Medicine Code",
        copy=False
    )
    generic_name = fields.Char(
        string="Generic Name"
    )
    brand_name = fields.Char(
        string="Brand Name"
    )
    category_id = fields.Many2one(
        "hospital.medicine.category",
        string="Category"
    )
    manufacturer = fields.Char(
        string="Manufacturer"
    )
    dosage_form = fields.Selection([
        ("tablet", "Tablet"),
        ("capsule", "Capsule"),
        ("syrup", "Syrup"),
        ("injection", "Injection"),
        ("ointment", "Ointment"),
        ("suspension", "Suspension"),
        ("inhaler", "Inhaler"),
        ("other", "Other")
    ],
        string="Dosage Form",
        default="tablet"
    )
    strength = fields.Char(
        string="Strength",
        placeholder="e.g. 500 mg, 10 ml"
    )
    unit = fields.Char(
        string="Unit of Measure",
        placeholder="e.g. Strip, Bottle, Box"
    )
    barcode = fields.Char(
        string="Barcode"
    )
    hsn_code = fields.Char(
        string="HSN Code"
    )
    gst_rate = fields.Selection([
        ("0", "0%"),
        ("5", "5%"),
        ("12", "12%"),
        ("18", "18%"),
        ("28", "28%")
    ],
        string="GST %",
        default="12"
    )
    price = fields.Float(
        string="Selling Price",
        default=0.0
    )
    selling_price = fields.Float(
        string="Selling Price Alias",
        related="price",
        readonly=False
    )
    purchase_price = fields.Float(
        string="Purchase Price",
        default=0.0
    )
    minimum_stock = fields.Integer(
        string="Minimum Stock",
        default=10
    )
    reorder_level = fields.Integer(
        string="Reorder Level",
        default=15
    )
    requires_prescription = fields.Boolean(
        string="Requires Prescription",
        default=False
    )
    storage_condition = fields.Char(
        string="Storage Condition",
        placeholder="e.g. Keep in a cool dry place"
    )
    status = fields.Selection([
        ("active", "Active"),
        ("inactive", "Inactive")
    ],
        string="Status",
        default="active",
        required=True
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )
    image = fields.Binary(
        string="Image"
    )
    description = fields.Text(
        string="Description"
    )

    batch_ids = fields.One2many(
        "hospital.medicine.batch",
        "medicine_id",
        string="Batches"
    )

    qty_available = fields.Integer(
        string="Quantity Available",
        compute="_compute_qty_available",
        store=True
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        compute="_compute_expiry_date",
        store=True
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "The medicine code must be unique!")
    ]

    @api.depends("batch_ids.qty_remaining")
    def _compute_qty_available(self):
        for record in self:
            record.qty_available = sum(record.batch_ids.mapped("qty_remaining"))

    @api.depends("batch_ids.expiry_date", "batch_ids.qty_remaining")
    def _compute_expiry_date(self):
        for record in self:
            # Look at active batches with quantity > 0
            active_batches = record.batch_ids.filtered(lambda b: b.qty_remaining > 0 and b.expiry_date)
            if active_batches:
                record.expiry_date = min(active_batches.mapped("expiry_date"))
            else:
                # If no stock, take min of all batches or False
                all_batches = record.batch_ids.filtered(lambda b: b.expiry_date)
                record.expiry_date = min(all_batches.mapped("expiry_date")) if all_batches else False
