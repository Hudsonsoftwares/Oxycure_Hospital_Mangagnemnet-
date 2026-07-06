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
        ('paid', 'Queued / Paid'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Collection'),
        ('dispensed', 'Dispensed / Completed'),
        ('cancelled', 'Cancelled')
    ],
        string="Status",
        default="draft",
        required=True
    )
    token_number = fields.Integer(string="Queue Token Number")
    pharmacy_queue_token = fields.Char(string="Pharmacy Queue Token")
    line_ids = fields.One2many(
        "hospital.pharmacy.request.line",
        "request_id",
        string="Requested Medicines"
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.pharmacy.request") or "New"
        
        if vals.get('status') == 'paid' and not vals.get('token_number'):
            today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            domain = [
                ('request_datetime', '>=', today_start),
                ('request_datetime', '<=', today_end),
                ('token_number', '>', 0)
            ]
            last_req = self.search(domain, order="token_number desc", limit=1)
            next_token = (last_req.token_number or 0) + 1
            vals['token_number'] = next_token
            vals['pharmacy_queue_token'] = f"RX-{next_token:03d}"
            
        return super(HospitalPharmacyRequest, self).create(vals)

    def write(self, vals):
        if 'status' in vals and vals['status'] == 'paid':
            for record in self:
                if not record.token_number:
                    today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    today_end = fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
                    domain = [
                        ('request_datetime', '>=', today_start),
                        ('request_datetime', '<=', today_end),
                        ('token_number', '>', 0)
                    ]
                    last_req = self.search(domain, order="token_number desc", limit=1)
                    next_token = (last_req.token_number or 0) + 1
                    vals['token_number'] = next_token
                    vals['pharmacy_queue_token'] = f"RX-{next_token:03d}"
        return super(HospitalPharmacyRequest, self).write(vals)

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
            if record.status not in ('paid', 'preparing', 'ready'):
                raise UserError(_("Only paid, preparing, or ready pharmacy requests can be dispensed."))
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

    def action_start_preparing(self):
        for record in self:
            if record.status == 'paid':
                record.write({'status': 'preparing'})
        return True

    def action_mark_ready(self):
        for record in self:
            if record.status == 'preparing':
                record.write({'status': 'ready'})
        return True


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


class HospitalPharmacyDashboard(models.TransientModel):
    _name = "hospital.pharmacy.dashboard"
    _description = "Pharmacist Operations Control Center"
    
    dashboard_html = fields.Html(string="Dashboard HTML", compute="_compute_dashboard_html")
    active_request_ids = fields.Many2many(
        "hospital.pharmacy.request",
        string="Active Pharmacy Requests",
        compute="_compute_active_requests"
    )
    
    def _compute_active_requests(self):
        for record in self:
            active = self.env['hospital.pharmacy.request'].search([
                ('status', 'in', ['paid', 'preparing', 'ready'])
            ], order="token_number asc, id asc")
            record.active_request_ids = active

    def _compute_dashboard_html(self):
        for record in self:
            active = self.env['hospital.pharmacy.request'].search([
                ('status', 'in', ['paid', 'preparing', 'ready'])
            ])
            
            queued = len(active.filtered(lambda r: r.status == 'paid'))
            preparing = len(active.filtered(lambda r: r.status == 'preparing'))
            ready = len(active.filtered(lambda r: r.status == 'ready'))
            
            # AI Medicine Grouping Optimization
            dispense_queue = active.filtered(lambda r: r.status in ('paid', 'preparing'))
            med_mapping = {}
            for req in dispense_queue:
                token_str = req.pharmacy_queue_token or f"RX-{req.token_number:03d}"
                for line in req.line_ids:
                    med_name = line.medicine_id.name
                    if not med_name:
                        continue
                    if med_name not in med_mapping:
                        med_mapping[med_name] = []
                    med_mapping[med_name].append((token_str, line.qty))

            optimizations = []
            for med_name, requests_data in med_mapping.items():
                if len(requests_data) > 1:
                    tokens = [x[0] for x in requests_data]
                    total_qty = sum(x[1] for x in requests_data)
                    rack_letter = med_name[0].upper()
                    shelf_num = (ord(rack_letter) % 4) + 1
                    location_str = f"Rack {rack_letter}, Shelf {shelf_num}"
                    
                    tokens_str = ", ".join(tokens)
                    optimizations.append(f"""
<li style="margin-bottom: 8px;">
    <span>📦</span> <strong>{med_name}</strong> is required by <strong>{len(requests_data)}</strong> active prescriptions (<strong>{tokens_str}</strong>). 
    Collect <strong>{total_qty} units</strong> total at once from <code>{location_str}</code> to save walking distance!
</li>
""")

            opt_html = ""
            if optimizations:
                opt_html = f"""
    <!-- AI Optimization Banner -->
    <div style="margin-top: 24px; background: rgba(16, 185, 129, 0.05); border: 1.5px solid rgba(16, 185, 129, 0.2); border-radius: 12px; padding: 16px;">
        <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 15px; font-weight: 700; color: #10b981; display: flex; align-items: center; gap: 8px;">
            <span>🤖</span> AI Dispensing Optimization (Less Walking)
        </h3>
        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #cbd5e1; line-height: 1.6;">
            {"".join(optimizations)}
        </ul>
    </div>
"""

            record.dashboard_html = f"""
<div class="pharmacy-dashboard" style="font-family: 'Outfit', 'Inter', sans-serif; background: #0f172a; padding: 24px; border-radius: 16px; color: #f8fafc; margin-bottom: 24px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);">
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px;">
        <div>
            <h2 style="margin: 0; font-size: 24px; font-weight: 700; color: #10b981; display: flex; align-items: center; gap: 8px;">
                <span>💊</span> NovaCare Pharmacy Operations Control Center
            </h2>
            <p style="margin: 4px 0 0 0; font-size: 14px; color: #94a3b8;">Dispensing queue and prescription preparation dashboard</p>
        </div>
        <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.2); padding: 6px 12px; border-radius: 9999px; font-size: 12px; color: #10b981; font-weight: 600;">
            ⚡ Airport Queue Mode
        </div>
    </div>
    
    <!-- Stats Cards Grid -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
        <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid #1e293b; border-radius: 12px; padding: 16px;">
            <span style="color: #94a3b8; font-size: 12px; font-weight: 600; text-transform: uppercase;">Queued (Awaiting Preparation)</span>
            <div style="font-size: 28px; font-weight: 700; color: #f1f5f9; margin-top: 8px; display: flex; align-items: center; gap: 8px;">
                <span>⏳</span> {queued} <span style="font-size: 14px; font-weight: 400; color: #64748b;">Tokens</span>
            </div>
        </div>
        
        <div style="background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 12px; padding: 16px;">
            <span style="color: #38bdf8; font-size: 12px; font-weight: 600; text-transform: uppercase;">Preparing (Packaging)</span>
            <div style="font-size: 28px; font-weight: 700; color: #38bdf8; margin-top: 8px; display: flex; align-items: center; gap: 8px;">
                <span>🛠️</span> {preparing} <span style="font-size: 14px; font-weight: 400; color: #38bdf8;">Tokens</span>
            </div>
        </div>
        
        <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 12px; padding: 16px;">
            <span style="color: #10b981; font-size: 12px; font-weight: 600; text-transform: uppercase;">Ready for Collection</span>
            <div style="font-size: 28px; font-weight: 700; color: #10b981; margin-top: 8px; display: flex; align-items: center; gap: 8px;">
                <span>✅</span> {ready} <span style="font-size: 14px; font-weight: 400; color: #10b981;">Tokens</span>
            </div>
        </div>
    </div>
    {opt_html}
</div>
"""

    @api.model
    def action_open_pharmacy_dashboard(self):
        record = self.create({})
        return {
            'name': 'Pharmacist Control Dashboard',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.pharmacy.dashboard',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }


class HospitalPharmacyTv(models.TransientModel):
    _name = "hospital.pharmacy.tv"
    _description = "Pharmacy Patient Display TV"
    
    tv_html = fields.Html(string="TV Display HTML", compute="_compute_tv_html")
    
    def _compute_tv_html(self):
        for record in self:
            active = self.env['hospital.pharmacy.request'].search([
                ('status', 'in', ['paid', 'preparing', 'ready'])
            ], order="token_number asc, id asc")
            
            preparing_tokens = active.filtered(lambda r: r.status in ('paid', 'preparing'))
            ready_tokens = active.filtered(lambda r: r.status == 'ready')
            
            prep_list = []
            for r in preparing_tokens:
                token_str = r.pharmacy_queue_token or f"RX-{r.token_number:03d}"
                patient_name = r.patient_id.name or "Patient"
                if r.status == 'paid':
                    badge_style = "background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2);"
                    status_text = "QUEUED"
                    dot_color = "#f59e0b"
                else:
                    badge_style = "background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.2);"
                    status_text = "PREPARING"
                    dot_color = "#38bdf8"
                
                prep_list.append(f"""
<div style="background: rgba(30, 41, 59, 0.4); border: 1.5px solid #334155; padding: 16px 20px; border-radius: 12px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
    <strong style="font-size: 24px; color: #f1f5f9;">{token_str}</strong>
    <span style="font-size: 16px; color: #cbd5e1; font-weight: 500;">{patient_name}</span>
    <span style="font-size: 12px; {badge_style} padding: 4px 10px; border-radius: 9999px; font-weight: 600; display: flex; align-items: center; gap: 4px;">
        <span style="width: 6px; height: 6px; background: {dot_color}; border-radius: 50%; display: inline-block; animation: pulse_tv 1.5s infinite;"></span> {status_text}
    </span>
</div>
""")
                
            ready_list = []
            for r in ready_tokens:
                token_str = r.pharmacy_queue_token or f"RX-{r.token_number:03d}"
                patient_name = r.patient_id.name or "Patient"
                ready_list.append(f"""
<div style="background: rgba(16, 185, 129, 0.05); border: 2px solid #10b981; padding: 18px 24px; border-radius: 14px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 8px 16px -4px rgba(16, 185, 129, 0.1);">
    <strong style="font-size: 28px; color: #10b981;">{token_str}</strong>
    <span style="font-size: 18px; color: #f8fafc; font-weight: 600;">{patient_name}</span>
    <span style="font-size: 13px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1.5px solid rgba(16, 185, 129, 0.3); padding: 6px 14px; border-radius: 9999px; font-weight: 700; letter-spacing: 0.5px;">
        🟢 READY FOR COLLECTION
    </span>
</div>
""")
                
            prep_html = "".join(prep_list) if prep_list else '<div style="color: #64748b; text-align: center; padding: 40px; font-size: 15px;">No tokens currently preparing</div>'
            ready_html = "".join(ready_list) if ready_list else '<div style="color: #64748b; text-align: center; padding: 40px; font-size: 15px;">No tokens ready for collection</div>'
            
            record.tv_html = f"""
<div class="pharmacy-tv-screen" style="font-family: 'Outfit', 'Inter', sans-serif; background: #090d16; border-radius: 20px; padding: 32px; box-shadow: inset 0 0 100px rgba(0,0,0,0.8), 0 20px 50px -12px rgba(0,0,0,0.5); min-height: 550px; color: #f8fafc;">
    <!-- Head Banner -->
    <div style="text-align: center; margin-bottom: 36px; border-bottom: 2px solid #1e293b; padding-bottom: 20px;">
        <h1 style="margin: 0; font-size: 32px; font-weight: 800; color: #10b981; letter-spacing: 1px; display: flex; align-items: center; justify-content: center; gap: 12px;">
            <span>🏥</span> NOVACARE PHARMACY DISPENSING STATUS
        </h1>
        <p style="margin: 6px 0 0 0; font-size: 15px; color: #64748b; font-weight: 500; text-transform: uppercase; letter-spacing: 2px;">Please collect your medicines when your token appears under "Ready"</p>
    </div>
    
    <!-- Split Screen Layout -->
    <div style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 32px;">
        <!-- Left: Preparing -->
        <div style="background: rgba(15, 23, 42, 0.6); border: 1.5px solid #1e293b; padding: 24px; border-radius: 16px;">
            <h2 style="margin-top: 0; margin-bottom: 20px; font-size: 20px; font-weight: 700; color: #94a3b8; border-bottom: 1.5px solid #334155; padding-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                <span style="animation: pulse_tv 1.5s infinite; color: #38bdf8; display: inline-block;">🛠️</span> PREPARING MEDICATION
            </h2>
            <div class="preparing-list">
                {prep_html}
            </div>
        </div>
        
        <!-- Right: Ready -->
        <div style="background: rgba(15, 23, 42, 0.8); border: 2.5px solid #10b981; padding: 24px; border-radius: 18px; box-shadow: 0 0 20px rgba(16, 185, 129, 0.05);">
            <h2 style="margin-top: 0; margin-bottom: 20px; font-size: 22px; font-weight: 800; color: #10b981; border-bottom: 2px solid rgba(16, 185, 129, 0.2); padding-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                <span>✅</span> READY FOR COLLECTION
            </h2>
            <div class="ready-list">
                {ready_html}
            </div>
        </div>
    </div>
    
    <!-- CSS Animation Injection -->
    <style>
        @keyframes pulse_tv {{
            0% {{ opacity: 0.3; }}
            50% {{ opacity: 1; }}
            100% {{ opacity: 0.3; }}
        }}
    </style>
</div>
"""

    @api.model
    def action_open_tv_screen(self):
        record = self.create({})
        return {
            'name': 'Pharmacy Display TV Screen',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.pharmacy.tv',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }
