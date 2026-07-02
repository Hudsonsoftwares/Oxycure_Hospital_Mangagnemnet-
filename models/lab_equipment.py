from odoo import models, fields

class HospitalLabEquipment(models.Model):
    _name = "hospital.lab.equipment"
    _description = "Laboratory Equipment"
    _order = "name"

    name = fields.Char(
        string="Equipment Name",
        required=True
    )
    test_ids = fields.Many2many(
        "hospital.lab.test",
        string="Lab Tests",
        help="Laboratory tests supported by this equipment"
    )
    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ],
        string="Status",
        default="active",
        required=True
    )
