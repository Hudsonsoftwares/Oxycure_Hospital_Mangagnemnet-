from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HospitalBilling(models.Model):
    _name = "hospital.billing"
    _description = "Hospital Billing / Invoice"
    _rec_name = "name"
    _order = "id desc"

    _sql_constraints = [
        ('billing_name_unique', 'unique(name)', 'The Invoice Number must be unique!'),
    ]

    name = fields.Char(
        string="Invoice Number",
        required=True,
        readonly=True,
        copy=False,
        default="New"
    )
    op_id = fields.Many2one(
        "hospital.op",
        string="OP Visit",
        required=False,
        ondelete="cascade"
    )
    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Appointment",
        ondelete="set null"
    )
    patient_id = fields.Many2one(
        "hospital.patient",
        string="Patient",
        compute="_compute_patient_doctor",
        store=True,
        readonly=True
    )
    doctor_id = fields.Many2one(
        "hospital.doctor",
        string="Doctor",
        compute="_compute_patient_doctor",
        store=True,
        readonly=True
    )
    billing_date = fields.Date(
        string="Billing Date",
        default=fields.Date.today,
        required=True
    )
    payment_status = fields.Selection([
        ('draft', 'Draft / Unpaid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ],
        string="Status",
        default="draft",
        required=True
    )
    billing_type = fields.Selection([
        ('op', 'OP Consultation & Labs'),
        ('medicine', 'Pharmacy / Medicine')
    ],
        string="Billing Type",
        default="op",
        required=True
    )
    bill_line_ids = fields.One2many(
        "hospital.billing.line",
        "billing_id",
        string="Bill Lines"
    )
    amount_total = fields.Float(
        string="Total Amount",
        compute="_compute_amounts",
        store=True
    )

    @api.depends('op_id.patient_id', 'op_id.doctor_id', 'appointment_id.patient_id', 'appointment_id.doctor_id')
    def _compute_patient_doctor(self):
        for record in self:
            if record.op_id:
                record.patient_id = record.op_id.patient_id
                record.doctor_id = record.op_id.doctor_id
            elif record.appointment_id:
                record.patient_id = record.appointment_id.patient_id
                record.doctor_id = record.appointment_id.doctor_id
            else:
                record.patient_id = False
                record.doctor_id = False

    @api.depends('bill_line_ids.subtotal')
    def _compute_amounts(self):
        for record in self:
            record.amount_total = sum(line.subtotal for line in record.bill_line_ids)

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("hospital.billing") or "New"
        return super(HospitalBilling, self).create(vals)

    def action_pay_bill(self):
        for record in self:
            if record.payment_status == 'draft':
                record.write({'payment_status': 'paid'})

    def action_print_invoice(self):
        self.ensure_one()
        return self.env.ref('hospital_management.action_report_hospital_billing').report_action(self)

    def action_send_email(self):
        self.ensure_one()
        if not self.patient_id.email:
            raise ValidationError(_("The patient does not have an email address configured. Please update their profile first."))
        template = self.env.ref('hospital_management.email_template_hospital_billing', raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)
        return True

    def write(self, vals):
        res = super(HospitalBilling, self).write(vals)
        if 'payment_status' in vals and vals['payment_status'] == 'paid':
            for record in self:
                if record.billing_type == 'op':
                    if record.op_id:
                        record.op_id.write({'billing_completed': True})
                        for line in record.bill_line_ids:
                            if line.lab_line_id:
                                line.lab_line_id.write({'status': 'billed'})
                                existing = self.env['hospital.lab.processing'].search([
                                    ('request_line_id', '=', line.lab_line_id.id)
                                ])
                                if not existing:
                                    self.env['hospital.lab.processing'].create({
                                        'op_id': record.op_id.id,
                                        'test_id': line.lab_line_id.test_id.id,
                                        'request_line_id': line.lab_line_id.id,
                                        'status': 'pending',
                                    })
                    elif record.appointment_id:
                        existing_op = self.env['hospital.op'].search([
                            ('appointment_id', '=', record.appointment_id.id)
                        ], limit=1)
                        if not existing_op:
                            op = self.env['hospital.op'].with_context(no_sync_billing=True).create({
                                'appointment_id': record.appointment_id.id,
                                'patient_id': record.appointment_id.patient_id.id,
                                'doctor_id': record.appointment_id.doctor_id.id,
                                'visit_type': record.appointment_id.visit_type,
                                'token_number': record.appointment_id.token_number,
                                'chief_complaint': record.appointment_id.chief_complaint,
                                'status': 'checked_in',
                                'billing_completed': True,
                            })
                            # Use super to avoid triggering write logic recursively
                            super(HospitalBilling, record).write({'op_id': op.id})
                            record.appointment_id.write({'status': 'checked_in'})
                elif record.billing_type == 'medicine':
                    existing_request = self.env['hospital.pharmacy.request'].search([
                        ('billing_id', '=', record.id)
                    ], limit=1)
                    if existing_request:
                        existing_request.write({'status': 'paid'})
                    else:
                        pharmacy_request = self.env['hospital.pharmacy.request'].create({
                            'op_id': record.op_id.id,
                            'billing_id': record.id,
                            'status': 'paid',
                        })
                        for line in record.bill_line_ids:
                            if line.prescription_line_id:
                                self.env['hospital.pharmacy.request.line'].create({
                                    'request_id': pharmacy_request.id,
                                    'medicine_id': line.prescription_line_id.medicine_id.id,
                                    'qty': line.qty,
                                    'dosage': line.prescription_line_id.dosage,
                                    'duration': line.prescription_line_id.duration,
                                    'instructions': line.prescription_line_id.instructions,
                                    'prescription_line_id': line.prescription_line_id.id,
                                })
        return res


class HospitalBillingLine(models.Model):
    _name = "hospital.billing.line"
    _description = "Billing Line Item"

    billing_id = fields.Many2one(
        "hospital.billing",
        string="Billing Invoice",
        required=True,
        ondelete="cascade"
    )
    name = fields.Char(
        string="Description",
        required=True
    )
    price = fields.Float(
        string="Price / Fee",
        required=True
    )
    qty = fields.Integer(
        string="Quantity",
        default=1,
        required=True
    )
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True
    )
    lab_line_id = fields.Many2one(
        "hospital.lab.request.line",
        string="Lab Test Reference",
        ondelete="set null"
    )
    prescription_line_id = fields.Many2one(
        "hospital.prescription.line",
        string="Prescription Reference",
        ondelete="set null"
    )

    @api.depends('price', 'qty')
    def _compute_subtotal(self):
        for record in self:
            record.subtotal = record.price * record.qty


class HospitalBillingTv(models.TransientModel):
    _name = "hospital.billing.tv"
    _description = "Billing Queue Display TV"

    tv_html = fields.Html(string="TV Display HTML", compute="_compute_tv_html")

    def _compute_tv_html(self):
        for record in self:
            # Get today's start and end datetimes
            today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Find unpaid invoices (status = draft)
            unpaid_invoices = self.env['hospital.billing'].search([
                ('payment_status', '=', 'draft')
            ], order="id asc")
            
            # Find paid invoices processed today
            paid_invoices = self.env['hospital.billing'].search([
                ('payment_status', '=', 'paid'),
                ('write_date', '>=', today_start),
                ('write_date', '<=', today_end)
            ], order="write_date desc", limit=10)
            
            unpaid_list = []
            for inv in unpaid_invoices:
                # Resolve token
                token_val = False
                if inv.op_id:
                    token_val = inv.op_id.token_number
                elif inv.appointment_id:
                    token_val = inv.appointment_id.token_number
                
                token_str = f"T-{token_val:03d}" if token_val else f"INV-{inv.id:03d}"
                patient_name = inv.patient_id.name or "Patient"
                doctor_name = inv.doctor_id.name or "Doctor"
                amount = inv.amount_total
                billing_type_desc = "Consultation/Lab" if inv.billing_type == 'op' else "Pharmacy"
                
                # Colors based on billing type
                type_badge_style = "background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.2);" if inv.billing_type == 'op' else "background: rgba(168, 85, 247, 0.1); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.2);"
                
                unpaid_list.append(f"""
<div style="background: rgba(30, 41, 59, 0.4); border: 1.5px solid #334155; padding: 16px 20px; border-radius: 12px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <strong style="font-size: 24px; color: #f1f5f9;">{token_str}</strong>
        <span style="font-size: 18px; color: #e2e8f0; font-weight: 600;">${amount:.2f}</span>
    </div>
    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 14px; color: #94a3b8;">
        <span>👤 {patient_name}</span>
        <span>👨‍⚕️ Dr. {doctor_name}</span>
    </div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
        <span style="font-size: 11px; {type_badge_style} padding: 3px 8px; border-radius: 9999px; font-weight: 600;">
            {billing_type_desc}
        </span>
        <span style="font-size: 11px; background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2); padding: 3px 8px; border-radius: 9999px; font-weight: 600; display: flex; align-items: center; gap: 4px;">
            <span style="width: 5px; height: 5px; background: #f59e0b; border-radius: 50%; display: inline-block; animation: pulse_tv 1.5s infinite;"></span> AWAITING PAYMENT
        </span>
    </div>
</div>
""")

            paid_list = []
            for inv in paid_invoices:
                token_val = False
                if inv.op_id:
                    token_val = inv.op_id.token_number
                elif inv.appointment_id:
                    token_val = inv.appointment_id.token_number
                
                token_str = f"T-{token_val:03d}" if token_val else f"INV-{inv.id:03d}"
                patient_name = inv.patient_id.name or "Patient"
                amount = inv.amount_total
                
                paid_list.append(f"""
<div style="background: rgba(16, 185, 129, 0.05); border: 2px solid #10b981; padding: 18px 24px; border-radius: 14px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 8px 16px -4px rgba(16, 185, 129, 0.1);">
    <div>
        <strong style="font-size: 26px; color: #10b981; display: block; margin-bottom: 4px;">{token_str}</strong>
        <span style="font-size: 16px; color: #cbd5e1; font-weight: 500;">{patient_name}</span>
    </div>
    <div style="text-align: right;">
        <span style="font-size: 20px; color: #f8fafc; font-weight: 700; display: block; margin-bottom: 6px;">${amount:.2f}</span>
        <span style="font-size: 12px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1.5px solid rgba(16, 185, 129, 0.3); padding: 4px 12px; border-radius: 9999px; font-weight: 700; letter-spacing: 0.5px;">
            🟢 PAID &amp; CLEARED
        </span>
    </div>
</div>
""")

            unpaid_html = "".join(unpaid_list) if unpaid_list else '<div style="color: #64748b; text-align: center; padding: 40px; font-size: 15px;">No bills pending payment</div>'
            paid_html = "".join(paid_list) if paid_list else '<div style="color: #64748b; text-align: center; padding: 40px; font-size: 15px;">No payments received today</div>'

            record.tv_html = f"""
<div class="billing-tv-screen" style="font-family: 'Outfit', 'Inter', sans-serif; background: #090d16; border-radius: 20px; padding: 32px; box-shadow: inset 0 0 100px rgba(0,0,0,0.8), 0 20px 50px -12px rgba(0,0,0,0.5); min-height: 580px; color: #f8fafc;">
    <!-- Head Banner -->
    <div style="text-align: center; margin-bottom: 36px; border-bottom: 2px solid #1e293b; padding-bottom: 20px;">
        <h1 style="margin: 0; font-size: 32px; font-weight: 800; color: #eab308; letter-spacing: 1px; display: flex; align-items: center; justify-content: center; gap: 12px;">
            <span>💳</span> NOVACARE BILLING &amp; PAYMENTS STATUS
        </h1>
        <p style="margin: 6px 0 0 0; font-size: 15px; color: #64748b; font-weight: 500; text-transform: uppercase; letter-spacing: 2px;">Please proceed to the billing counter when your token is listed</p>
    </div>
    
    <!-- Split Screen Layout -->
    <div style="display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 32px;">
        <!-- Left: Awaiting Payment -->
        <div style="background: rgba(15, 23, 42, 0.6); border: 1.5px solid #1e293b; padding: 24px; border-radius: 16px;">
            <h2 style="margin-top: 0; margin-bottom: 20px; font-size: 20px; font-weight: 700; color: #f59e0b; border-bottom: 1.5px solid #334155; padding-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                <span style="animation: pulse_tv 1.5s infinite; color: #f59e0b; display: inline-block;">⏳</span> AWAITING BILL PAYMENT
            </h2>
            <div class="unpaid-list" style="max-height: 480px; overflow-y: auto;">
                {unpaid_html}
            </div>
        </div>
        
        <!-- Right: Recent Payments -->
        <div style="background: rgba(15, 23, 42, 0.8); border: 2.5px solid #10b981; padding: 24px; border-radius: 18px; box-shadow: 0 0 20px rgba(16, 185, 129, 0.05);">
            <h2 style="margin-top: 0; margin-bottom: 20px; font-size: 20px; font-weight: 800; color: #10b981; border-bottom: 2px solid rgba(16, 185, 129, 0.2); padding-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                <span>✅</span> RECENTLY PAID
            </h2>
            <div class="paid-list" style="max-height: 480px; overflow-y: auto;">
                {paid_html}
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
            'name': 'Billing Queue TV Display',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.billing.tv',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }


class HospitalBillingDashboard(models.TransientModel):
    _name = "hospital.billing.dashboard"
    _description = "Billing Counter Control Center"

    dashboard_html = fields.Html(string="Dashboard HTML", compute="_compute_dashboard_html")
    active_billing_ids = fields.Many2many(
        "hospital.billing",
        string="Pending Payments List",
        compute="_compute_active_billings"
    )

    def _compute_active_billings(self):
        for record in self:
            active = self.env['hospital.billing'].search([
                ('payment_status', '=', 'draft')
            ], order="id asc")
            record.active_billing_ids = active

    def _compute_dashboard_html(self):
        for record in self:
            # Unpaid/draft invoices
            unpaid_invoices = self.env['hospital.billing'].search([
                ('payment_status', '=', 'draft')
            ])
            
            op_unpaid = unpaid_invoices.filtered(lambda r: r.billing_type == 'op')
            pharmacy_unpaid = unpaid_invoices.filtered(lambda r: r.billing_type == 'medicine')
            
            op_count = len(op_unpaid)
            op_total = sum(op_unpaid.mapped('amount_total'))
            
            pharmacy_count = len(pharmacy_unpaid)
            pharmacy_total = sum(pharmacy_unpaid.mapped('amount_total'))
            
            # Paid today
            today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
            
            paid_today = self.env['hospital.billing'].search([
                ('payment_status', '=', 'paid'),
                ('write_date', '>=', today_start),
                ('write_date', '<=', today_end)
            ])
            
            collected_count = len(paid_today)
            collected_total = sum(paid_today.mapped('amount_total'))
            
            record.dashboard_html = f"""
<div class="billing-dashboard" style="font-family: 'Outfit', 'Inter', sans-serif; background: #0f172a; padding: 24px; border-radius: 16px; color: #f8fafc; margin-bottom: 24px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);">
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px;">
        <div>
            <h2 style="margin: 0; font-size: 24px; font-weight: 700; color: #eab308; display: flex; align-items: center; gap: 8px;">
                <span>💳</span> NovaCare Billing &amp; Counter Control Center
            </h2>
            <p style="margin: 4px 0 0 0; font-size: 14px; color: #94a3b8;">Real-time checkout, payments collection, and invoice clearance desk</p>
        </div>
        <div style="background: rgba(234, 179, 8, 0.1); border: 1px solid rgba(234, 179, 8, 0.2); padding: 6px 12px; border-radius: 9999px; font-size: 12px; color: #eab308; font-weight: 600;">
            ⚡ Payment Counter Mode
        </div>
    </div>
    
    <!-- Stats Cards Grid -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px;">
        <!-- Card 1: OP & Labs -->
        <div style="background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 12px; padding: 16px;">
            <span style="color: #38bdf8; font-size: 12px; font-weight: 600; text-transform: uppercase;">Pending OP &amp; Labs</span>
            <div style="font-size: 28px; font-weight: 700; color: #38bdf8; margin-top: 8px; display: flex; justify-content: space-between; align-items: baseline;">
                <span>{op_count} <span style="font-size: 14px; font-weight: 400; color: #64748b;">Invoices</span></span>
                <span style="font-size: 22px; color: #f1f5f9;">${op_total:.2f}</span>
            </div>
        </div>
        
        <!-- Card 2: Pharmacy / Medicine -->
        <div style="background: rgba(168, 85, 247, 0.05); border: 1px solid rgba(168, 85, 247, 0.2); border-radius: 12px; padding: 16px;">
            <span style="color: #c084fc; font-size: 12px; font-weight: 600; text-transform: uppercase;">Pending Pharmacy Bills</span>
            <div style="font-size: 28px; font-weight: 700; color: #c084fc; margin-top: 8px; display: flex; justify-content: space-between; align-items: baseline;">
                <span>{pharmacy_count} <span style="font-size: 14px; font-weight: 400; color: #64748b;">Invoices</span></span>
                <span style="font-size: 22px; color: #f1f5f9;">${pharmacy_total:.2f}</span>
            </div>
        </div>
        
        <!-- Card 3: Total Collected Today -->
        <div style="background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 12px; padding: 16px;">
            <span style="color: #10b981; font-size: 12px; font-weight: 600; text-transform: uppercase;">Collected Today</span>
            <div style="font-size: 28px; font-weight: 700; color: #10b981; margin-top: 8px; display: flex; justify-content: space-between; align-items: baseline;">
                <span>{collected_count} <span style="font-size: 14px; font-weight: 400; color: #64748b;">Payments</span></span>
                <span style="font-size: 24px; color: #f8fafc;">${collected_total:.2f}</span>
            </div>
        </div>
    </div>
</div>
"""

    @api.model
    def action_open_billing_dashboard(self):
        record = self.create({})
        return {
            'name': 'Billing Counter Control Center',
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.billing.dashboard',
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }
