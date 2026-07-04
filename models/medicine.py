from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HospitalMedicine(models.Model):
    _name = "hospital.medicine"
    _description = "Hospital Medicine Master"
    _order = "name"

    name = fields.Char(
        string="Medicine Name",
        required=True
    )
    code = fields.Char(
        string="Medicine Code",
        copy=False
    )
    generic_name = fields.Char(
        string="Generic Name"
    )
    brand_name = fields.Char(
        string="Brand Name"
    )
    category_id = fields.Many2one(
        "hospital.medicine.category",
        string="Category"
    )
    manufacturer = fields.Char(
        string="Manufacturer"
    )
    dosage_form = fields.Selection([
        ("tablet", "Tablet"),
        ("capsule", "Capsule"),
        ("syrup", "Syrup"),
        ("injection", "Injection"),
        ("ointment", "Ointment"),
        ("suspension", "Suspension"),
        ("inhaler", "Inhaler"),
        ("other", "Other")
    ],
        string="Dosage Form",
        default="tablet"
    )
    strength = fields.Char(
        string="Strength",
        placeholder="e.g. 500 mg, 10 ml"
    )
    unit = fields.Char(
        string="Unit of Measure",
        placeholder="e.g. Strip, Bottle, Box"
    )
    barcode = fields.Char(
        string="Barcode"
    )
    hsn_code = fields.Char(
        string="HSN Code"
    )
    gst_rate = fields.Selection([
        ("0", "0%"),
        ("5", "5%"),
        ("12", "12%"),
        ("18", "18%"),
        ("28", "28%")
    ],
        string="GST %",
        default="12"
    )
    price = fields.Float(
        string="Selling Price",
        default=0.0
    )
    selling_price = fields.Float(
        string="Selling Price Alias",
        related="price",
        readonly=False
    )
    purchase_price = fields.Float(
        string="Purchase Price",
        default=0.0
    )
    minimum_stock = fields.Integer(
        string="Minimum Stock",
        default=10
    )
    reorder_level = fields.Integer(
        string="Reorder Level",
        default=15
    )
    requires_prescription = fields.Boolean(
        string="Requires Prescription",
        default=False
    )
    storage_condition = fields.Char(
        string="Storage Condition",
        placeholder="e.g. Keep in a cool dry place"
    )
    status = fields.Selection([
        ("active", "Active"),
        ("inactive", "Inactive")
    ],
        string="Status",
        default="active",
        required=True
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )
    image = fields.Binary(
        string="Image"
    )
    description = fields.Text(
        string="Description"
    )

    batch_ids = fields.One2many(
        "hospital.medicine.batch",
        "medicine_id",
        string="Batches"
    )
    supplier_ids = fields.Many2many(
        "hospital.medicine.supplier",
        "hospital_medicine_supplier_rel",
        "medicine_id",
        "supplier_id",
        string="Suppliers",
        help="Suppliers that provide this medicine"
    )
    alternative_ids = fields.Many2many(
        "hospital.medicine",
        "hospital_medicine_alternative_rel",
        "medicine_id",
        "alternative_id",
        string="Alternative Medicines",
        domain="[('status', '=', 'active')]",
        help="Substitutes/Alternatives for this medicine when it is out of stock"
    )

    qty_available = fields.Integer(
        string="Quantity Available",
        compute="_compute_qty_available",
        store=True
    )
    stock_status = fields.Selection([
        ("out_of_stock", "Out of Stock"),
        ("low_stock", "Low Stock"),
        ("in_stock", "In Stock")
    ],
        string="Stock Status",
        compute="_compute_stock_status",
        store=True
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        compute="_compute_expiry_date",
        store=True
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "The medicine code must be unique!")
    ]

    @api.depends("batch_ids.qty_remaining")
    def _compute_qty_available(self):
        for record in self:
            record.qty_available = sum(record.batch_ids.mapped("qty_remaining"))

    @api.depends("qty_available", "minimum_stock")
    def _compute_stock_status(self):
        for record in self:
            if record.qty_available <= 0:
                record.stock_status = "out_of_stock"
            elif record.qty_available <= record.minimum_stock:
                record.stock_status = "low_stock"
            else:
                record.stock_status = "in_stock"

    @api.depends("batch_ids.expiry_date", "batch_ids.qty_remaining")
    def _compute_expiry_date(self):
        for record in self:
            # Look at active batches with quantity > 0
            active_batches = record.batch_ids.filtered(lambda b: b.qty_remaining > 0 and b.expiry_date)
            if active_batches:
                record.expiry_date = min(active_batches.mapped("expiry_date"))
            else:
                # If no stock, take min of all batches or False
                all_batches = record.batch_ids.filtered(lambda b: b.expiry_date)
                record.expiry_date = min(all_batches.mapped("expiry_date")) if all_batches else False

    def action_ai_auto_restock(self):
        self.ensure_one()
        suppliers = self.supplier_ids
        if not suppliers:
            suppliers = self.env["hospital.medicine.supplier"].search([])
        if not suppliers:
            raise UserError(_("No medicine suppliers found in the system. Please create a supplier first."))

        # Calculate standard restock quantity to reach minimum
        suggested_qty = max(self.minimum_stock - self.qty_available, 50)
        
        # Default fallback values
        chosen_supplier = suppliers[0]
        qty_to_order = suggested_qty
        import datetime
        suggested_batch = f"BATCH-{datetime.date.today().strftime('%Y%m')}-01"
        purchase_price = self.purchase_price or 10.0
        selling_price = self.price or 15.0
        
        # Attempt Gemini AI analysis
        api_key = self.env['ir.config_parameter'].sudo().get_param('hospital_management.gemini_api_key')
        if not api_key:
            import os
            api_key = os.environ.get('GEMINI_API_KEY')
            
        if api_key:
            suppliers_list = "\n".join([f"- ID {s.id}: {s.name} ({s.code})" for s in suppliers])
            prompt = (
                f"You are an AI pharmacy inventory assistant. We need to restock the following medicine:\n"
                f"- Medicine Name: {self.name}\n"
                f"- Current Available Stock: {self.qty_available}\n"
                f"- Minimum Stock Level: {self.minimum_stock}\n"
                f"- Current Last Purchase Price: {self.purchase_price}\n"
                f"- Current Selling Price: {self.price}\n\n"
                f"Available Suppliers list:\n{suppliers_list}\n\n"
                f"Please recommend:\n"
                f"1. Which supplier ID to use (select one from the list).\n"
                f"2. The exact quantity to order (must be at least {suggested_qty}).\n"
                f"3. A suggested batch number (use format BATCH-YYYYMM-XX where XX is sequential).\n"
                f"4. Suggested purchase price per unit (float).\n"
                f"5. Suggested selling price per unit (float).\n\n"
                f"Return ONLY a valid JSON object with keys: 'supplier_id' (integer), 'qty' (integer), 'batch_number' (string), 'purchase_price' (float), 'selling_price' (float)."
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
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json"
                }
            }
            headers = {"Content-Type": "application/json"}
            
            import requests
            import json
            for model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=20)
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
                        rec_supplier_id = result.get('supplier_id')
                        rec_supplier = suppliers.filtered(lambda s: s.id == rec_supplier_id)
                        if rec_supplier:
                            chosen_supplier = rec_supplier[0]
                        qty_to_order = int(result.get('qty', suggested_qty))
                        suggested_batch = result.get('batch_number', suggested_batch)
                        purchase_price = float(result.get('purchase_price', purchase_price))
                        selling_price = float(result.get('selling_price', selling_price))
                        break
                except Exception as e:
                    # Fail silently to try other models or fallback
                    pass

        # Create or update Draft Purchase Order
        po = self.env["hospital.medicine.purchase"].search([
            ("supplier_id", "=", chosen_supplier.id),
            ("state", "=", "draft")
        ], limit=1)
        
        if not po:
            po = self.env["hospital.medicine.purchase"].create({
                "supplier_id": chosen_supplier.id,
                "purchase_date": fields.Date.context_today(self),
                "state": "draft"
            })
            
        # Check if line already exists for this medicine
        line = self.env["hospital.medicine.purchase.line"].search([
            ("purchase_id", "=", po.id),
            ("medicine_id", "=", self.id)
        ], limit=1)
        
        if not line:
            from datetime import timedelta
            self.env["hospital.medicine.purchase.line"].create({
                "purchase_id": po.id,
                "medicine_id": self.id,
                "qty": qty_to_order,
                "purchase_price": purchase_price,
                "selling_price": selling_price,
                "batch_number": suggested_batch,
                "expiry_date": fields.Date.context_today(self) + timedelta(days=365)
            })
        else:
            line.write({
                "qty": line.qty + qty_to_order
            })
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Auto-Restock'),
                'message': _('Draft Purchase Order %s created/updated for supplier %s.') % (po.name, chosen_supplier.name),
                'type': 'success',
                'sticky': False,
            }
        }

