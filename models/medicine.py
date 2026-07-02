from odoo import models, fields

class HospitalMedicine(models.Model):
    _name = "hospital.medicine"
    _description = "Hospital Medicine"
    _order = "name"

    name = fields.Char(
        string="Medicine Name",
        required=True
    )
    code = fields.Char(
        string="Medicine Code",
        copy=False
    )
    description = fields.Text(
        string="Description"
    )
    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ],
        string="Status",
        default="active",
        required=True
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )
    price = fields.Float(
        string="Price",
        default=0.0
    )
    qty_available = fields.Integer(
        string="Quantity Available",
        default=100
    )
    reorder_level = fields.Integer(
        string="Reorder Level",
        default=10
    )
    expiry_date = fields.Date(
        string="Expiry Date"
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The medicine code must be unique!')
    ]
