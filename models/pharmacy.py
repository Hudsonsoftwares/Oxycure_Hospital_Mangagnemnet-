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
        compute="_compute_qty",
        store=True,
        readonly=False
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
    is_stock_available = fields.Boolean(
        string="Is Stock Available",
        compute="_compute_is_stock_available"
    )
    stock_availability_info = fields.Char(
        string="Stock Status & Suggestion",
        compute="_compute_stock_availability_info"
    )

    @api.depends("qty", "medicine_id.qty_available")
    def _compute_is_stock_available(self):
        for record in self:
            record.is_stock_available = record.qty <= record.medicine_id.qty_available

    @api.depends("qty", "medicine_id.qty_available")
    def _compute_stock_availability_info(self):
        for record in self:
            med = record.medicine_id
            if not med:
                record.stock_availability_info = ""
                continue
                
            qty_avail = med.qty_available
            
            # Determine dynamic unit name based on medicine name, dosage_form, or unit
            unit_name = "Units"
            med_name_lower = (med.name or "").lower()
            if "drop" in med_name_lower:
                unit_name = "Drops"
            elif "tablet" in med_name_lower:
                unit_name = "Tablets"
            elif "capsule" in med_name_lower:
                unit_name = "Capsules"
            elif "syrup" in med_name_lower:
                unit_name = "Bottles"
            elif "injection" in med_name_lower or "vial" in med_name_lower or "ampoule" in med_name_lower:
                unit_name = "Vials"
            elif "cream" in med_name_lower or "ointment" in med_name_lower or "gel" in med_name_lower:
                unit_name = "Tubes"
            else:
                form = med.dosage_form
                if form == "tablet":
                    unit_name = "Tablets"
                elif form == "capsule":
                    unit_name = "Capsules"
                elif form == "syrup":
                    unit_name = "Bottles"
                elif form == "injection":
                    unit_name = "Vials"
                elif form == "ointment":
                    unit_name = "Tubes"
                elif form == "suspension":
                    unit_name = "Bottles"
                elif form == "inhaler":
                    unit_name = "Inhalers"
                elif med.unit:
                    unit_name = f"{med.unit}(s)"

            if qty_avail >= record.qty:
                record.stock_availability_info = f"✓ {qty_avail} {unit_name} Available (Ready to Dispense)"
            else:
                # Prioritize explicitly configured alternatives that are active and in-stock
                alternatives = med.alternative_ids.filtered(lambda a: a.status == "active" and a.qty_available > 0)
                
                # If no configured alternatives are in-stock, fallback to dynamic search
                if not alternatives:
                    alternatives = self.env["hospital.medicine"].search([
                        ("id", "!=", med.id),
                        ("qty_available", ">", 0),
                        ("status", "=", "active"),
                        "|",
                        ("generic_name", "ilike", med.generic_name or "---"),
                        ("category_id", "=", med.category_id.id if med.category_id else False)
                    ], limit=5)
                
                if alternatives:
                    alt_list = ", ".join([f"{a.name} ({a.qty_available} available)" for a in alternatives])
                    api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
                    if not api_key:
                        import os
                        api_key = os.environ.get('GEMINI_API_KEY')
                        
                    suggested_txt = ""
                    if api_key:
                        prompt = (
                            f"The pharmacy is out of stock for '{med.name}' (requested: {record.qty}, available: {qty_avail}).\n"
                            f"Here are the active, in-stock alternatives available in our pharmacy:\n{alt_list}\n\n"
                            f"Recommend the best alternative from this list. Return ONLY a single phrase like: 'Suggested Substitute: <Medicine Name> (<quantity> available)'. Do not include explanations, intro, or markdown."
                        )
                        
                        models_to_try = [
                            "gemini-2.5-flash",
                            "gemini-3.5-flash",
                            "gemini-2.0-flash",
                            "gemini-2.5-pro",
                            "gemini-2.0-flash-lite",
                            "gemini-flash-latest"
                        ]
                        
                        payload = {
                            "contents": [{"parts": [{"text": prompt}]}]
                        }
                        headers = {"Content-Type": "application/json"}
                        
                        import requests
                        import json
                        for model in models_to_try:
                            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                            try:
                                response = requests.post(url, json=payload, headers=headers, timeout=10)
                                if response.status_code == 200:
                                    res_data = response.json()
                                    suggestion = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                                    suggested_txt = suggestion
                                    break
                            except Exception:
                                pass
                                
                    if not suggested_txt:
                        best_alt = alternatives[0]
                        suggested_txt = f"Suggested Substitute: {best_alt.name} ({best_alt.qty_available} available)"
                        
                    record.stock_availability_info = f"Only {qty_avail} {unit_name} Available. {suggested_txt}"
                else:
                    record.stock_availability_info = f"Only {qty_avail} {unit_name} Available. No substitutes in stock."

    @api.depends("dosage", "duration")
    def _compute_qty(self):
        for record in self:
            if record.dosage and record.duration:
                try:
                    record.qty = record._calculate_qty()
                except Exception:
                    record.qty = 0
            else:
                record.qty = 0

    def _calculate_qty(self):
        self.ensure_one()
        import re
        dosage = (self.dosage or "").strip().lower()
        duration = (self.duration or "").strip().lower()
        
        # Parse duration (e.g. "5 days" -> 5, "1 week" -> 7)
        days = 0
        dur_match = re.search(r'(\d+)\s*(day|week|month)', duration)
        if dur_match:
            val = int(dur_match.group(1))
            unit = dur_match.group(2)
            if 'day' in unit:
                days = val
            elif 'week' in unit:
                days = val * 7
            elif 'month' in unit:
                days = val * 30
        else:
            # check for just numbers
            digits = re.findall(r'\d+', duration)
            if digits:
                days = int(digits[0])
                
        if days <= 0:
            days = 1 # default to 1 day if not specified

        # Parse dosage
        daily_qty = 0
        # Check standard 1-0-1 pattern
        if re.match(r'^\d+(-\d+)+$', dosage):
            parts = [int(p) for p in dosage.split('-')]
            daily_qty = sum(parts)
        # Check "3 times daily", "3 times a day"
        elif 'times' in dosage or 'time' in dosage:
            times_match = re.search(r'(\d+)\s*time', dosage)
            if times_match:
                daily_qty = int(times_match.group(1))
        # Check "once daily", "twice daily"
        elif 'once' in dosage:
            daily_qty = 1
        elif 'twice' in dosage:
            daily_qty = 2
        elif 'thrice' in dosage:
            daily_qty = 3
            
        # Check if dosage starts with a number (e.g. "1 tablet")
        tablet_multiplier = 1
        tab_match = re.match(r'^(\d+)\s*(tablet|capsule|pill|unit|ml)', dosage)
        if tab_match:
            tablet_multiplier = int(tab_match.group(1))

        # If both parsed successfully using simple logic, return it
        if daily_qty > 0 and days > 0:
            return daily_qty * tablet_multiplier * days

        # Gemini AI fallback
        api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
        if not api_key:
            import os
            api_key = os.environ.get('GEMINI_API_KEY')

        if api_key:
            prompt = (
                f"You are an AI pharmacy calculator. Calculate the exact total quantity of medicine units (tablets/capsules/ml) "
                f"needed for the following prescription:\n"
                f"- Medicine: {self.medicine_id.name}\n"
                f"- Dosage: {self.dosage}\n"
                f"- Duration: {self.duration}\n"
                f"- Instructions: {self.instructions or 'None'}\n\n"
                f"Return ONLY a valid JSON object with the key 'qty' (integer)."
            )
            
            models_to_try = [
                "gemini-2.5-flash",
                "gemini-3.5-flash",
                "gemini-2.0-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash-lite",
                "gemini-flash-latest"
            ]
            
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            headers = {"Content-Type": "application/json"}
            
            import requests
            import json
            for model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=15)
                    if response.status_code == 200:
                        res_data = response.json()
                        response_text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                        if response_text.startswith("```"):
                            lines = response_text.splitlines()
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines[-1].startswith("```"):
                                lines = lines[:-1]
                            response_text = "\n".join(lines).strip()
                        result = json.loads(response_text)
                        return int(result.get('qty', 0))
                except Exception:
                    pass
                    
        # Ultimate fallback
        return max(days, 1)

    @api.constrains("medicine_id", "qty")
    def _check_pharmacist_modifications(self):
        for line in self:
            request = line.request_id
            if request.status != 'draft':
                continue
                
            is_added = not line.prescription_line_id
            is_swapped = line.prescription_line_id and line.medicine_id.id != line.prescription_line_id.medicine_id.id
            
            if is_added or is_swapped:
                any_out_of_stock = False
                for req_line in request.line_ids:
                    if req_line.prescription_line_id:
                        orig_med = req_line.prescription_line_id.medicine_id
                        if orig_med.qty_available < req_line.qty:
                            any_out_of_stock = True
                            break
                
                if not any_out_of_stock:
                    from odoo.exceptions import ValidationError
                    raise ValidationError(_(
                        "You can only add or substitute medicines if at least one of the prescribed medicines is out of stock."
                    ))
