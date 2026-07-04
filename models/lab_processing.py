from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class HospitalLabProcessing(models.Model):
    _name = "hospital.lab.processing"
    _description = "Laboratory Test Processing"
    _order = "id desc"

    op_id = fields.Many2one(
        "hospital.op",
        string="OP Visit",
        required=True,
        readonly=True,
        ondelete="cascade"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        related="op_id.patient_id",
        store=True,
        string="Patient",
        readonly=True
    )
    test_id = fields.Many2one(
        "hospital.lab.test",
        string="Lab Test / Service",
        required=True,
        readonly=True
    )
    request_line_id = fields.Many2one(
        "hospital.lab.request.line",
        string="Request Line",
        ondelete="cascade"
    )
    status = fields.Selection([
        ('pending', 'Pending Sample'),
        ('collected', 'Sample Collected'),
        ('testing', 'Testing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ],
        string="Status",
        default="pending",
        required=True
    )
    
    # Stage 1: Sample Collection Fields
    sample_type = fields.Selection([
        ('blood', 'Blood'),
        ('urine', 'Urine'),
        ('saliva', 'Saliva'),
        ('swab', 'Swab'),
        ('other', 'Other')
    ],
        string="Sample Type"
    )
    sample_details = fields.Char(
        string="Sample Details",
        placeholder="e.g. Blood (EDTA), Urine Container"
    )
    sample_collected_at = fields.Datetime(
        string="Sample Collected At",
        readonly=True
    )

    # Stage 2: Testing / Processing Fields
    process_start_datetime = fields.Datetime(
        string="Testing Started At",
        readonly=True
    )
    equipment_id = fields.Many2one(
        "hospital.lab.equipment",
        string="Equipment Used",
        domain="[('test_ids', '=', test_id), ('status', '=', 'active')]"
    )
    processing_notes = fields.Text(
        string="Processing Notes",
        placeholder="Enter step notes or anomalies here..."
    )

    # Stage 3: Results Fields
    result_details = fields.Text(
        string="Result Details",
        placeholder="Enter lab findings and values..."
    )
    lab_findings = fields.Text(
        string="Findings / Conclusions",
        placeholder="Doctor conclusions..."
    )
    result_pdf = fields.Binary(
        string="Lab Report PDF"
    )
    result_pdf_name = fields.Char(
        string="PDF Filename"
    )
    ai_summary = fields.Text(
        string="AI Summary",
        readonly=True
    )
    technician_id = fields.Many2one(
        "res.users",
        string="Technician",
        default=lambda self: self.env.user
    )
    date_completed = fields.Datetime(
        string="Completed Date",
        readonly=True
    )

    @api.constrains('status', 'sample_type', 'sample_details', 'equipment_id', 'result_details')
    def _check_stage_fields(self):
        for record in self:
            if record.status == 'collected':
                if not record.sample_type:
                    raise ValidationError(_("Sample Type is required for Sample Collected stage."))
                if not record.sample_details:
                    raise ValidationError(_("Sample Details are required for Sample Collected stage."))
            
            elif record.status == 'testing':
                if not record.sample_type or not record.sample_details:
                    raise ValidationError(_("Sample Type and Details are required before testing."))
                if not record.equipment_id:
                    raise ValidationError(_("Please specify the Equipment Used before starting testing stage."))
            
            elif record.status == 'completed':
                if not record.sample_type or not record.sample_details:
                    raise ValidationError(_("Sample collection details are required before completing the test."))
                if not record.equipment_id:
                    raise ValidationError(_("Equipment used is required before completing the test."))
                if not record.result_details:
                    raise ValidationError(_("Please specify the Result Details before completing the test."))

    @api.onchange('status')
    def _onchange_status(self):
        for record in self:
            if record.status == 'collected':
                if not record.sample_collected_at:
                    record.sample_collected_at = fields.Datetime.now()
            elif record.status == 'testing':
                if not record.sample_collected_at:
                    record.sample_collected_at = fields.Datetime.now()
                if not record.process_start_datetime:
                    record.process_start_datetime = fields.Datetime.now()
            elif record.status == 'completed':
                if not record.sample_collected_at:
                    record.sample_collected_at = fields.Datetime.now()
                if not record.process_start_datetime:
                    record.process_start_datetime = fields.Datetime.now()
                if not record.date_completed:
                    record.date_completed = fields.Datetime.now()

    @api.model
    def create(self, vals):
        record = super(HospitalLabProcessing, self).create(vals)
        record._sync_to_request_line()
        return record

    def _sync_to_request_line(self):
        for record in self:
            if record.request_line_id:
                vals = {
                    'result_pdf': record.result_pdf,
                    'result_pdf_name': record.result_pdf_name,
                    'ai_summary': record.ai_summary,
                }
                if record.status in ('completed', 'cancelled'):
                    vals['status'] = record.status
                record.request_line_id.write(vals)

    def write(self, vals):
        if 'status' in vals:
            if vals['status'] == 'collected':
                vals['sample_collected_at'] = fields.Datetime.now()
            elif vals['status'] == 'testing':
                vals['process_start_datetime'] = fields.Datetime.now()
                # If they skip 'collected' state directly to 'testing', make sure collection time is set
                for record in self:
                    if not record.sample_collected_at:
                        vals['sample_collected_at'] = fields.Datetime.now()
            elif vals['status'] == 'completed':
                vals['date_completed'] = fields.Datetime.now()
                # Ensure previous timestamps are set if skipped
                for record in self:
                    if not record.sample_collected_at:
                        vals['sample_collected_at'] = fields.Datetime.now()
                    if not record.process_start_datetime:
                        vals['process_start_datetime'] = fields.Datetime.now()

        res = super(HospitalLabProcessing, self).write(vals)
        self._sync_to_request_line()
        return res

    def action_generate_ai_summary(self):
        self.ensure_one()
        if not self.result_pdf:
            raise UserError(_("Please upload a PDF file first before generating AI summary."))

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

        # Get base64 data string
        pdf_base64 = self.result_pdf.decode('utf-8') if isinstance(self.result_pdf, bytes) else self.result_pdf

        payload = {
            "contents": [{
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "application/pdf",
                            "data": pdf_base64
                        }
                    },
                    {
                        "text": "Summarize this medical lab report. Focus on key findings, abnormal values, and clinical conclusions. Format the response nicely with clean Markdown bullet points, keeping it professional and structured."
                    }
                ]
            }]
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
                        summary = res_data['candidates'][0]['content']['parts'][0]['text']
                        self.ai_summary = summary
                        success = True
                        break
                    except (KeyError, IndexError):
                        last_error = _("Received an unexpected response structure from Gemini API.")
                else:
                    try:
                        last_error = response.json().get('error', {}).get('message', response.text)
                    except Exception:
                        last_error = response.text
            except requests.exceptions.RequestException as e:
                last_error = str(e)

        if not success:
            raise UserError(_("Gemini API Error (Tried multiple models): %s") % last_error)

    def action_quick_collect(self):
        for record in self:
            if record.status != 'pending':
                continue
            # Determine appropriate sample type based on test name
            test_name = (record.test_id.name or "").lower()
            sample_type = 'blood'
            if 'urine' in test_name:
                sample_type = 'urine'
            elif 'swab' in test_name or 'covid' in test_name:
                sample_type = 'swab'
            elif 'saliva' in test_name:
                sample_type = 'saliva'
            
            record.write({
                'status': 'collected',
                'sample_type': sample_type,
                'sample_details': f'Standard {sample_type.capitalize()} Sample'
            })
        return True

    def action_quick_start(self):
        for record in self:
            if record.status != 'collected':
                continue
            # Search for active equipment for this test
            eq = self.env['hospital.lab.equipment'].search([
                ('test_ids', '=', record.test_id.id),
                ('status', '=', 'active')
            ], limit=1)
            if not eq:
                # If no matching equipment, find any active equipment
                eq = self.env['hospital.lab.equipment'].search([('status', '=', 'active')], limit=1)
            
            record.write({
                'status': 'testing',
                'equipment_id': eq.id if eq else False
            })
        return True

    def action_quick_complete(self):
        self.ensure_one()
        return {
            'name': 'Lab Test Results & Findings',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.lab.processing',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class HospitalLabQueueDashboard(models.TransientModel):
    _name = "hospital.lab.queue.dashboard"
    _description = "AI Smart Lab Queue Dashboard"
    
    dashboard_html = fields.Html(string="Dashboard HTML", compute="_compute_dashboard_html")
    active_processing_ids = fields.Many2many(
        "hospital.lab.processing",
        string="Active Lab Tests",
        compute="_compute_active_processings"
    )
    
    def _compute_active_processings(self):
        for record in self:
            active = self.env['hospital.lab.processing'].search([
                ('status', 'in', ['pending', 'collected', 'testing'])
            ])
            
            def sort_key(lp):
                status_weight = {'testing': 0, 'collected': 1, 'pending': 2}.get(lp.status, 3)
                prio_val = lp.op_id.ai_priority or lp.op_id.priority or 'low'
                prio_weight = {'emergency': 0, 'high': 1, 'urgent': 1, 'medium': 2, 'semi_urgent': 2, 'low': 3, 'normal': 3}.get(prio_val, 3)
                
                test_name = (lp.test_id.name or "").lower()
                if 'troponin' in test_name:
                    test_weight = 0
                elif 'dengue' in test_name or 'ns1' in test_name or 'malaria' in test_name:
                    test_weight = 1
                elif 'cbc' in test_name or 'crp' in test_name or 'wbc' in test_name:
                    test_weight = 2
                else:
                    test_weight = 3
                    
                created_id = lp.id
                return (status_weight, prio_weight, test_weight, created_id)
                
            record.active_processing_ids = active.sorted(key=sort_key)

    def _compute_dashboard_html(self):
        for record in self:
            active_tests = self.env['hospital.lab.processing'].search([
                ('status', 'in', ['pending', 'collected', 'testing'])
            ])
            
            total_active = len(active_tests)
            testing_count = len(active_tests.filtered(lambda t: t.status == 'testing'))
            collected_count = len(active_tests.filtered(lambda t: t.status == 'collected'))
            pending_count = len(active_tests.filtered(lambda t: t.status == 'pending'))
            
            critical_count = len(active_tests.filtered(
                lambda t: (t.op_id.ai_priority or t.op_id.priority) == 'emergency' or 'troponin' in (t.test_id.name or "").lower()
            ))
            
            running_tests = active_tests.filtered(lambda t: t.status == 'testing')
            running_str = "None (Ready for next sample)"
            if running_tests:
                running_str = f"🧪 {running_tests[0].test_id.name} ({running_tests[0].patient_id.name})"
                
            next_tests = record.active_processing_ids.filtered(lambda t: t.status != 'testing')
            next_str = "No pending tests"
            if next_tests:
                next_str = f"⏳ {next_tests[0].test_id.name} ({next_tests[0].patient_id.name})"
                
            record.dashboard_html = f"""
<div class="smart-lab-dashboard" style="font-family: 'Outfit', 'Inter', sans-serif; background: #0b1329; padding: 24px; border-radius: 16px; color: #f8fafc; margin-bottom: 24px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);">
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px;">
        <div>
            <h2 style="margin: 0; font-size: 24px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 8px;">
                <span>🔬</span> NovaCare Smart Lab Queue Dashboard
            </h2>
            <p style="margin: 4px 0 0 0; font-size: 14px; color: #94a3b8;">AI-optimized specimen processing order and queue sequence manager</p>
        </div>
        <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 6px 12px; border-radius: 9999px; font-size: 12px; color: #38bdf8; font-weight: 600;">
            🤖 AI Assisted Dispatch
        </div>
    </div>
    
    <!-- Stats Cards Grid -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px;">
        <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid #1e293b; border-radius: 12px; padding: 16px;">
            <span style="color: #94a3b8; font-size: 12px; font-weight: 600; text-transform: uppercase;">Active Queue</span>
            <div style="font-size: 28px; font-weight: 700; color: #f1f5f9; margin-top: 8px; display: flex; align-items: center; gap: 8px;">
                <span>👥</span> {total_active} <span style="font-size: 14px; font-weight: 400; color: #64748b;">Tests</span>
            </div>
            <div style="margin-top: 8px; font-size: 12px; color: #ef4444; font-weight: 600; display: flex; align-items: center; gap: 4px;">
                <span>🚨</span> {critical_count} Critical Priority
            </div>
        </div>
        
        <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 12px; padding: 16px;">
            <span style="color: #10b981; font-size: 12px; font-weight: 600; text-transform: uppercase;">Now Running</span>
            <div style="font-size: 15px; font-weight: 600; color: #f1f5f9; margin-top: 14px; word-break: break-all;">
                {running_str}
            </div>
            <div style="margin-top: 8px; font-size: 12px; color: #64748b;">
                Testing Status: {testing_count} in progress
            </div>
        </div>
        
        <div style="background: rgba(245, 158, 11, 0.05); border: 1px solid rgba(245, 158, 11, 0.2); border-radius: 12px; padding: 16px;">
            <span style="color: #f59e0b; font-size: 12px; font-weight: 600; text-transform: uppercase;">Next Up (Recommended)</span>
            <div style="font-size: 15px; font-weight: 600; color: #f1f5f9; margin-top: 14px; word-break: break-all;">
                {next_str}
            </div>
            <div style="margin-top: 8px; font-size: 12px; color: #64748b;">
                Samples: {collected_count} collected, {pending_count} pending
            </div>
        </div>
    </div>
    
    <div style="background: rgba(30, 41, 59, 0.3); border: 1px solid #1e293b; border-radius: 12px; padding: 16px;">
        <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 15px; font-weight: 600; color: #f8fafc; display: flex; align-items: center; gap: 6px;">
            <span>🤖</span> AI Lab Operations Assistant
        </h3>
        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #cbd5e1; line-height: 1.6;">
            <li>Priority sequencing is calculated dynamically from ESI patient emergency status and clinical test urgencies (Troponin > Infection > Routine).</li>
            <li>Always collect samples for pending tests before processing routine tests.</li>
            <li>Click <strong>Start Testing</strong> to automatically allocate compatibly mapped equipment and begin test runs.</li>
        </ul>
    </div>
</div>
"""

    @api.model
    def action_open_lab_dashboard(self):
        record = self.create({})
        return {
            'name': 'Smart Lab Queue Dashboard',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.lab.queue.dashboard',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }
