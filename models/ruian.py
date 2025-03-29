from odoo import models, fields, api


class RuianTown(models.Model):
    _name = "ruian.town"
    _description = "RUIAN Towns"

    code = fields.Integer("Town Code", index=True)
    name = fields.Char("Town Name")
    postal_code = fields.Integer("Postal Code")

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Town code must be unique!"),
    ]


class RuianStreet(models.Model):
    _name = "ruian.street"
    _description = "RUIAN Streets"

    name = fields.Char("Street Name")
    town_ids = fields.Many2many("ruian.town", string="Towns")
    code = fields.Integer("Street Code", index=True)

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Street code must be unique!"),
    ]


class RuianNumber(models.Model):
    _name = "ruian.number"
    _description = "RUIAN Address Numbers"

    code = fields.Integer("RUIAN Code", index=True)
    name = fields.Char("Number")
    town_id = fields.Many2one("ruian.town", "Town")
    street_ids = fields.Many2many("ruian.street", string="Streets")
    coord_x = fields.Float("Coordinate X", digits=(9, 6))
    coord_y = fields.Float("Coordinate Y", digits=(9, 6))

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Number code must be unique!"),
    ]

    def _auto_init(self):
        res = super()._auto_init()
        self.env.cr.execute(
            """
            CREATE INDEX IF NOT EXISTS ruian_number_code_idx 
            ON ruian_number (code)
        """
        )
        return res
