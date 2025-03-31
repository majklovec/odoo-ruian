from odoo import models, fields, api
from odoo.tools.translate import _


class RuianNumber(models.Model):
    _name = "ruian.number"
    _description = "RUIAN Numbers"
    _order = "name"

    code = fields.Integer(required=True)
    name = fields.Char(required=True)

    coord_x = fields.Float(digits=(10, 7))
    coord_y = fields.Float(digits=(10, 7))

    town_id = fields.Many2one("ruian.town", string="Town")
    street_id = fields.Many2one("ruian.street", string="Street")

    full_address = fields.Char(compute="_compute_full_address")

    _sql_constraints = [
        ("code_uniq", "UNIQUE(code)", "Number code must be unique!"),
    ]

    def _compute_full_address(self):
        for record in self:
            street = record.street_id.name if record.street_id else ""
            town = record.town_id.name if record.town_id else ""
            psc = record.town_id.postal_code if record.town_id else ""
            record.full_address = f"{street} {record.name}, {town} {psc}"
