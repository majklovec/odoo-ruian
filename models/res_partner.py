from odoo import models, fields


class ResPartner(models.Model):
    _inherit = "res.partner"

    ruian_code = fields.Char("RUIAN Code")
