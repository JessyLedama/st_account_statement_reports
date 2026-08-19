# -*- coding: utf-8 -*-

from odoo import models, fields, api

class CustomerBalances(models.Model):
    _name = "customer.balances"
    _description = "Customer Balances"
    _order = "partner_id"

    partner_id = fields.Many2one("res.partner", string="Customer", required=True, readonly=True,)

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True, default=lambda self: self.env.company,)

    date_to = fields.Date(string="As At Date", readonly=True,)

    balance = fields.Float(string="Balance", readonly=True, currency_field="currency_id",)

    balance_type = fields.Char(string="Balance Type", readonly=True, compute="_compute_balance_type")

    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True,)

    @api.depends("balance")
    def _compute_balance_type(self):
        for record in self:
            if record.balance > 0:
                record.balance_type = "DR"
            elif record.balance < 0:
                record.balance_type = "CR"
            else:
                record.balance_type = ""
