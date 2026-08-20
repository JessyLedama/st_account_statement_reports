# -*- coding: utf-8 -*-
from odoo import models, fields
from datetime import timedelta


class StatementMixin(models.AbstractModel):
    _name = "statement.mixin"
    _description = "Common Statement Logic"

    # ------------------------------------------------------
    # OPENING BALANCE
    # ------------------------------------------------------
    def _get_opening_balance(self, partner, account_type, date_from):
        """Compute balance before the chosen start date."""
        if not date_from:
            return 0.0

        aml = self.env["account.move.line"].search([
            ("partner_id", "=", partner.id),
            ("account_id.account_type", "=", account_type),
            ("parent_state", "=", "posted"),
            ("date", "<", date_from),
        ])

        return sum((l.debit or 0.0) - (l.credit or 0.0) for l in aml)

    # ------------------------------------------------------
    # OPENING BALANCE IN FOREIGN CURRENCY
    # ------------------------------------------------------
    def _get_opening_balance_currency(self, partner, account_type, date_from):
        """Compute foreign currency balance before the chosen start date."""
        if not date_from:
            return 0.0

        aml = self.env["account.move.line"].search([
            ("partner_id", "=", partner.id),
            ("account_id.account_type", "=", account_type),
            ("parent_state", "=", "posted"),
            ("date", "<", date_from),
        ])

        return sum(
            line.amount_currency or 0.0
            for line in aml
        )

    # ------------------------------------------------------
    # BUILD STATEMENT WITH RUNNING BALANCE
    # ------------------------------------------------------
    def _get_statement_lines_with_balance(self, partner, account_type, date_from, date_to):
        """Returns full list of statement rows including running balance."""

        opening_balance = self._get_opening_balance(partner, account_type, date_from)

        opening_balance_currency = self._get_opening_balance_currency(partner, account_type, date_from)

        # Query lines inside date range
        domain = [
            ("partner_id", "=", partner.id),
            ("account_id.account_type", "=", account_type),
            ("parent_state", "=", "posted"),
        ]
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))

        aml = self.env["account.move.line"].search(domain, order="date asc, id asc")

        running_balance = opening_balance
        running_balance_currency = opening_balance_currency
        results = []

        # ------------------------------------------------------
        # OPENING BALANCE ROW (fake date ensures top position)
        # ------------------------------------------------------
        if date_from:
            fake_date = fields.Date.to_date(date_from) - timedelta(days=1)
        else:
            fake_date = None

        results.append({
            "date": fake_date,
            "move": "Opening Balance",
            "reference": "",
            "narration": "",
            "due_date": None,
            "currency_id": False,
            "amount_currency": 0.0,
            "debit": opening_balance if opening_balance > 0 else 0.0,
            "credit": -opening_balance if opening_balance < 0 else 0.0,
            "balance": opening_balance,
            "balance_currency": opening_balance_currency,
        })

        # ------------------------------------------------------
        # NORMAL TRANSACTION LINES
        # ------------------------------------------------------
        for line in aml:
            debit = line.debit or 0.0
            credit = line.credit or 0.0

            running_balance += (debit - credit)
            running_balance_currency += line.amount_currency or 0.0

            move = line.move_id

            # -----------------------------------------
            # Reference logic (FINAL & SIMPLE)
            # -----------------------------------------
            if move.move_type == "out_invoice":
                # Customer invoice ONLY
                reference = move.payment_reference or ""
            else:
                # Customer payment, vendor bill, vendor payment, everything else
                reference = move.ref or ""

            payment = move.payment_ids[:1]

            narration = ""

            # Narration
            if payment:
                narration = payment.narration

            elif move.move_type == "out_invoice":
                # Sale Order
                sale_orders = move.invoice_line_ids.sale_line_ids.order_id
                if sale_orders:
                    narration = sale_orders[:1].x_narration or ""

            elif move.move_type == "in_invoice":
                # Vendor Bill -> Purchase Order
                purchase_orders = move.invoice_line_ids.purchase_line_id.order_id
                if purchase_orders:
                    narration = purchase_orders[:1].x_narration or ""

            # Prefer the move line's currency information
            currency_id = line.currency_id
            amount_currency = line.amount_currency

            # Fallback for payment lines if needed
            if not currency_id and payment:
                currency_id = payment.currency_id
                amount_currency = payment.amount


            results.append({
                "date": line.date,
                "move": move.name,
                "reference": reference,
                "narration": narration,
                "due_date": line.date_maturity,
                "currency_id": currency_id.id if currency_id else False,
                "amount_currency": amount_currency,
                "debit": debit,
                "credit": credit,
                "balance": running_balance,
                "balance_currency": running_balance_currency,
            })

        return results



    # ------------------------------------------------------
    # TOTALS (we don't use them in UI, but kept for compatibility)
    # ------------------------------------------------------
    def _compute_totals(self, lines):
        return {"total_due": 0.0, "total_overdue": 0.0}
