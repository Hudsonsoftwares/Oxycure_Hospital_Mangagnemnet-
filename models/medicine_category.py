from odoo import models, fields, api

class HospitalMedicineCategory(models.Model):
    _name = "hospital.medicine.category"
    _description = "Medicine Category"
    _rec_name = "complete_name"
    _order = "complete_name"

    name = fields.Char(
        string="Category Name",
        required=True
    )
    parent_id = fields.Many2one(
        "hospital.medicine.category",
        string="Parent Category",
        ondelete="cascade"
    )
    complete_name = fields.Char(
        string="Complete Name",
        compute="_compute_complete_name",
        store=True
    )
    description = fields.Text(
        string="Description"
    )

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = f"{category.parent_id.complete_name} / {category.name}"
            else:
                category.complete_name = category.name
