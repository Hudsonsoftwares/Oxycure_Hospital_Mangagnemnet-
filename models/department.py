from odoo import models, fields, api, _

class HospitalDepartment(models.Model):
    _name = "hospital.department"
    _description = "Hospital Department"
    _rec_name = "name"

    department_id = fields.Char(
        string="Department ID",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )

    name = fields.Char(
        string="Department Name",
        required=True
    )

    code = fields.Char(
        string="Department Code",
        required=True
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

    @api.model
    def create(self, vals):
        if vals.get("department_id", "New") == "New":
            vals["department_id"] = self.env["ir.sequence"].next_by_code(
                "hospital.department"
            ) or "New"
        return super().create(vals)
