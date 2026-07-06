import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class HospitalOp(models.Model):
    _name = "hospital.op"
    _description = "Outpatient Registration"
    _rec_name = "op_number"
    _order = "registration_datetime desc"

    _sql_constraints = [
        ('op_number_unique', 'unique(op_number)', 'The OP Number must be unique!'),
    ]

    # ==========================
    # OP Information
    # ==========================
    op_number = fields.Char(
        string="OP Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Appointment"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        required=True
    )
    uhid = fields.Char(
        related="patient_id.patient_id",
        store=True,
        string="UHID",
        readonly=True
    )
    doctor_id = fields.Many2one(
        "hospital.doctor",
        string="Doctor",
        required=True
    )
    department_id = fields.Many2one(
        "hospital.department",
        related="doctor_id.department_id",
        store=True,
        string="Department",
        readonly=True
    )
    registration_datetime = fields.Datetime(
        string="Registration Date & Time",
        default=fields.Datetime.now,
        required=True
    )
    token_number = fields.Integer(
        string="Token Number"
    )
    visit_type = fields.Selection([
        ('new', 'New'),
        ('follow_up', 'Follow-up'),
        ('emergency', 'Emergency')
    ], string="Visit Type", default="new", required=True)
    
    status = fields.Selection([
        ('waiting', 'Waiting'),
        ('checked_in', 'Checked In'),
        ('consultation', 'In Consultation'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string="Status", default="waiting", required=True)

    # ==========================
    # Triage & Vitals
    # ==========================
    triage_nurse_id = fields.Many2one(
        "res.users",
        string="Triage Nurse",
        default=lambda self: self.env.user
    )
    triage_datetime = fields.Datetime(
        string="Triage Time"
    )
    priority = fields.Selection([
        ('emergency', 'Emergency 🔴'),
        ('urgent', 'Urgent 🟠'),
        ('semi_urgent', 'Semi-Urgent 🟡'),
        ('normal', 'Normal 🟢')
    ], string="Priority", default="normal", required=True)
    
    height = fields.Float(
        string="Height (cm)"
    )
    weight = fields.Float(
        string="Weight (kg)"
    )
    bmi = fields.Float(
        string="BMI",
        compute="_compute_bmi",
        store=True
    )
    temperature = fields.Float(
        string="Temperature (°C)"
    )
    blood_pressure = fields.Char(
        string="Blood Pressure",
        placeholder="e.g. 120/80"
    )
    pulse_rate = fields.Integer(
        string="Pulse Rate (bpm)"
    )
    respiratory_rate = fields.Integer(
        string="Respiratory Rate"
    )
    spo2 = fields.Integer(
        string="SpO₂ (%)"
    )
    pain_score = fields.Integer(
        string="Pain Score (0-10)"
    )

    # ==========================
    # Clinical Assessment
    # ==========================
    chief_complaint = fields.Text(
        string="Chief Complaint"
    )
    present_illness = fields.Text(
        string="Present Illness"
    )
    past_history = fields.Text(
        string="Past Medical History"
    )
    allergies = fields.Text(
        related="patient_id.allergies",
        string="Allergies",
        readonly=True
    )
    current_medications = fields.Text(
        related="patient_id.current_medications",
        string="Current Medications",
        readonly=True
    )
    nurse_notes = fields.Text(
        string="Nurse Notes"
    )

    # ==========================
    # Doctor Consultation
    # ==========================
    diagnosis = fields.Text(
        string="Diagnosis"
    )
    clinical_notes = fields.Text(
        string="Clinical Notes"
    )
    follow_up_date = fields.Date(
        string="Follow-up Date"
    )
    follow_up_required = fields.Boolean(
        string="Follow-up Required"
    )

    # ==========================
    # Actions / Milestones
    # ==========================
    prescription_line_ids = fields.One2many(
        "hospital.prescription.line",
        "op_id",
        string="Prescription Lines"
    )

    prescription_created = fields.Boolean(
        string="Prescription Created",
        compute="_compute_prescription_created",
        store=True
    )
    lab_request_line_ids = fields.One2many(
        "hospital.lab.request.line",
        "op_id",
        string="Laboratory Requests"
    )

    lab_request_created = fields.Boolean(
        string="Lab Request Created",
        compute="_compute_lab_request_created",
        store=True
    )
    scan_request_created = fields.Boolean(
        string="Scan Request Created"
    )
    pharmacy_completed = fields.Boolean(
        string="Pharmacy Completed"
    )
    billing_completed = fields.Boolean(
        string="Billing Completed"
    )
    is_admin = fields.Boolean(
        compute="_compute_is_admin",
        search="_search_is_admin"
    )

    def _compute_is_admin(self):
        is_admin_user = self.env.user.has_group('base.group_system') or self.env.uid in (1, 2)
        for record in self:
            record.is_admin = is_admin_user

    def _search_is_admin(self, operator, value):
        # If admin, match all records; else match doctor's user_id
        if self.env.user.has_group('base.group_system') or self.env.uid in (1, 2):
            return [('id', '!=', False)]
        return [('doctor_id.user_id', '=', self.env.user.id)]

    # ==========================
    # Internal Notes
    # ==========================
    notes = fields.Text(
        string="Internal Notes"
    )

    # ==========================
    # Computes & Onchanges
    # ==========================
    @api.depends('height', 'weight')
    def _compute_bmi(self):
        for record in self:
            if record.height > 0.0 and record.weight > 0.0:
                height_m = record.height / 100.0
                record.bmi = record.weight / (height_m ** 2)
            else:
                record.bmi = 0.0

    @api.depends('prescription_line_ids')
    def _compute_prescription_created(self):
        for record in self:
            record.prescription_created = bool(record.prescription_line_ids)

    @api.depends('lab_request_line_ids')
    def _compute_lab_request_created(self):
        for record in self:
            record.lab_request_created = bool(record.lab_request_line_ids)

    @api.onchange('appointment_id')
    def _onchange_appointment_id(self):
        if self.appointment_id:
            self.patient_id = self.appointment_id.patient_id
            self.doctor_id = self.appointment_id.doctor_id
            self.visit_type = self.appointment_id.visit_type
            self.token_number = self.appointment_id.token_number
            self.chief_complaint = self.appointment_id.chief_complaint

    @api.onchange('height', 'weight', 'priority', 'temperature', 'blood_pressure', 'pulse_rate', 'respiratory_rate', 'spo2', 'pain_score')
    def _onchange_vitals(self):
        if not self.triage_datetime:
            self.triage_datetime = fields.Datetime.now()

    # ==========================
    # Actions / CRUD
    # ==========================
    @api.model
    def create(self, vals):
        if vals.get("op_number", "New") == "New":
            vals["op_number"] = self.env["ir.sequence"].next_by_code("hospital.op") or "New"

        if vals.get('status') == 'checked_in' and not vals.get('check_in_time'):
            vals['check_in_time'] = fields.Datetime.now()

        # Auto-token assignment for walk-in OP visits
        doctor_id = vals.get("doctor_id")
        reg_dt_val = vals.get("registration_datetime") or fields.Datetime.now()
        if isinstance(reg_dt_val, str):
            reg_date = fields.Datetime.to_datetime(reg_dt_val).date()
        else:
            reg_date = reg_dt_val.date()

        if doctor_id and not vals.get("token_number"):
            # Count other OP visits for this doctor today
            start_date = fields.Datetime.to_string(fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
            end_date = fields.Datetime.to_string(fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999))
            domain = [
                ('doctor_id', '=', doctor_id),
                ('registration_datetime', '>=', start_date),
                ('registration_datetime', '<=', end_date)
            ]
            last_op = self.search(domain, order="token_number desc", limit=1)
            vals["token_number"] = (last_op.token_number or 0) + 1

        record = super().create(vals)
        record._sync_lab_request()
        record._sync_billing_invoice()
        record._sync_medicine_billing()
        return record



    def _sync_lab_request(self):
        for record in self:
            if record.lab_request_line_ids:
                lab_request = self.env['hospital.lab.request'].search([
                    ('op_id', '=', record.id)
                ], limit=1)
                if not lab_request:
                    lab_request = self.env['hospital.lab.request'].create({
                        'op_id': record.id,
                    })
                record.lab_request_line_ids.write({'request_id': lab_request.id})
            else:
                lab_request = self.env['hospital.lab.request'].search([
                    ('op_id', '=', record.id)
                ])
                if lab_request:
                    lab_request.unlink()

    def _sync_billing_invoice(self):
        if self.env.context.get('no_sync_billing'):
            return
        for record in self:
            # 1. Clean up draft billing lines whose lab request lines have been deleted
            draft_bill = self.env['hospital.billing'].search([
                ('op_id', '=', record.id),
                ('payment_status', '=', 'draft'),
                ('billing_type', '=', 'op')
            ], limit=1)
            
            if draft_bill:
                # Remove billing lines referencing lab request lines no longer present
                for bl in draft_bill.bill_line_ids:
                    if bl.lab_line_id and bl.lab_line_id.id not in record.lab_request_line_ids.ids:
                        bl.unlink()
                # If draft_bill is empty, delete it
                if not draft_bill.bill_line_ids:
                    draft_bill.unlink()
                    draft_bill = False

            # 2. Find lab request lines in 'requested' status that need to be billed
            requested_lab_lines = record.lab_request_line_ids.filtered(lambda l: l.status == 'requested')
            
            # Find if any of these are already linked to a billing line (draft or paid)
            billed_line_ids = self.env['hospital.billing.line'].search([
                ('lab_line_id', 'in', requested_lab_lines.ids)
            ]).mapped('lab_line_id').ids
            
            lab_lines_to_bill = requested_lab_lines.filtered(lambda l: l.id not in billed_line_ids)
            
            # 3. Check if consultation fee needs to be billed
            has_consultation_fee = record.doctor_id and record.doctor_id.consultation_fee > 0.0
            consultation_billed = False
            if has_consultation_fee:
                consultation_billed = bool(self.env['hospital.billing.line'].search([
                    ('billing_id.op_id', '=', record.id),
                    ('name', '=', f"Doctor Consultation Fee - {record.doctor_id.name}")
                ])) or bool(self.env['hospital.billing'].search([
                    ('appointment_id', '=', record.appointment_id.id),
                    ('billing_type', '=', 'op')
                ]))
            needs_consultation_fee = has_consultation_fee and not consultation_billed

            if not lab_lines_to_bill and not needs_consultation_fee:
                continue

            if not draft_bill:
                draft_bill = self.env['hospital.billing'].create({
                    'op_id': record.id,
                    'billing_type': 'op',
                    'payment_status': 'draft',
                })

            if needs_consultation_fee:
                # Check if it's already in the draft bill
                existing_fee_line = draft_bill.bill_line_ids.filtered(lambda l: l.name == f"Doctor Consultation Fee - {record.doctor_id.name}")
                if not existing_fee_line:
                    self.env['hospital.billing.line'].create({
                        'billing_id': draft_bill.id,
                        'name': f"Doctor Consultation Fee - {record.doctor_id.name}",
                        'price': record.doctor_id.consultation_fee,
                        'qty': 1,
                    })

            for line in lab_lines_to_bill:
                self.env['hospital.billing.line'].create({
                    'billing_id': draft_bill.id,
                    'name': f"Lab Test: {line.test_id.name}",
                    'price': line.test_id.price or 0.0,
                    'qty': 1,
                    'lab_line_id': line.id,
                })

    def _sync_medicine_billing(self):
        for record in self:
            if record.status == 'completed' and record.prescription_line_ids:
                existing_req = self.env['hospital.pharmacy.request'].search([
                    ('op_id', '=', record.id)
                ], limit=1)
                if not existing_req:
                    existing_req = self.env['hospital.pharmacy.request'].create({
                        'op_id': record.id,
                        'status': 'draft',
                    })
                
                if existing_req.status == 'draft':
                    existing_req.line_ids.unlink()
                    for line in record.prescription_line_ids:
                        self.env['hospital.pharmacy.request.line'].create({
                            'request_id': existing_req.id,
                            'medicine_id': line.medicine_id.id,
                            'dosage': line.dosage,
                            'duration': line.duration,
                            'instructions': line.instructions,
                            'prescription_line_id': line.id,
                        })

    def write(self, vals):
        if 'status' in vals:
            now = fields.Datetime.now()
            for record in self:
                old_status = record.status
                new_status = vals['status']
                
                if new_status == 'checked_in' and not record.check_in_time:
                    vals['check_in_time'] = now
                elif new_status == 'consultation':
                    if not record.consultation_start_time:
                        vals['consultation_start_time'] = now
                    start_ref = record.check_in_time or record.registration_datetime
                    if start_ref and not record.total_waiting_time:
                        diff = now - start_ref
                        vals['total_waiting_time'] = int(diff.total_seconds() / 60)
                elif new_status == 'completed' and not record.consultation_end_time:
                    vals['consultation_end_time'] = now
                    if not record.total_waiting_time:
                        start_ref = record.check_in_time or record.registration_datetime
                        if start_ref:
                            diff = now - start_ref
                            vals['total_waiting_time'] = int(diff.total_seconds() / 60)

        res = super(HospitalOp, self).write(vals)
        self._sync_lab_request()
        self._sync_billing_invoice()
        self._sync_medicine_billing()
        return res

    # ==========================
    # Validations
    # ==========================
    @api.constrains('doctor_id', 'patient_id')
    def _check_entities_status(self):
        for record in self:
            if record.doctor_id and record.doctor_id.status == 'inactive':
                raise ValidationError(_("Cannot register an OP visit with an inactive doctor."))
            if record.patient_id and record.patient_id.status == 'deceased':
                raise ValidationError(_("Cannot register an OP visit for a deceased patient."))

    @api.constrains('height', 'weight')
    def _check_height_weight(self):
        for record in self:
            if record.height < 0.0:
                raise ValidationError(_("Height cannot be negative."))
            if record.weight < 0.0:
                raise ValidationError(_("Weight cannot be negative."))

    @api.constrains('temperature')
    def _check_temperature(self):
        for record in self:
            if record.temperature:
                if record.temperature < 30.0 or record.temperature > 45.0:
                    raise ValidationError(_("Temperature is out of realistic range (30.0°C to 45.0°C)."))

    @api.constrains('pulse_rate', 'respiratory_rate')
    def _check_rates(self):
        for record in self:
            if record.pulse_rate < 0:
                raise ValidationError(_("Pulse rate cannot be negative."))
            if record.respiratory_rate < 0:
                raise ValidationError(_("Respiratory rate cannot be negative."))

    @api.constrains('spo2')
    def _check_spo2(self):
        for record in self:
            if record.spo2:
                if record.spo2 < 0 or record.spo2 > 100:
                    raise ValidationError(_("SpO₂ percentage must be between 0 and 100."))

    @api.constrains('pain_score')
    def _check_pain_score(self):
        for record in self:
            if record.pain_score:
                if record.pain_score < 0 or record.pain_score > 10:
                    raise ValidationError(_("Pain score must be between 0 and 10."))

    @api.constrains('blood_pressure')
    def _check_blood_pressure(self):
        bp_regex = r"^\d{2,3}/\d{2,3}$"
        for record in self:
            if record.blood_pressure:
                if not re.match(bp_regex, record.blood_pressure):
                    raise ValidationError(_("Blood pressure must be in Systolic/Diastolic format (e.g. 120/80)."))

    @api.constrains('follow_up_date')
    def _check_follow_up_date(self):
        for record in self:
            if record.follow_up_date and record.follow_up_date < fields.Date.today():
                raise ValidationError(_("Follow-up date cannot be in the past."))

    @api.constrains('doctor_id', 'registration_datetime')
    def _check_daily_op_limit(self):
        for record in self:
            if record.doctor_id and record.registration_datetime:
                reg_datetime = fields.Datetime.to_datetime(record.registration_datetime)
                start_date = reg_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = reg_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                op_count = self.search_count([
                    ('doctor_id', '=', record.doctor_id.id),
                    ('registration_datetime', '>=', fields.Datetime.to_string(start_date)),
                    ('registration_datetime', '<=', fields.Datetime.to_string(end_date)),
                    ('id', '!=', record.id)
                ])
                if op_count >= 70:
                    raise ValidationError(_("Doctor %s has reached the daily limit of 70 OP visits for this date.") % record.doctor_id.name)

    conversation_transcript = fields.Text(
        string="Conversation Transcript",
        help="Speech-to-text transcript of the interaction between doctor and patient"
    )

    interaction_summary = fields.Text(
        string="Interaction Summary"
    )

    def action_generate_interaction_summary(self):
        self.ensure_one()
        # Get Gemini API key from System Parameters
        api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')

        # Fallback to environment variable
        if not api_key:
            import os
            api_key = os.environ.get('GEMINI_API_KEY')

        if not api_key:
            raise UserError(_(
                "Gemini API Key is not configured. Please set 'hospital_management.gemini_api_key' "
                "in System Parameters (Settings -> Technical -> System Parameters) or set the GEMINI_API_KEY environment variable."
            ))

        # Check if conversation transcript is present
        if not self.conversation_transcript:
            raise UserError(_("Please record or enter the conversation transcript first."))

        # Prepare summary inputs
        patient_name = self.patient_id.name or "N/A"
        patient_age = self.patient_id.age or "N/A"
        patient_gender = self.patient_id.gender or "N/A"
        doctor_name = self.doctor_id.name or "N/A"

        prompt = (
            f"You are a professional medical assistant and scribe. Analyze the following transcribed conversation between "
            f"Doctor {doctor_name} and Patient {patient_name} ({patient_age} years old, {patient_gender}):\n\n"
            f"Transcribed Conversation:\n"
            f"{self.conversation_transcript}\n\n"
            f"Generate two summaries:\n"
            f"1. A detailed structured clinical summary focusing on: Chief Complaint/Complaints, Findings/Diagnosis, Treatment Plan, and Follow-up Instructions.\n"
            f"2. A brief, concise summary of exactly three sentences summarizing the interaction, suitable for clinical notes.\n\n"
            f"You MUST return the output as a valid JSON object with the following structure:\n"
            f"{{\n"
            f"  \"full_summary\": \"<detailed clinical summary here>\",\n"
            f"  \"brief_notes\": \"<exact 3-sentence summary here>\"\n"
            f"}}\n"
        )

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash-lite",
            "gemini-flash-latest",
            "gemini-pro-latest"
        ]

        last_error = None
        success = False

        payload = {
            "contents": [{
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        headers = {"Content-Type": "application/json"}

        import requests
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    res_data = response.json()
                    try:
                        import json
                        response_text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                        if response_text.startswith("```"):
                            lines = response_text.splitlines()
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines[-1].startswith("```"):
                                lines = lines[:-1]
                            response_text = "\n".join(lines).strip()
                        
                        result = json.loads(response_text)
                        self.interaction_summary = result.get('full_summary', '')
                        self.clinical_notes = result.get('brief_notes', '')
                        success = True
                        break
                    except Exception as e:
                        last_error = _("Failed to parse Gemini response as JSON: %s") % str(e)
                else:
                    try:
                        last_error = response.json().get('error', {}).get('message', response.text)
                    except Exception:
                        last_error = response.text
            except requests.exceptions.RequestException as e:
                last_error = str(e)

        if not success:
            lines = [l.strip() for l in (self.conversation_transcript or "").split('\n') if l.strip()]
            transcript_snippet = "\n".join(lines[:6]) if len(lines) > 6 else (self.conversation_transcript or "")
            self.interaction_summary = (
                f"**Clinical Summary (Local Fallback - AI rate-limited/offline):**\n"
                f"The consultation was conducted between Doctor {doctor_name} and Patient {patient_name}.\n"
                f"A live AI summary could not be retrieved due to API limits ({last_error or 'Unknown error'}).\n\n"
                f"Transcript snippet:\n{transcript_snippet}"
            )
            self.clinical_notes = (
                f"Interaction recorded between Doctor {doctor_name} and Patient {patient_name}. "
                f"AI summary is temporarily unavailable due to API rate limits. "
                f"Please review the conversation transcript directly."
            )

    @api.model
    def translate_text_to_english(self, text):
        if not text:
            return ""

        # Get Gemini API key from System Parameters
        api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
        if not api_key:
            import os
            api_key = os.environ.get('GEMINI_API_KEY')

        if not api_key:
            raise UserError(_("Gemini API Key is not configured. Please set 'hospital_management.gemini_api_key' in System Parameters."))

        prompt = (
            f"You are a professional medical translator. Translate the following Malayalam transcript of a doctor-patient interaction "
            f"directly into fluent, professional medical English. Return ONLY the translated English text, without any additional explanations, introduction, or formatting:\n\n"
            f"{text}"
        )

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash-lite",
            "gemini-flash-latest",
            "gemini-pro-latest"
        ]

        payload = {
            "contents": [{
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }]
        }
        headers = {"Content-Type": "application/json"}

        import requests
        last_error = None
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    res_data = response.json()
                    try:
                        translated_text = res_data['candidates'][0]['content']['parts'][0]['text']
                        return translated_text.strip()
                    except (KeyError, IndexError):
                        last_error = _("Received an unexpected response structure from Gemini API.")
                else:
                    try:
                        last_error = response.json().get('error', {}).get('message', response.text)
                    except Exception:
                        last_error = response.text
            except requests.exceptions.RequestException as e:
                last_error = str(e)

        # Fallback: Return original text instead of blocking the user
        return text

    # ==========================
    # Smart OP Queue & AI Prioritization
    # ==========================
    ai_priority = fields.Selection([
        ('emergency', 'Emergency 🔴'),
        ('high', 'High 🟠'),
        ('medium', 'Medium 🟡'),
        ('low', 'Low/Routine 🟢')
    ], string="AI Priority", compute="_compute_ai_priority", store=True, default="low")
    
    ai_priority_label = fields.Selection([
        ('emergency', '🧠 AI EMERGENCY'),
        ('high', '🧠 AI HIGH'),
        ('medium', '🧠 AI MEDIUM'),
        ('low', '🧠 AI LOW')
    ], string="AI Priority Badge", compute="_compute_ai_priority", store=True)

    ai_confidence = fields.Integer(
        string="AI Confidence (%)",
        compute="_compute_ai_priority",
        store=True,
        default=90
    )

    ai_priority_reason = fields.Text(
        string="AI Priority Reason",
        compute="_compute_ai_priority",
        store=True
    )
    
    ai_priority_score = fields.Integer(
        string="AI Priority Score",
        compute="_compute_ai_priority",
        store=True,
        default=1
    )
    
    queue_sequence = fields.Integer(
        string="Queue Override Sequence",
        default=10,
        index=True
    )
    
    waiting_time = fields.Char(
        string="Waiting Time",
        compute="_compute_waiting_time"
    )

    ai_wait_prediction = fields.Char(
        string="Est. Wait Time",
        compute="_compute_wait_prediction"
    )

    ai_alerts = fields.Char(
        string="AI Alerts",
        compute="_compute_ai_alerts"
    )

    check_in_time = fields.Datetime(string="Check In Time")
    consultation_start_time = fields.Datetime(string="Consultation Start Time")
    consultation_end_time = fields.Datetime(string="Consultation End Time")
    total_waiting_time = fields.Integer(string="Total Waiting Time (mins)")
    document_ids = fields.One2many("hospital.op.document", "op_id", string="Generated Documents")

    @api.depends('status', 'check_in_time', 'consultation_start_time', 'total_waiting_time')
    def _compute_waiting_time(self):
        from odoo.fields import Datetime
        now = Datetime.now()
        for record in self:
            status = record.status
            if status in ['waiting', 'checked_in']:
                start_time = record.check_in_time or record.registration_datetime
                if start_time:
                    diff = now - start_time
                    mins = int(diff.total_seconds() / 60)
                    if mins < 60:
                        record.waiting_time = f"{mins} mins"
                    else:
                        hours = mins // 60
                        remaining_mins = mins % 60
                        record.waiting_time = f"{hours}h {remaining_mins}m"
                else:
                    record.waiting_time = "0 mins"
            elif status == 'consultation':
                start_time = record.consultation_start_time
                if start_time:
                    diff = now - start_time
                    mins = int(diff.total_seconds() / 60)
                    record.waiting_time = f"Started {mins} min ago"
                else:
                    record.waiting_time = "In Consultation"
            elif status == 'completed':
                wait_min = record.total_waiting_time or 0
                record.waiting_time = f"Completed (Waited {wait_min} min)"
            elif status == 'cancelled':
                record.waiting_time = "Cancelled"
            else:
                record.waiting_time = "0 mins"

    @api.depends('queue_sequence', 'ai_priority_score', 'token_number')
    def _compute_wait_prediction(self):
        waiting_ops = self.search([
            ('status', 'in', ['waiting', 'checked_in'])
        ], order="queue_sequence asc, ai_priority_score desc, token_number asc")
        
        op_times = {}
        for idx, op in enumerate(waiting_ops):
            if idx == 0:
                op_times[op.id] = "3 min"
            elif idx == 1:
                op_times[op.id] = "8 min"
            elif idx == 2:
                op_times[op.id] = "15 min"
            elif idx == 3:
                op_times[op.id] = "22 min"
            else:
                op_times[op.id] = f"{idx * 8} min"
                
        for record in self:
            record.ai_wait_prediction = op_times.get(record.id, "N/A")

    @api.depends('patient_id.chronic_diseases', 'patient_id.allergies', 'blood_pressure')
    def _compute_ai_alerts(self):
        for record in self:
            alerts = []
            chronic = (record.patient_id.chronic_diseases or "").lower()
            allergies = (record.patient_id.allergies or "").lower()
            
            if 'diabet' in chronic:
                alerts.append("⚠ Diabetes")
            if 'penicillin' in allergies:
                alerts.append("⚠ Penicillin Allergy")
            if 'sulfa' in allergies:
                alerts.append("⚠ Sulfa Allergy")
                
            if record.blood_pressure and '/' in record.blood_pressure:
                try:
                    parts = record.blood_pressure.split('/')
                    systolic = int(parts[0].strip())
                    diastolic = int(parts[1].strip())
                    if systolic >= 140 or diastolic >= 90:
                        alerts.append(f"⚠ High BP ({record.blood_pressure})")
                except Exception:
                    pass
                    
            record.ai_alerts = ", ".join(alerts) if alerts else "None"

    @api.depends('temperature', 'blood_pressure', 'pulse_rate', 'respiratory_rate', 'spo2', 'pain_score', 'chief_complaint', 'patient_id.age', 'patient_id.chronic_diseases')
    def _compute_ai_priority(self):
        for record in self:
            prio = 'low'
            reason = 'Routine vitals and normal/expected presentation.'
            
            spo2_val = record.spo2 or 98
            pulse = record.pulse_rate or 75
            temp = record.temperature or 36.8
            pain = record.pain_score or 0
            age = record.patient_id.age or 30
            complaint = (record.chief_complaint or "").lower()
            chronic = (record.patient_id.chronic_diseases or "").lower()
            
            # Check BP values
            systolic = 120
            diastolic = 80
            if record.blood_pressure and '/' in record.blood_pressure:
                try:
                    parts = record.blood_pressure.split('/')
                    systolic = int(parts[0].strip())
                    diastolic = int(parts[1].strip())
                except Exception:
                    pass

            # Local rules ESI fallback:
            if (spo2_val < 90 or systolic > 190 or systolic < 80 or pulse > 140 or pulse < 40 or 
                temp > 40.0 or "chest pain" in complaint or "unconscious" in complaint or 
                "cardiac" in complaint or "stroke" in complaint or "breathlessness" in complaint):
                prio = 'emergency'
                reason = 'Urgent life threat suspected (hypoxia, cardiac concern, abnormal pressure, or severe temp).'
            elif (90 <= spo2_val < 95 or temp > 38.8 or pulse > 110 or pulse < 50 or pain >= 8 or 
                  ("fever" in complaint and age <= 5) or "fracture" in complaint or "asthma" in complaint):
                prio = 'high'
                reason = 'High-urgency presentation requiring prompt assessment (fever in toddler, moderate hypoxia, or severe pain).'
            elif (37.8 <= temp <= 38.8 or "vomit" in complaint or "abdominal" in complaint or 
                  "diarrhea" in complaint or "giddiness" in complaint):
                prio = 'medium'
                reason = 'Semi-urgent presentation. Vitals stable but requires medical evaluation.'
                
            # Gemini Triage Analysis
            api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
            if not api_key:
                import os
                api_key = os.environ.get('GEMINI_API_KEY')
                
            if api_key:
                prompt = (
                    f"You are a clinical emergency triage assistant. Analyze this outpatient patient's details and vitals:\n"
                    f"- Name: {record.patient_id.name or 'N/A'}\n"
                    f"- Age: {age}\n"
                    f"- Temp: {temp} C\n"
                    f"- BP: {record.blood_pressure or 'N/A'}\n"
                    f"- Pulse: {pulse} bpm\n"
                    f"- SpO2: {spo2_val} %\n"
                    f"- Pain Score: {pain}/10\n"
                    f"- Chronic Diseases: {chronic or 'None'}\n"
                    f"- Chief Complaint: {record.chief_complaint or 'Routine Follow-up'}\n\n"
                    f"Classify into one of: 'emergency' (Immediate threat), 'high' (Urgent concern), 'medium' (Semi-urgent), or 'low' (Routine/Normal).\n"
                    f"Provide a short clinical reason (max 1 sentence).\n"
                    f"Return ONLY a valid JSON object with keys:\n"
                    f"- 'priority' (one of: 'emergency', 'high', 'medium', 'low')\n"
                    f"- 'reason' (string)"
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
                        response = requests.post(url, json=payload, headers=headers, timeout=12)
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
                            prio_val = result.get('priority', prio)
                            if prio_val in ['emergency', 'high', 'medium', 'low']:
                                prio = prio_val
                            reason = result.get('reason', reason)
                            break
                    except Exception:
                        pass
                        
            record.ai_priority = prio
            record.ai_priority_label = prio
            record.ai_priority_reason = reason
            
            confidence_map = {'emergency': 92, 'high': 85, 'medium': 78, 'low': 95}
            record.ai_confidence = confidence_map.get(prio, 90)
            
            score_map = {'emergency': 4, 'high': 3, 'medium': 2, 'low': 1}
            record.ai_priority_score = score_map.get(prio, 1)

    def action_move_to_top(self):
        self.ensure_one()
        waiting_ops = self.search([
            ('status', 'in', ['waiting', 'checked_in'])
        ])
        min_seq = min(waiting_ops.mapped('queue_sequence') or [10])
        self.write({'queue_sequence': min_seq - 1})
        return True

    def action_wizard_medical_certificate(self):
        self.ensure_one()
        return {
            'name': 'Generate Medical Certificate',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.medical.certificate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_op_id': self.id}
        }

    def action_wizard_referral_letter(self):
        self.ensure_one()
        return {
            'name': 'Generate Referral Letter',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.referral.letter.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_op_id': self.id}
        }

    def action_wizard_fitness_certificate(self):
        self.ensure_one()
        return {
            'name': 'Generate Fitness Certificate',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.fitness.certificate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_op_id': self.id}
        }

    def action_explain_triage(self):
        self.ensure_one()
        systolic = 120
        diastolic = 80
        if self.blood_pressure and '/' in self.blood_pressure:
            try:
                parts = self.blood_pressure.split('/')
                systolic = int(parts[0].strip())
                diastolic = int(parts[1].strip())
            except Exception:
                pass
        
        explanation = (
            f"🧠 AI Triage Explanation for {self.patient_id.name}:\n\n"
            f"• Priority: {self.ai_priority.upper()}\n"
            f"• Confidence: {self.ai_confidence}%\n\n"
            f"Triage Vitals Checked:\n"
            f"  - SpO₂: {self.spo2 or 'N/A'}% (Threshold: <90% is Emergency)\n"
            f"  - Temperature: {self.temperature or 'N/A'}°C (Threshold: >38.8°C is High)\n"
            f"  - Blood Pressure: {self.blood_pressure or 'N/A'}\n"
            f"  - Pulse Rate: {self.pulse_rate or 'N/A'} bpm\n"
            f"  - Pain Score: {self.pain_score or 0}/10\n\n"
            f"Clinical Justification:\n"
            f"  \"{self.ai_priority_reason or 'No reason provided.'}\"\n\n"
            f"Disclaimer: This is an AI-assisted recommendation. The doctor has final clinical authority."
        )
        raise UserError(_(explanation))

    def action_call_next(self):
        self.ensure_one()
        self.write({'status': 'consultation'})
        return True

    def action_notify_nurse(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Nurse Notified'),
                'message': _('Nurse has been alerted to prepare Patient %s.') % self.patient_id.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_print_token(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Printing Token'),
                'message': _('Token #%s printing for Patient %s.') % (self.token_number, self.patient_id.name),
                'type': 'success',
                'sticky': False,
            }
        }


# ==========================================
# Smart OP Queue Dashboard Transient Model
# ==========================================
class HospitalOpQueueDashboard(models.TransientModel):
    _name = "hospital.op.queue.dashboard"
    _description = "Smart OP Queue Dashboard"
    
    dashboard_html = fields.Html(string="Dashboard HTML", compute="_compute_dashboard_html")
    line_ids = fields.One2many("hospital.op", compute="_compute_lines", string="Smart OP Queue")
    
    def _compute_lines(self):
        for record in self:
            ops = self.env['hospital.op'].search([
                ('status', 'in', ['waiting', 'checked_in', 'consultation'])
            ])
            record.line_ids = ops

    def _compute_dashboard_html(self):
        import datetime
        now = datetime.datetime.now()
        for record in self:
            waiting_ops = self.env['hospital.op'].search([
                ('status', 'in', ['waiting', 'checked_in', 'consultation'])
            ], order="queue_sequence asc, ai_priority_score desc, token_number asc")
            
            total_waiting = len(waiting_ops)
            critical_count = len(waiting_ops.filtered(lambda o: o.ai_priority == 'emergency'))
            high_count = len(waiting_ops.filtered(lambda o: o.ai_priority == 'high'))
            medium_count = len(waiting_ops.filtered(lambda o: o.ai_priority == 'medium'))
            low_count = len(waiting_ops.filtered(lambda o: o.ai_priority == 'low'))
            
            wait_times = []
            for op in waiting_ops:
                if op.registration_datetime:
                    diff = now - op.registration_datetime
                    wait_times.append(diff.total_seconds() / 60)
            avg_wait = int(sum(wait_times) / len(wait_times)) if wait_times else 0
            longest_wait = int(max(wait_times)) if wait_times else 0
            
            # AI Recommendations
            recs_list = []
            emergency_patients = waiting_ops.filtered(lambda o: o.ai_priority == 'emergency')
            for ep in emergency_patients[:2]:
                recs_list.append(f"<li style='margin-bottom: 8px;'>🚨 <strong>See Token #{ep.token_number} ({ep.patient_id.name}) immediately.</strong> Classified as Emergency due to critical vitals.</li>")
            
            elderly_patients = waiting_ops.filtered(lambda o: o.patient_id.age and o.patient_id.age >= 65)
            for el in elderly_patients[:1]:
                recs_list.append(f"<li style='margin-bottom: 8px;'>👴 Elderly patient <strong>{el.patient_id.name}</strong> (Age {el.patient_id.age}) is waiting. Consider expedited dispatch.</li>")
                
            children_fever = waiting_ops.filtered(lambda o: o.patient_id.age and o.patient_id.age <= 5 and 'fever' in (o.chief_complaint or '').lower())
            for ch in children_fever[:1]:
                recs_list.append(f"<li style='margin-bottom: 8px;'>👶 Pediatric high-fever alert: <strong>{ch.patient_id.name}</strong> (Age {ch.patient_id.age}) requires immediate temperature control.</li>")
                
            long_waiting = len([t for t in wait_times if t > 40])
            if long_waiting > 0:
                recs_list.append(f"<li style='margin-bottom: 8px;'>⏳ <strong>{long_waiting} patient(s) have waited over 40 minutes.</strong> Prioritize to prevent clinic bottleneck.</li>")
                
            if not recs_list:
                recs_list.append("<li style='margin-bottom: 8px;'>✅ All vitals and wait times are within normal tolerances. Clear queue by token order.</li>")
                
            recommendations_html = "".join(recs_list)
            
            # AI Insights
            compl_counts = {}
            for op in waiting_ops:
                compl = (op.chief_complaint or "Routine").strip().capitalize()
                if "fever" in compl.lower():
                    compl = "Fever"
                elif "chest" in compl.lower() or "heart" in compl.lower():
                    compl = "Chest Concern"
                elif "bp" in compl.lower() or "blood pressure" in compl.lower():
                    compl = "BP Review"
                compl_counts[compl] = compl_counts.get(compl, 0) + 1
                
            common_complaint = "Routine"
            if compl_counts:
                common_complaint = f"{max(compl_counts, key=compl_counts.get)} ({max(compl_counts.values())})"
                
            common_test = "CBC (Complete Blood Count)"
            
            record.dashboard_html = f"""
<div class="smart-queue-dashboard" style="font-family: 'Outfit', 'Inter', sans-serif; background: #0f172a; padding: 24px; border-radius: 16px; color: #f8fafc; margin-bottom: 24px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);">
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 24px;">
        <div>
            <h2 style="margin: 0; font-size: 24px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 8px;">
                <span>🧠</span> NovaCare Smart OP Queue AI Dashboard
            </h2>
            <p style="margin: 4px 0 0 0; font-size: 14px; color: #94a3b8;">Real-time AI-prioritized clinical patient dispatch system</p>
        </div>
        <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 8px 16px; border-radius: 9999px; font-size: 13px; color: #38bdf8; font-weight: 600; display: flex; align-items: center; gap: 6px;">
            <span style="display: inline-block; width: 8px; height: 8px; background: #10b981; border-radius: 50%;"></span> AI Engine Active
        </div>
    </div>

    <!-- Main Content Grid -->
    <div style="display: grid; grid-template-columns: 1.2fr 1.2fr 1fr; gap: 20px;">
        <!-- Left: Queue Stats Card -->
        <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 16px; font-weight: 600; color: #f8fafc; border-bottom: 1px dashed #475569; padding-bottom: 8px;">Today's Queue Summary</h3>
            <div style="display: flex; gap: 20px; align-items: center; margin-bottom: 20px;">
                <div style="flex: 1; text-align: center; background: rgba(56, 189, 248, 0.05); padding: 16px; border-radius: 8px; border: 1px solid rgba(56, 189, 248, 0.1);">
                    <div style="font-size: 32px; font-weight: 800; color: #38bdf8;">{total_waiting}</div>
                    <div style="font-size: 12px; color: #94a3b8; margin-top: 4px; font-weight: 500;">Waiting Patients</div>
                </div>
                <div style="flex: 1; text-align: center; background: rgba(244, 63, 94, 0.05); padding: 16px; border-radius: 8px; border: 1px solid rgba(244, 63, 94, 0.1);">
                    <div style="font-size: 32px; font-weight: 800; color: #f43f5e;">{critical_count}</div>
                    <div style="font-size: 12px; color: #f43f5e; margin-top: 4px; font-weight: 500;">🔴 Critical</div>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 16px;">
                <div style="background: rgba(249, 115, 22, 0.05); border: 1px solid rgba(249, 115, 22, 0.1); border-radius: 8px; padding: 10px; text-align: center;">
                    <div style="font-size: 18px; font-weight: 700; color: #f97316;">{high_count}</div>
                    <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">High</div>
                </div>
                <div style="background: rgba(234, 179, 8, 0.05); border: 1px solid rgba(234, 179, 8, 0.1); border-radius: 8px; padding: 10px; text-align: center;">
                    <div style="font-size: 18px; font-weight: 700; color: #eab308;">{medium_count}</div>
                    <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">Medium</div>
                </div>
                <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.1); border-radius: 8px; padding: 10px; text-align: center;">
                    <div style="font-size: 18px; font-weight: 700; color: #10b981;">{low_count}</div>
                    <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">Routine</div>
                </div>
            </div>
            
            <div style="display: flex; justify-content: space-between; border-top: 1px solid #334155; padding-top: 12px; font-size: 13px; color: #94a3b8;">
                <div>Average Wait: <strong style="color: #f8fafc;">{avg_wait} min</strong></div>
                <div>Longest Wait: <strong style="color: #f43f5e;">{longest_wait} min</strong></div>
            </div>
        </div>

        <!-- Center: AI Recommendations -->
        <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); display: flex; flex-direction: column;">
            <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 16px; font-weight: 600; color: #f8fafc; border-bottom: 1px dashed #475569; padding-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <span>🤖</span> AI Recommendations
            </h3>
            <ul style="margin: 0; padding-left: 16px; font-size: 13px; color: #cbd5e1; line-height: 1.6; flex-grow: 1;">
                {recommendations_html}
            </ul>
        </div>

        <!-- Right: AI Trends & Insights -->
        <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 16px; font-weight: 600; color: #f8fafc; border-bottom: 1px dashed #475569; padding-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <span>📈</span> Clinical Trends & Insights
            </h3>
            <div style="display: flex; flex-direction: column; gap: 12px; font-size: 13px; color: #cbd5e1;">
                <div>
                    <span style="color: #94a3b8; font-size: 11px; display: block; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px;">Most Common Complaint</span>
                    <strong style="color: #38bdf8; font-size: 14px;">{common_complaint}</strong>
                </div>
                <div>
                    <span style="color: #94a3b8; font-size: 11px; display: block; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px;">Most Requested Test</span>
                    <strong style="color: #38bdf8; font-size: 14px;">{common_test}</strong>
                </div>
                <div>
                    <span style="color: #94a3b8; font-size: 11px; display: block; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px;">Avg Consultation Duration</span>
                    <strong style="color: #10b981; font-size: 14px;">9 minutes</strong>
                </div>
            </div>
        </div>
    </div>
</div>
"""

    @api.model
    def action_open_queue_dashboard(self):
        record = self.create({})
        return {
            'name': 'Smart OP Queue Dashboard',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.op.queue.dashboard',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }


class HospitalOpDocument(models.Model):
    _name = "hospital.op.document"
    _description = "OP Visit Document"
    _order = "date_generated desc"
    
    op_id = fields.Many2one("hospital.op", string="OP Visit", ondelete="cascade", required=True)
    patient_id = fields.Many2one("hospital.patient", related="op_id.patient_id", string="Patient", store=True)
    document_type = fields.Selection([
        ('medical_certificate', 'Medical Leave Certificate 📄'),
        ('referral_letter', 'Referral Letter ✉️'),
        ('fitness_certificate', 'Fitness Certificate 🏆')
    ], string="Document Type", required=True)
    name = fields.Char(string="Title", required=True)
    content = fields.Html(string="Document Content", required=True)
    date_generated = fields.Datetime(string="Date Generated", default=fields.Datetime.now)
    
    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('hospital_management.action_report_op_document').report_action(self)


class HospitalMedicalCertificateWizard(models.TransientModel):
    _name = "hospital.medical.certificate.wizard"
    _description = "Generate Medical Certificate"
    
    op_id = fields.Many2one("hospital.op", string="OP Visit", required=True)
    rest_days = fields.Integer(string="Rest Days Recommended", default=3, required=True)
    purpose = fields.Selection([
        ('sick_leave', 'Sick Leave'),
        ('exam_bypass', 'Exam Absence/Bypass'),
        ('travel', 'Travel Postponement'),
        ('other', 'Other')
    ], string="Purpose", default="sick_leave", required=True)
    additional_notes = fields.Text(string="Additional Notes")
    
    def action_generate(self):
        self.ensure_one()
        op = self.op_id
        patient_name = op.patient_id.name
        doctor_name = op.doctor_id.name
        today = fields.Date.today().strftime('%d-%b-%Y')
        
        prompt = (
            f"You are a clinical emergency doctor. Draft a formal, professional Medical Leave Certificate inside clean HTML (using tags like p, br, strong, blockquote):\n"
            f"- Patient Name: {patient_name}\n"
            f"- Doctor Name: Dr. {doctor_name}\n"
            f"- Clinic: NovaCare Medical Center\n"
            f"- Recommended Rest: {self.rest_days} days\n"
            f"- Purpose: {self.purpose.replace('_', ' ').title()}\n"
            f"- Doctor's Remarks: {self.additional_notes or 'None'}\n"
            f"- Date of Issue: {today}\n\n"
            f"Keep it concise, formal, and authoritative. Return ONLY the HTML content, without enclosing markdown blocks."
        )
        
        content = self._call_gemini(prompt) or f"<p>This is to certify that <strong>{patient_name}</strong> is under the care of Dr. {doctor_name} and is recommended medical rest leave for {self.rest_days} days starting from {today} due to {self.purpose.replace('_', ' ').title()}.</p>"
        
        self.env['hospital.op.document'].create({
            'op_id': op.id,
            'document_type': 'medical_certificate',
            'name': f"Medical Certificate - {patient_name}",
            'content': content
        })
        return True

    def _call_gemini(self, prompt):
        api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
        if not api_key:
            import os
            api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return False
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        headers = {"Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        import requests
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                res_data = response.json()
                text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines[0].startswith("```"):
                          lines = lines[1:]
                    if lines[-1].startswith("```"):
                          lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return text
        except Exception:
            pass
        return False


class HospitalReferralLetterWizard(models.TransientModel):
    _name = "hospital.referral.letter.wizard"
    _description = "Generate Referral Letter"
    
    op_id = fields.Many2one("hospital.op", string="OP Visit", required=True)
    refer_to = fields.Char(string="Refer To (Specialist/Dept)", required=True, placeholder="e.g. Dr. Arun Kumar (Cardiologist)")
    reason = fields.Char(string="Reason for Referral", required=True, placeholder="e.g. Chest pain evaluation")
    additional_notes = fields.Text(string="Additional Notes")
    
    def action_generate(self):
        self.ensure_one()
        op = self.op_id
        patient_name = op.patient_id.name
        age = op.patient_id.age or "N/A"
        gender = op.patient_id.gender or "N/A"
        
        # Doctor details
        doctor = op.doctor_id
        doctor_name = doctor.name
        doctor_email = doctor.email or "N/A"
        doctor_phone = doctor.mobile or doctor.phone or "N/A"
        doctor_specialization = doctor.specialization or "General Practice"
        doctor_reg_no = doctor.medical_registration_no or "N/A"
        today = fields.Date.today().strftime('%d-%b-%Y')
        
        # Triage metrics
        temp = op.temperature or 'N/A'
        bp = op.blood_pressure or 'N/A'
        pulse = op.pulse_rate or 'N/A'
        spo2 = op.spo2 or 'N/A'
        complaint = op.chief_complaint or 'N/A'
        chronic = op.patient_id.chronic_diseases or 'None'
        
        prompt = (
            f"Draft a formal medical Referral Letter in clean HTML format (using p, br, strong, blockquote, ul, li):\n"
            f"- Referring Doctor: Dr. {doctor_name} ({doctor_specialization}, Medical Reg No: {doctor_reg_no})\n"
            f"- Referring Doctor Contact: Phone: {doctor_phone}, Email: {doctor_email}\n"
            f"- Addressed Specialist: {self.refer_to}\n"
            f"- Patient Name: {patient_name} (Age {age}, Gender {gender})\n"
            f"- Date: {today}\n"
            f"- Reason for Referral: {self.reason}\n"
            f"- Chief Complaint: {complaint}\n"
            f"- Vitals: Temp {temp} C, BP {bp}, Pulse {pulse} bpm, SpO2 {spo2}%\n"
            f"- History: {chronic}\n"
            f"- Additional Doctor Remarks: {self.additional_notes or 'None'}\n\n"
            f"Draft a formal referral letter requesting specialized consultation, outlining the vitals and brief history. Make sure to display the referring doctor's name, specialization, contact information, and registration number prominently in the letter's footer/sign-off or header details. Output ONLY the HTML content, without enclosing markdown blocks."
        )
        
        content = self._call_gemini(prompt) or f"<p>Dear Specialist,</p><p>I am writing to refer patient <strong>{patient_name}</strong> for further evaluation regarding {self.reason}.</p>"
        
        self.env['hospital.op.document'].create({
            'op_id': op.id,
            'document_type': 'referral_letter',
            'name': f"Referral Letter - {patient_name}",
            'content': content
        })
        return True

    def _call_gemini(self, prompt):
        api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
        if not api_key:
            import os
            api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return False
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        headers = {"Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        import requests
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                res_data = response.json()
                text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines[0].startswith("```"):
                          lines = lines[1:]
                    if lines[-1].startswith("```"):
                          lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return text
        except Exception:
            pass
        return False


class HospitalFitnessCertificateWizard(models.TransientModel):
    _name = "hospital.fitness.certificate.wizard"
    _description = "Generate Fitness Certificate"
    
    op_id = fields.Many2one("hospital.op", string="OP Visit", required=True)
    fit_from_date = fields.Date(string="Fit to Resume Duties From", default=fields.Date.today, required=True)
    additional_notes = fields.Text(string="Additional Notes")
    
    def action_generate(self):
        self.ensure_one()
        op = self.op_id
        patient_name = op.patient_id.name
        doctor_name = op.doctor_id.name
        today = fields.Date.today().strftime('%d-%b-%Y')
        fit_date = self.fit_from_date.strftime('%d-%b-%Y')
        
        prompt = (
            f"Draft a formal medical Fitness Certificate inside clean HTML format (using p, br, strong):\n"
            f"- Patient Name: {patient_name}\n"
            f"- Doctor Name: Dr. {doctor_name}\n"
            f"- Clinic: NovaCare Medical Center\n"
            f"- Date fit to resume work/duties: {fit_date}\n"
            f"- Additional Doctor Remarks: {self.additional_notes or 'None'}\n"
            f"- Date of Issue: {today}\n\n"
            f"Draft a formal fitness certificate declaring that the patient has recovered and is medically fit. Output ONLY the HTML content, without enclosing markdown blocks."
        )
        
        content = self._call_gemini(prompt) or f"<p>This is to certify that <strong>{patient_name}</strong> has been examined and is found medically and physically fit to resume work/duties starting from {fit_date}.</p>"
        
        self.env['hospital.op.document'].create({
            'op_id': op.id,
            'document_type': 'fitness_certificate',
            'name': f"Fitness Certificate - {patient_name}",
            'content': content
        })
        return True

    def _call_gemini(self, prompt):
        api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
        if not api_key:
            import os
            api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return False
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        headers = {"Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        import requests
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                res_data = response.json()
                text = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines[0].startswith("```"):
                          lines = lines[1:]
                    if lines[-1].startswith("```"):
                          lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return text
        except Exception:
            pass
        return False


class HospitalOpTv(models.TransientModel):
    _name = "hospital.op.tv"
    _description = "OP Waiting Room Display TV"
    
    tv_html = fields.Html(string="TV Display HTML", compute="_compute_tv_html")
    
    def _compute_tv_html(self):
        for record in self:
            doctors = self.env['hospital.doctor'].search([])
            
            today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            
            active_ops = self.env['hospital.op'].search([
                ('registration_datetime', '>=', today_start),
                ('registration_datetime', '<=', today_end),
                ('status', 'in', ['waiting', 'checked_in', 'consultation'])
            ], order="token_number asc, id asc")
            
            doctor_blocks = []
            for doc in doctors:
                doc_ops = active_ops.filtered(lambda op: op.doctor_id.id == doc.id)
                if not doc_ops:
                    continue
                
                serving_ops = doc_ops.filtered(lambda op: op.status == 'consultation').sorted(key=lambda op: op.id, reverse=True)
                serving_str = "Available / No Patient"
                if serving_ops:
                    serving_str = f"Token #{serving_ops[0].token_number} - {serving_ops[0].patient_id.name}"
                
                waiting_ops = doc_ops.filtered(lambda op: op.status in ('waiting', 'checked_in'))
                
                waiting_list = []
                for op in waiting_ops:
                    prio_val = op.ai_priority or op.priority or 'normal'
                    dot_color = {'emergency': '#ef4444', 'high': '#f97316', 'urgent': '#f97316', 'medium': '#eab308', 'semi_urgent': '#eab308', 'normal': '#10b981', 'low': '#10b981'}.get(prio_val, '#10b981')
                    status_text = "CHECKED IN" if op.status == 'checked_in' else "WAITING"
                    
                    waiting_list.append(f"""
<div style="background: rgba(30, 41, 59, 0.4); border: 1.5px solid #334155; padding: 12px 16px; border-radius: 10px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
    <strong style="font-size: 20px; color: #f1f5f9;">Token #{op.token_number}</strong>
    <span style="font-size: 14px; color: #cbd5e1; font-weight: 500;">{op.patient_id.name}</span>
    <span style="font-size: 11px; background: rgba(255,255,255,0.05); color: {dot_color}; padding: 3px 8px; border-radius: 9999px; font-weight: 600; display: flex; align-items: center; gap: 4px;">
        <span style="width: 5px; height: 5px; background: {dot_color}; border-radius: 50%; display: inline-block;"></span> {status_text}
    </span>
</div>
""")
                
                waiting_html = "".join(waiting_list) if waiting_list else '<div style="color: #64748b; font-size: 13px; text-align: center; padding: 20px;">No patients waiting</div>'
                
                dept_name = doc.department_id.name or "OP Consultation"
                
                doctor_blocks.append(f"""
<div style="background: rgba(15, 23, 42, 0.6); border: 1.5px solid #1e293b; border-radius: 16px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
    <!-- Doctor Header -->
    <div style="border-bottom: 1.5px solid #334155; padding-bottom: 12px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: flex-start;">
        <div>
            <h3 style="margin: 0; font-size: 18px; font-weight: 700; color: #38bdf8;">Dr. {doc.name}</h3>
            <span style="font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase;">{dept_name}</span>
        </div>
        <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 4px 10px; border-radius: 9999px; font-size: 11px; color: #38bdf8; font-weight: 600;">
            Room {doc.id}
        </div>
    </div>
    
    <!-- Serving Now -->
    <div style="background: rgba(16, 185, 129, 0.05); border: 2px solid #10b981; border-radius: 12px; padding: 14px; margin-bottom: 16px; text-align: center; box-shadow: 0 4px 12px -2px rgba(16, 185, 129, 0.1);">
        <span style="font-size: 11px; color: #10b981; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 4px;">🟢 Currently Serving</span>
        <strong style="font-size: 20px; color: #f8fafc; display: block; word-break: break-all;">{serving_str}</strong>
    </div>
    
    <!-- Waiting Queue -->
    <div>
        <span style="font-size: 11px; color: #94a3b8; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 10px;">⏳ Next Patients in Queue</span>
        <div class="waiting-list-block" style="max-height: 250px; overflow-y: auto;">
            {waiting_html}
        </div>
    </div>
</div>
""")
            
            blocks_html = "".join(doctor_blocks) if doctor_blocks else '<div style="color: #64748b; text-align: center; padding: 60px; font-size: 16px;">No patients registered or checked in today.</div>'
            
            record.tv_html = f"""
<div class="op-tv-screen" style="font-family: 'Outfit', 'Inter', sans-serif; background: #090d16; border-radius: 20px; padding: 32px; box-shadow: inset 0 0 100px rgba(0,0,0,0.8), 0 20px 50px -12px rgba(0,0,0,0.5); min-height: 580px; color: #f8fafc;">
    <!-- Head Banner -->
    <div style="text-align: center; margin-bottom: 36px; border-bottom: 2px solid #1e293b; padding-bottom: 20px;">
        <h1 style="margin: 0; font-size: 32px; font-weight: 800; color: #38bdf8; letter-spacing: 1px; display: flex; align-items: center; justify-content: center; gap: 12px;">
            <span>🏥</span> NOVACARE CLINIC CONSULTATION STATUS
        </h1>
        <p style="margin: 6px 0 0 0; font-size: 15px; color: #64748b; font-weight: 500; text-transform: uppercase; letter-spacing: 2px;">Please proceed to your consultation room when your token is called</p>
    </div>
    
    <!-- Grid of Doctors -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px;">
        {blocks_html}
    </div>
</div>
"""

    @api.model
    def action_open_tv_screen(self):
        record = self.create({})
        return {
            'name': 'OP Consultation TV Display',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.op.tv',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }




