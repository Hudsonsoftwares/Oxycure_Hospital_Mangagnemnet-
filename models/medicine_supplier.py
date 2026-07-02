from odoo import models, fields

class HospitalMedicineSupplier(models.Model):
    _name = "hospital.medicine.supplier"
    _description = "Medicine Supplier"
    _order = "name"

    name = fields.Char(
        string="Supplier Name",
        required=True
    )
    code = fields.Char(
        string="Supplier Code",
        copy=False
    )
    phone = fields.Char(
        string="Phone"
    )
    email = fields.Char(
        string="Email"
    )
    address = fields.Text(
        string="Address"
    )
    gstin = fields.Char(
        string="GSTIN (GST Number)"
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "The supplier code must be unique!")
    ]
