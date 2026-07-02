from odoo import models, fields, api, _

class HospitalPharmacyRequest(models.Model):
    _name = "hospital.pharmacy.request"
    _description = "Pharmacy Dispensing Request"
    _rec_name = "name"
    _order = "id desc"

    name = fields.Char(
        string="Request Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    op_id = fields.Many2one(
        "hospital.op",
        string="OP Visit",
        required=True,
        ondelete="cascade"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        related="op_id.patient_id",
        store=True,
        string="Patient",
        readonly=True
    )
    doctor_id = fields.Many2one(
        "hospital.doctor",
        related="op_id.doctor_id",
        store=True,
        string="Doctor",
        readonly=True
    )
    billing_id = fields.Many2one(
        "hospital.billing",
        string="Billing Invoice",
        required=False,
        ondelete="cascade"
    )
    request_datetime = fields.Datetime(
        string="Request Date & Time",
        default=fields.Datetime.now,
        required=True
    )
    status = fields.Selection([
        ('draft', 'Draft (Pharmacist sets Qty)'),
        ('to_pay', 'Pending Payment'),
        ('paid', 'Paid / Ready to Dispense'),
        ('dispensed', 'Dispensed / Completed'),
        ('cancelled', 'Cancelled')
    ],
        string="Status",
        default="draft",
        required=True
    )
    line_ids = fields.One2many(
        "hospital.pharmacy.request.line",
        "request_id",
        string="Requested Medicines"
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.pharmacy.request") or "New"
        return super(HospitalPharmacyRequest, self).create(vals)

    def action_send_to_billing(self):
        from odoo.exceptions import UserError
        for record in self:
            if record.status != 'draft':
                continue
            for line in record.line_ids:
                if line.qty <= 0:
                    raise UserError(_("Please set a quantity greater than 0 for all medicines."))
            
            # Create draft billing invoice
            bill = self.env['hospital.billing'].create({
                'op_id': record.op_id.id,
                'billing_type': 'medicine',
                'payment_status': 'draft',
            })
            for line in record.line_ids:
                self.env['hospital.billing.line'].create({
                    'billing_id': bill.id,
                    'name': f"Medicine: {line.medicine_id.name}",
                    'price': line.medicine_id.price or 0.0,
                    'qty': line.qty,
                    'prescription_line_id': line.prescription_line_id.id if line.prescription_line_id else False,
                })
            
            record.write({
                'billing_id': bill.id,
                'status': 'to_pay'
            })

    def action_dispense(self):
        from odoo.exceptions import ValidationError, UserError
        for record in self:
            if record.status != 'paid':
                raise UserError(_("Only paid pharmacy requests can be dispensed."))
            if True: # Execute dispensing block
                # First validate all lines have sufficient stock before doing any deduction
                today = fields.Date.today()
                for line in record.line_ids:
                    # Get active, non-expired batches sorted by expiry_date (FEFO)
                    batches = self.env["hospital.medicine.batch"].search([
                        ("medicine_id", "=", line.medicine_id.id),
                        ("qty_remaining", ">", 0),
                        ("expiry_date", ">=", today)
                    ], order="expiry_date asc, name asc")
                    
                    total_available = sum(batches.mapped("qty_remaining"))
                    if total_available < line.qty:
                        raise ValidationError(_("Insufficient stock for medicine '%s'! Required: %s, Available: %s") % (
                            line.medicine_id.name, line.qty, total_available
                        ))

                # If all lines are valid, perform the FEFO deduction
                for line in record.line_ids:
                    qty_to_deduct = line.qty
                    batches = self.env["hospital.medicine.batch"].search([
                        ("medicine_id", "=", line.medicine_id.id),
                        ("qty_remaining", ">", 0),
                        ("expiry_date", ">=", today)
                    ], order="expiry_date asc, name asc")
                    
                    for batch in batches:
                        if qty_to_deduct <= 0:
                            break
                        
                        deducted = min(qty_to_deduct, batch.qty_remaining)
                        batch.write({
                            "qty_remaining": batch.qty_remaining - deducted
                        })
                        
                        # Create stock movement log
                        self.env["hospital.stock.movement"].create({
                            "medicine_id": line.medicine_id.id,
                            "batch_id": batch.id,
                            "qty": -deducted,
                            "type": "dispense",
                            "reference": record.name
                        })
                        
                        qty_to_deduct -= deducted

                record.write({'status': 'dispensed'})
                record.op_id.write({'pharmacy_completed': True})


class HospitalPharmacyRequestLine(models.Model):
    _name = "hospital.pharmacy.request.line"
    _description = "Pharmacy Request Line"

    request_id = fields.Many2one(
        "hospital.pharmacy.request",
        string="Pharmacy Request",
        required=True,
        ondelete="cascade"
    )
    medicine_id = fields.Many2one(
        "hospital.medicine",
        string="Medicine",
        required=True
    )
    qty = fields.Integer(
        string="Quantity",
        required=True
    )
    dosage = fields.Char(
        string="Dosage"
    )
    duration = fields.Char(
        string="Duration"
    )
    instructions = fields.Char(
        string="Instructions"
    )
    prescription_line_id = fields.Many2one(
        "hospital.prescription.line",
        string="Prescription Line",
        ondelete="set null"
    )
    pharmacist_instructions = fields.Char(
        string="Pharmacist Instructions",
        placeholder="e.g. Take with warm water"
    )
