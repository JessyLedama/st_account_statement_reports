# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.exceptions import UserError

class VendorBalancesWizard(models.TransientModel):
    _name = "vendor.balances.wizard"
    _description = "Vendor Balances Wizard"

    date_to = fields.Date(string="As At Date", required=True, default=fields.Date.context_today,)

    currency_id = fields.Many2one(
                "res.currency", 
                string="Currency", 
                required="True", 
                default=lambda self: self.env.company.currency_id,
            )

    def _get_balances(self):
        self.ensure_one()

        domain = [
            ("partner_id", "!=", False),
            ("account_id.account_type", "=", "liability_payable"),
            ("parent_state", "=", "posted"),
            ("company_id", "=", self.env.company.id),
            ("date", "<=", self.date_to),
            ("currency_id", "=", self.currency_id.id),
        ]

        # ------------------------------------------------------------
        # Group account move lines by vendor
        # ------------------------------------------------------------
        grouped = self.env["account.move.line"]._read_group(
            domain,
            ["partner_id"],
            ["amount_currency:sum"],
        )

        balances = []

        for partner, amount_currency in grouped:
            if not partner:
                continue

            balance = amount_currency or 0.0

            # Ignore vendors whose balance is exactly zero
            if not balance:
                continue

            balances.append({
                "partner_id": partner.id,
                "company_id": self.env.company.id,
                "date_to": self.date_to,
                "balance": balance,
                "currency_id": self.currency_id.id,
            })

        return balances

    def _create_balances(self):
        self.ensure_one()

        Balance = self.env["vendor.balances"]

        # Remove previous report records belonging to this wizard/company.
        # Since vendor.balances is a normal model, each report generation
        # creates a new set of records.
        balances = self._get_balances()

        if not balances:
            raise UserError(
            "No vendors with outstanding balances were found."
            )

        return Balance.create(balances)

    def action_show_balances(self):
        records = self._create_balances()

        return {
            "type": "ir.actions.act_window",
            "name": "Vendor Balances",
            "res_model": "vendor.balances",
            "view_mode": "list",
            "domain": [("id", "in", records.ids)],
            "target": "current",
        }

    def action_print_pdf(self):
        records = self._create_balances()

        return self.env.ref(
            "account_statement_reports.action_vendor_balances_report"
        ).report_action(records)