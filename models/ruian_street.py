from odoo import models, fields, api
from odoo.tools.translate import _


class RuianStreet(models.Model):
    _name = "ruian.street"
    _description = "RUIAN Streets"
    _order = "name desc"

    name = fields.Char(required=True)

    town_ids = fields.Many2many("ruian.town", string="Associated Towns")
    number_ids = fields.Many2many("ruian.number", string="House Numbers")

    number_count = fields.Integer(compute="_compute_number_count")

    _sql_constraints = [
        ("name_uniq", "UNIQUE(name)", "Street name must be unique!"),
    ]

    def _compute_number_count(self):
        for record in self:
            record.number_count = self.env["ruian.number"].search_count(
                [("street_ids", "in", self.ids)]
            )
