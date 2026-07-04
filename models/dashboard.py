from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class HospitalDashboard(models.TransientModel):
    _name = "hospital.dashboard"
    _description = "OxyCure Dashboard"

    name = fields.Char(string="Title", default="OxyCure Live Dashboard")
    dashboard_html = fields.Html(string="Content", compute="_compute_dashboard_html", sanitize=False)

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        return {
            'name': _('Dashboard'),
            'type': 'ir.actions.act_window',
            'res_model': 'hospital.dashboard',
            'view_mode': 'form',
            'res_id': dashboard.id,
            'target': 'current',
            'context': {'form_view_initial_mode': 'view'},
        }

    def _compute_dashboard_html(self):
        for record in self:
            # 1. Daily patient count
            today_start = fields.Datetime.to_string(fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
            today_end = fields.Datetime.to_string(fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999))
            
            op_today = self.env['hospital.op'].search([
                ('registration_datetime', '>=', today_start),
                ('registration_datetime', '<=', today_end)
            ])
            apt_today = self.env['hospital.appointment'].search([
                ('appointment_date', '=', fields.Date.today())
            ])
            
            patient_ids = set(op_today.mapped('patient_id.id') + apt_today.mapped('patient_id.id'))
            daily_patient_count = len(patient_ids)
            
            # 2. OP visits today
            op_visits = len(op_today)
            
            # 3. Appointments today
            appointments_today = len(apt_today)
            
            # 4. Doctors on duty (available status)
            doctors_on_duty = self.env['hospital.doctor'].search_count([('status', '=', 'available')])
            
            # 5. Lab requests today
            lab_requests = self.env['hospital.lab.request'].search_count([
                ('request_datetime', '>=', today_start),
                ('request_datetime', '<=', today_end)
            ])
            
            # 6. Pharmacy sales today (total paid medicine bills today)
            paid_med_bills = self.env['hospital.billing'].search([
                ('billing_type', '=', 'medicine'),
                ('payment_status', '=', 'paid'),
                ('write_date', '>=', today_start),
                ('write_date', '<=', today_end)
            ])
            pharmacy_sales = sum(paid_med_bills.mapped('amount_total'))
            
            # 7. Revenue summary (total paid invoices today)
            paid_bills_today = self.env['hospital.billing'].search([
                ('payment_status', '=', 'paid'),
                ('write_date', '>=', today_start),
                ('write_date', '<=', today_end)
            ])
            total_revenue = sum(paid_bills_today.mapped('amount_total'))
            
            # 8. Pending payments
            draft_bills = self.env['hospital.billing'].search([('payment_status', '=', 'draft')])
            pending_payments_count = len(draft_bills)
            pending_payments_amount = sum(draft_bills.mapped('amount_total'))
            
            # 9. Low stock medicines
            low_stock_medicines = self.env['hospital.medicine'].search([
                ('qty_available', '<=', 10) # default threshold 10
            ])
            low_stock_count = len(low_stock_medicines)
            
            # 10. Expired/Expiring medicine batches
            today_date = fields.Date.today()
            expired_batches = self.env['hospital.medicine.batch'].search([
                ('qty_remaining', '>', 0),
                ('expiry_date', '<', today_date)
            ])
            expired_count = len(expired_batches)

            thirty_days_later = today_date + timedelta(days=30)
            expiring_batches = self.env['hospital.medicine.batch'].search([
                ('qty_remaining', '>', 0),
                ('expiry_date', '>=', today_date),
                ('expiry_date', '<=', thirty_days_later)
            ])
            expiring_count = len(expiring_batches)

            expired_list_str = "\n".join([
                f"- {b.medicine_id.name} (Batch: {b.name}, Qty: {b.qty_remaining}, Expired On: {b.expiry_date})"
                for b in expired_batches
            ]) or "None"

            expiring_list_str = "\n".join([
                f"- {b.medicine_id.name} (Batch: {b.name}, Qty: {b.qty_remaining}, Expires On: {b.expiry_date})"
                for b in expiring_batches
            ]) or "None"

            # 11. AI Insight via Gemini API
            ai_insight = "OxyCure AI Insight is analyzing hospital database..."
            api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
            if not api_key:
                import os
                api_key = os.environ.get('GEMINI_API_KEY')
            
            if api_key:
                try:
                    import requests
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [{
                            "parts": [
                                {
                                    "text": (
                                        f"You are an AI Hospital Operations assistant. Given the following current hospital dashboard statistics:\n"
                                        f"- Daily Patient Count: {daily_patient_count}\n"
                                        f"- OP Visits Today: {op_visits}\n"
                                        f"- Appointments Today: {appointments_today}\n"
                                        f"- Doctors on Duty: {doctors_on_duty}\n"
                                        f"- Lab Requests: {lab_requests}\n"
                                        f"- Pharmacy Sales: ${pharmacy_sales:.2f}\n"
                                        f"- Total Revenue: ${total_revenue:.2f}\n"
                                        f"- Pending Payments: {pending_payments_count} (${pending_payments_amount:.2f})\n"
                                        f"- Low Stock Medicines: {low_stock_count}\n"
                                        f"- Expired Medicine Batches (stock > 0):\n{expired_list_str}\n"
                                        f"- Expiring Medicine Batches (next 30 days, stock > 0):\n{expiring_list_str}\n\n"
                                        f"Provide a brief, concise, and professional operational insight (3-4 sentences max) summarizing hospital performance, highlighting any urgent concerns (e.g. low stock, pending payments, or high patient-to-doctor ratio), and explicitly calling out the specific expired or expiring medicines that need attention and recommending what action to take (e.g. disposal or prioritizing dispensing)."
                                    )
                                }
                            ]
                        }]
                    }
                    
                    models_to_try = [
                        "gemini-2.5-flash",
                        "gemini-3.5-flash",
                        "gemini-2.0-flash",
                        "gemini-2.5-pro",
                        "gemini-2.0-flash-lite",
                        "gemini-flash-latest",
                        "gemini-pro-latest"
                    ]
                    
                    success = False
                    last_error = "No response"
                    for model in models_to_try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                        try:
                            response = requests.post(url, json=payload, headers=headers, timeout=30)
                            if response.status_code == 200:
                                res_data = response.json()
                                ai_insight = res_data['candidates'][0]['content']['parts'][0]['text']
                                success = True
                                break
                            else:
                                try:
                                    last_error = response.json().get('error', {}).get('message', response.text)
                                except Exception:
                                    last_error = response.text
                        except Exception as ex:
                            last_error = str(ex)
                    
                    if not success:
                        ai_insight = f"Failed to load AI Insight (Gemini API returned error: {last_error})."
                except Exception as e:
                    ai_insight = f"Failed to connect to AI engine: {str(e)}"
            else:
                ai_insight = "AI Insight is unavailable. Please configure the Gemini API Key in system parameters."

            # Build Expired Batches Table
            if expired_batches:
                expired_rows = ""
                for b in expired_batches:
                    expired_rows += f"""
                    <tr style="border-bottom: 1px solid #f1f5f9; color: #1e293b;">
                        <td style="padding: 10px 4px; font-weight: 500;">{b.medicine_id.name}</td>
                        <td style="padding: 10px 4px; color: #4b5563;">{b.name}</td>
                        <td style="padding: 10px 4px; text-align: right; font-weight: 600; color: #ef4444;">{b.qty_remaining}</td>
                        <td style="padding: 10px 4px; text-align: right; color: #ef4444;">{b.expiry_date.strftime('%Y-%m-%d')}</td>
                    </tr>
                    """
                expired_table_html = f"""
                <div style="max-height: 240px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 2px solid #f1f5f9; color: #64748b; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;">
                                <th style="padding: 8px 4px;">Medicine</th>
                                <th style="padding: 8px 4px;">Batch</th>
                                <th style="padding: 8px 4px; text-align: right;">Qty</th>
                                <th style="padding: 8px 4px; text-align: right;">Expired Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {expired_rows}
                        </tbody>
                    </table>
                </div>
                """
            else:
                expired_table_html = """
                <div style="padding: 20px; text-align: center; color: #10b981; font-weight: 500; font-size: 13px; background: #f0fdf4; border-radius: 8px; border: 1px dashed #bbf7d0;">
                    ✓ No expired medicines in stock.
                </div>
                """

            # Build Expiring Batches Table
            if expiring_batches:
                expiring_rows = ""
                for b in expiring_batches:
                    expiring_rows += f"""
                    <tr style="border-bottom: 1px solid #f1f5f9; color: #1e293b;">
                        <td style="padding: 10px 4px; font-weight: 500;">{b.medicine_id.name}</td>
                        <td style="padding: 10px 4px; color: #4b5563;">{b.name}</td>
                        <td style="padding: 10px 4px; text-align: right; font-weight: 600; color: #d97706;">{b.qty_remaining}</td>
                        <td style="padding: 10px 4px; text-align: right; color: #d97706;">{b.expiry_date.strftime('%Y-%m-%d')}</td>
                    </tr>
                    """
                expiring_table_html = f"""
                <div style="max-height: 240px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 2px solid #f1f5f9; color: #64748b; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;">
                                <th style="padding: 8px 4px;">Medicine</th>
                                <th style="padding: 8px 4px;">Batch</th>
                                <th style="padding: 8px 4px; text-align: right;">Qty</th>
                                <th style="padding: 8px 4px; text-align: right;">Expiry Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {expiring_rows}
                        </tbody>
                    </table>
                </div>
                """
            else:
                expiring_table_html = """
                <div style="padding: 20px; text-align: center; color: #10b981; font-weight: 500; font-size: 13px; background: #f0fdf4; border-radius: 8px; border: 1px dashed #bbf7d0;">
                    ✓ No medicines expiring in the next 30 days.
                </div>
                """

            # Constructing Premium Dashboard HTML
            html = f"""
            <div class="oxycure-dashboard-container" style="background-color: #f8fafc; padding: 24px; font-family: 'Inter', sans-serif;">
                
                <!-- Dashboard Header -->
                <div style="background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%); padding: 32px; border-radius: 16px; margin-bottom: 24px; color: white; box-shadow: 0 10px 15px -3px rgba(59, 130, 246, 0.2);">
                    <h1 style="margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">OxyCure Command Center</h1>
                    <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 14px;">Real-time clinical, operational, and financial indicators</p>
                </div>

                <!-- AI Insight Card -->
                <div style="background: white; border-radius: 16px; padding: 24px; margin-bottom: 24px; border-left: 6px solid #8b5cf6; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); position: relative; overflow: hidden;">
                    <div style="position: absolute; right: -20px; top: -20px; font-size: 100px; color: #f3e8ff; opacity: 0.5; font-weight: 900; pointer-events: none; font-family: 'Courier New', monospace;">AI</div>
                    <h3 style="margin: 0 0 8px 0; color: #6d28d9; font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 20px;">✨</span> Real-time AI Insight
                    </h3>
                    <p style="margin: 0; color: #4b5563; font-size: 14px; line-height: 1.6; font-style: italic;">
                        "{ai_insight}"
                    </p>
                </div>

                <!-- KPI Grid -->
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; margin-bottom: 24px;">
                    
                    <!-- Daily Patient Count -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; transition: transform 0.2s;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Daily Patients</div>
                        <div style="font-size: 28px; font-weight: 700; color: #1e293b; margin: 8px 0;">{daily_patient_count}</div>
                        <div style="font-size: 12px; color: #10b981; font-weight: 500;">Unique visits today</div>
                    </div>

                    <!-- OP Visits -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">OP Registrations</div>
                        <div style="font-size: 28px; font-weight: 700; color: #1e293b; margin: 8px 0;">{op_visits}</div>
                        <div style="font-size: 12px; color: #3b82f6; font-weight: 500;">Active outpatients today</div>
                    </div>

                    <!-- Appointments Today -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Appointments Today</div>
                        <div style="font-size: 28px; font-weight: 700; color: #1e293b; margin: 8px 0;">{appointments_today}</div>
                        <div style="font-size: 12px; color: #6366f1; font-weight: 500;">Scheduled appointments</div>
                    </div>

                    <!-- Doctors on Duty -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Doctors on Duty</div>
                        <div style="font-size: 28px; font-weight: 700; color: #1e293b; margin: 8px 0;">{doctors_on_duty}</div>
                        <div style="font-size: 12px; color: #10b981; font-weight: 500;">Available status</div>
                    </div>

                    <!-- Lab Requests -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Lab Requests</div>
                        <div style="font-size: 28px; font-weight: 700; color: #1e293b; margin: 8px 0;">{lab_requests}</div>
                        <div style="font-size: 12px; color: #f59e0b; font-weight: 500;">Requests logged today</div>
                    </div>

                    <!-- Pharmacy Sales -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Pharmacy Sales</div>
                        <div style="font-size: 28px; font-weight: 700; color: #1e293b; margin: 8px 0;">${pharmacy_sales:.2f}</div>
                        <div style="font-size: 12px; color: #10b981; font-weight: 500;">Paid medicine invoices</div>
                    </div>

                    <!-- Revenue Summary -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Total Revenue Today</div>
                        <div style="font-size: 28px; font-weight: 700; color: #1e293b; margin: 8px 0;">${total_revenue:.2f}</div>
                        <div style="font-size: 12px; color: #10b981; font-weight: 500;">Total cash flows collected</div>
                    </div>

                    <!-- Pending Payments -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #ef4444; border-left: 4px solid #ef4444;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Pending Payments</div>
                        <div style="font-size: 28px; font-weight: 700; color: #ef4444; margin: 8px 0;">{pending_payments_count}</div>
                        <div style="font-size: 12px; color: #64748b; font-weight: 500;">Total draft: ${pending_payments_amount:.2f}</div>
                    </div>

                    <!-- Low Stock Medicines -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; border-left: 4px solid #f59e0b;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Low Stock Medicines</div>
                        <div style="font-size: 28px; font-weight: 700; color: #f59e0b; margin: 8px 0;">{low_stock_count}</div>
                        <div style="font-size: 12px; color: #64748b; font-weight: 500;">Stock level <= 10 units</div>
                    </div>

                    <!-- Expiring Medicines -->
                    <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; border-left: 4px solid #ef4444;">
                        <div style="font-size: 12px; text-transform: uppercase; color: #64748b; font-weight: 600; letter-spacing: 0.5px;">Expiring Medicines</div>
                        <div style="font-size: 28px; font-weight: 700; color: #ef4444; margin: 8px 0;">{expiring_count}</div>
                        <div style="font-size: 12px; color: #64748b; font-weight: 500;">Expiring within 30 days</div>
                    </div>

                </div>

                <!-- Expiry Alerts Panels -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; margin-top: 24px;">
                    
                    <!-- Expired Medicines Table -->
                    <div style="background: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; border-top: 6px solid #ef4444;">
                        <h3 style="margin: 0 0 16px 0; color: #b91c1c; font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 20px;">⚠️</span> Expired Medicines ({expired_count})
                        </h3>
                        {expired_table_html}
                    </div>

                    <!-- Expiring Medicines Table -->
                    <div style="background: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; border-top: 6px solid #f59e0b;">
                        <h3 style="margin: 0 0 16px 0; color: #b45309; font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 20px;">⏳</span> Expiring Soon (Next 30 Days) ({expiring_count})
                        </h3>
                        {expiring_table_html}
                    </div>
                    
                </div>

                <!-- Footer / Refresh Note -->
                <div style="text-align: right; font-size: 11px; color: #94a3b8; font-weight: 500; margin-top: 24px;">
                    🔄 Automatically updates in real-time.
                </div>

            </div>
            """
            record.dashboard_html = html
