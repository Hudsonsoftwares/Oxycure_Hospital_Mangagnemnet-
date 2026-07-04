from odoo import models, fields, api, _

class HospitalPharmacyAlert(models.Model):
    _name = "hospital.pharmacy.alert"
    _description = "Pharmacy Inventory Alert"
    _order = "date_created desc, id desc"

    name = fields.Char(
        string="Alert Title",
        required=True
    )
    alert_type = fields.Selection([
        ("expiry", "Near Expiry"),
        ("low_stock", "Low Stock")
    ],
        string="Alert Type",
        required=True
    )
    medicine_id = fields.Many2one(
        "hospital.medicine",
        string="Medicine"
    )
    batch_id = fields.Many2one(
        "hospital.medicine.batch",
        string="Batch"
    )
    message = fields.Text(
        string="Alert Message",
        required=True
    )
    date_created = fields.Date(
        string="Date Triggered",
        default=fields.Date.context_today,
        required=True
    )
    status = fields.Selection([
        ("active", "Active"),
        ("resolved", "Resolved")
    ],
        string="Status",
        default="active",
        required=True
    )

    def action_resolve(self):
        self.write({"status": "resolved"})

    @api.model
    def cron_generate_alerts(self):
        # 1. Check for Low Stock
        medicines = self.env["hospital.medicine"].search([("status", "=", "active")])
        for med in medicines:
            # Determine threshold
            threshold = med.minimum_stock or med.reorder_level or 10
            if med.qty_available <= threshold:
                # Check if active alert already exists
                existing = self.search([
                    ("medicine_id", "=", med.id),
                    ("alert_type", "=", "low_stock"),
                    ("status", "=", "active")
                ], limit=1)
                if not existing:
                    self.create({
                        "name": f"Low Stock Alert: {med.name}",
                        "alert_type": "low_stock",
                        "medicine_id": med.id,
                        "message": f"Medicine '{med.name}' is running low on stock. Current quantity: {med.qty_available} (Threshold: {threshold}).",
                        "status": "active"
                    })
                
                # Trigger AI Auto-Restocking if no draft PO line exists for this medicine
                existing_draft_line = self.env["hospital.medicine.purchase.line"].search([
                    ("medicine_id", "=", med.id),
                    ("purchase_id.state", "=", "draft")
                ], limit=1)
                if not existing_draft_line:
                    try:
                        med.action_ai_auto_restock()
                    except Exception:
                        pass
            else:
                # If stock has been replenished, auto-resolve the active alert
                active_alerts = self.search([
                    ("medicine_id", "=", med.id),
                    ("alert_type", "=", "low_stock"),
                    ("status", "=", "active")
                ])
                if active_alerts:
                    active_alerts.write({"status": "resolved"})

        # 2. Check for Near Expiry (within 30 days)
        from datetime import timedelta
        thirty_days_later = fields.Date.today() + timedelta(days=30)
        batches = self.env["hospital.medicine.batch"].search([
            ("qty_remaining", ">", 0),
            ("expiry_date", "<=", thirty_days_later)
        ])
        for batch in batches:
            existing = self.search([
                ("batch_id", "=", batch.id),
                ("alert_type", "=", "expiry"),
                ("status", "=", "active")
            ], limit=1)
            if not existing:
                is_expired = batch.expiry_date <= fields.Date.today()
                status_txt = "expired" if is_expired else "expiring soon"
                self.create({
                    "name": f"Expiry Alert: Batch {batch.name} - {batch.medicine_id.name}",
                    "alert_type": "expiry",
                    "medicine_id": batch.medicine_id.id,
                    "batch_id": batch.id,
                    "message": f"Batch {batch.name} of medicine '{batch.medicine_id.name}' is {status_txt} ({batch.expiry_date}). Remaining quantity: {batch.qty_remaining}.",
                    "status": "active"
                })
        
        # Auto-resolve expiry alerts for batches that have been fully consumed/disposed
        empty_batch_alerts = self.search([
            ("alert_type", "=", "expiry"),
            ("status", "=", "active"),
            ("batch_id.qty_remaining", "=", 0)
        ])
        if empty_batch_alerts:
            empty_batch_alerts.write({"status": "resolved"})
