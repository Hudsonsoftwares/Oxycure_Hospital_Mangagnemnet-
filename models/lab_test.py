from odoo import models, fields

class HospitalLabTest(models.Model):
    _name = "hospital.lab.test"
    _description = "Laboratory Test"
    _order = "name"

    name = fields.Char(
        string="Test Name",
        required=True
    )
    code = fields.Char(
        string="Test Code",
        copy=False
    )
    price = fields.Float(
        string="Price"
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

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The laboratory test code must be unique!')
    ]
