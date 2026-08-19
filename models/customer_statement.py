from odoo import models, fields
import base64
from io import BytesIO
import xlsxwriter


class CustomerStatement(models.Model):
    _name = "customer.statement"
    _description = "Customer Statement"
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", required=True, readonly=True)
    date_from = fields.Date(required=True, readonly=True)
    date_to = fields.Date(required=True, readonly=True)

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        readonly=True,
    )

    opening_balance = fields.Float(readonly=True)

    line_ids = fields.One2many(
        "customer.statement.line",
        "statement_id",
        readonly=True,
    )

    # Last balance in the list
    final_balance = fields.Float(readonly=True)

    currency_id = fields.Many2one("res.currency", readonly=True,)
    
    final_balance_currency = fields.Monetary(currency_field="currency_id", readonly=True)

    balance_type = fields.Char(compute="_compute_balance_type", string="Balance Type")

    # ------------------------------------------------------------
    # MAIN STATEMENT GENERATION
    # ------------------------------------------------------------
    def action_get_statement(self):
        mixin = self.env["statement.mixin"]

        # Get opening balance
        self.opening_balance = mixin._get_opening_balance(
            self.partner_id, "asset_receivable", self.date_from
        )

        # Build transaction lines with running balance
        lines = mixin._get_statement_lines_with_balance(
            self.partner_id, "asset_receivable",
            self.date_from, self.date_to
        )

        # Remove existing
        self.line_ids.unlink()

        # Insert new
        for l in lines:
            self.env["customer.statement.line"].create({
                "statement_id": self.id,
                "date": l["date"],
                "move": l["move"],
                "reference": l["reference"],
                "narration": l["narration"],
                "due_date": l["due_date"],
                "currency_id": l["currency_id"],
                "amount_currency": l["amount_currency"],
                "debit": l["debit"],
                "credit": l["credit"],
                "balance": l["balance"],
                "balance_currency": l["balance_currency"],
            })

        if lines:
            # Last balance
            self.final_balance = lines[-1]["balance"] if lines else 0.0
            self.final_balance_currency = lines[-1]["balance_currency"]

            currency_ids = [
                line["currency_id"]
                for line in lines
                if line.get("currency_id")
            ]

            self.currency_id = currency_ids[-1] if currency_ids else False
        else:
            self.final_balance = 0.0
            self.final_balance_currency = 0.0
            self.currency_id = False
        

        return True

    # ------------------------------------------------------------
    # PDF EXPORT
    # ------------------------------------------------------------
    def action_print_pdf(self):
        return self.env.ref(
            "account_statement_reports.asr_customer_statement_report"
        ).report_action(self)

    # ------------------------------------------------------------
    # EXCEL EXPORT (same style as vendor)
    # ------------------------------------------------------------
    def action_export_excel(self):
        """Generate XLSX customer statement."""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Customer Statement")

        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})

        # Header
        sheet.write(0, 0, "Customer:", bold)
        sheet.write(0, 1, self.partner_id.name)

        sheet.write(1, 0, "Period:", bold)
        sheet.write(1, 1, f"{self.date_from or '-'} → {self.date_to or '-'}")

        # Table headers
        headers = ["Date", "Move", "Reference", "Narration", "Due Date", "Currency", "Amount in Currency", "Debit", "Credit", "Balance", "Balance in Currency"]
        for col, h in enumerate(headers):
            sheet.write(3, col, h, bold)

        # Lines
        row = 4
        for line in self.line_ids:
            sheet.write(row, 0, str(line.date or ""))
            sheet.write(row, 1, line.move or "")
            sheet.write(row, 2, line.reference or "")
            sheet.write(row, 3, line.narration or "")
            sheet.write(row, 4, str(line.due_date) if line.due_date else "")
            sheet.write(row, 5, line.currency_id.name or "")
            sheet.write(row, 6, line.amount_currency or "")
            sheet.write_number(row, 7, line.debit or 0, money)
            sheet.write_number(row, 8, line.credit or 0, money)
            sheet.write_number(row, 9, line.balance or 0, money)
            sheet.write_number(row, 10, line.balance_currency or 0, money)
            row += 1

                # ------------------------------------------------------------
        # SUMMARY
        # ------------------------------------------------------------
        row += 2

        sheet.write(row, 8, "Final Balance", bold)
        sheet.write_number(row, 9, self.final_balance or 0.0, money)
        row += 1

        sheet.write(row, 8, "Balance Type", bold)
        sheet.write(row, 9, self.balance_type or "")
        row += 1

        sheet.write(row, 8, "Final Balance in Currency", bold)

        if self.currency_id:
            sheet.write(
                row,
                9,
                f"{self.currency_id.name} {self.final_balance_currency:,.2f}"
            )
        else:
            sheet.write_number(
                row,
                9,
                self.final_balance_currency or 0.0,
                money
            )

        workbook.close()
        output.seek(0)

        # Attachment for download
        xlsx_data = base64.b64encode(output.read())

        attachment = self.env["ir.attachment"].create({
            "name": f"Customer Statement - {self.partner_id.name}.xlsx",
            "type": "binary",
            "datas": xlsx_data,
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }


    # Compute the balance type
    def _compute_balance_type(self):
        for record in self:
            if record.final_balance > 0:
                record.balance_type = "DR"
            elif record.final_balance < 0:
                record.balance_type = "CR"
            else:
                record.balance_type = ""
