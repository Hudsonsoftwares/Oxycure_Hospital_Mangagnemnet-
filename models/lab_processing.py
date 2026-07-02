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
    equipment_used = fields.Char(
        string="Equipment Used",
        placeholder="e.g. Centrifuge model 500, Analyzer CX"
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

    @api.constrains('status', 'sample_type', 'sample_details', 'equipment_used', 'result_details')
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
                if not record.equipment_used:
                    raise ValidationError(_("Please specify the Equipment Used before starting testing stage."))
            
            elif record.status == 'completed':
                if not record.sample_type or not record.sample_details:
                    raise ValidationError(_("Sample collection details are required before completing the test."))
                if not record.equipment_used:
                    raise ValidationError(_("Equipment used is required before completing the test."))
                if not record.result_details:
                    raise ValidationError(_("Please specify the Result Details before completing the test."))

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

        if 'status' in vals:
            for record in self:
                if record.request_line_id:
                    if vals['status'] == 'completed':
                        record.request_line_id.write({'status': 'completed'})
                    elif vals['status'] == 'cancelled':
                        record.request_line_id.write({'status': 'cancelled'})
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

        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}

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

            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                res_data = response.json()
                try:
                    summary = res_data['candidates'][0]['content']['parts'][0]['text']
                    self.ai_summary = summary
                except (KeyError, IndexError):
                    raise UserError(_("Received an unexpected response structure from Gemini API."))
            else:
                try:
                    err_msg = response.json().get('error', {}).get('message', response.text)
                except Exception:
                    err_msg = response.text
                raise UserError(_("Gemini API Error: %s") % err_msg)

        except requests.exceptions.RequestException as e:
            raise UserError(_("Failed to connect to Gemini API: %s") % str(e))
