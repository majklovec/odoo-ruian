from odoo import models, fields, api
from odoo.tools.translate import _


class RuianTown(models.Model):
    _name = "ruian.town"
    _description = "RUIAN Towns"
    _order = "name desc"

    code = fields.Integer(required=True)
    name = fields.Char(required=True)
    postal_code = fields.Char(required=True)

    _sql_constraints = [
        ("code_uniq", "UNIQUE(code)", "Town code must be unique!"),
    ]


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


class RuianNumber(models.Model):
    _name = "ruian.number"
    _description = "RUIAN Numbers"
    _order = "name desc"

    code = fields.Integer(required=True)
    name = fields.Char(required=True)
    coord_x = fields.Float(digits=(9, 6))
    coord_y = fields.Float(digits=(9, 6))

    town_id = fields.Many2one("ruian.town", string="Town")
    street_ids = fields.Many2many("ruian.street", string="Streets")

    full_address = fields.Char(compute="_compute_full_address")

    _sql_constraints = [
        ("code_uniq", "UNIQUE(code)", "Number code must be unique!"),
    ]

    def _compute_full_address(self):
        for record in self:
            streets = ", ".join(record.street_ids.mapped("name"))
            towns = ", ".join(record.town_ids.mapped("name"))
            record.full_address = f"{record.name}, {streets}, {towns}"


class RuianImportLog(models.Model):
    _name = "ruian.import.log"
    _description = "RUIAN Import Statistics"
    _order = "start_date desc"

    name = fields.Char(
        string="Import ID", readonly=True, default=lambda self: _("New"), index=True
    )
    start_date = fields.Datetime(string="Start Time", readonly=True)
    end_date = fields.Datetime(string="End Time", readonly=True)
    duration = fields.Float(string="Duration (seconds)", readonly=True)
    processed_rows = fields.Integer(string="Processed Rows", readonly=True)
    created_towns = fields.Integer(string="Created Towns", readonly=True)
    created_streets = fields.Integer(string="Created Streets", readonly=True)
    created_numbers = fields.Integer(string="Created Numbers", readonly=True)
    warnings = fields.Integer(string="Warnings", readonly=True)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("running", "Running"),
            ("done", "Completed"),
            ("error", "Error"),
        ],
        string="Status",
        readonly=True,
        default="draft",
    )
    error_message = fields.Text(string="Error Details", readonly=True)
    user_id = fields.Many2one("res.users", string="Executed By", readonly=True)
    file_count = fields.Integer(string="Processed Files", readonly=True)

    @api.model
    def create(self, vals_list):
        """Handle batch creation with sequence generation"""
        # Process each record in the batch
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "ruian.import.log"
                ) or _("New")
        return super().create(vals_list)
