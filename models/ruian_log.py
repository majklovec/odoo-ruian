from odoo import models, fields, api
from odoo.tools.translate import _


class RuianImportLog(models.Model):
    _name = "ruian.log"
    _description = "RUIAN Import Statistics"
    _order = "start_date desc"

    name = fields.Char(string="Import ID", readonly=True, index=True)
    start_date = fields.Datetime(string="Start Time", readonly=True)
    end_date = fields.Datetime(string="End Time", readonly=True)

    rows = fields.Integer(string="Rows", readonly=True)

    files = fields.Integer(string="Files", readonly=True)
    file_count = fields.Integer(string="File count", readonly=True)

    towns = fields.Integer(string="Towns", readonly=True)
    streets = fields.Integer(string="Streets", readonly=True)
    numbers = fields.Integer(string="Numbers", readonly=True)

    towns_created = fields.Integer(string="Towns created", readonly=True)
    streets_created = fields.Integer(string="Streets created", readonly=True)
    numbers_created = fields.Integer(string="Numbers created", readonly=True)

    towns_updated = fields.Integer(string="Towns updated", readonly=True)
    streets_updated = fields.Integer(string="Streets updated", readonly=True)
    numbers_updated = fields.Integer(string="Numbers updated", readonly=True)

    warnings = fields.Integer(string="Warnings", readonly=True)
    duration = fields.Float(
        string="Duration",
        help="duration in hours",
        compute="_compute_duration",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [("running", "Running"), ("failed", "Failed"), ("done", "Done")],
        string="Status",
        readonly=True,
    )
    progress = fields.Char(
        string="Progress", compute="_compute_progress", readonly=True
    )
    eta = fields.Char(string="ETA", compute="_compute_eta", readonly=True)

    error_message = fields.Char(string="Error message", readonly=True, index=True)

    @api.depends("start_date", "end_date")
    def _compute_duration(self):
        for log in self:
            if log.end_date and log.start_date:
                start = fields.Datetime.to_datetime(log.start_date)
                end = fields.Datetime.to_datetime(log.end_date)
                delta = end - start
                log.duration = delta.total_seconds() / 3600  # Convert seconds to hours
            else:
                log.duration = 0.0

    @api.depends("files", "file_count")
    def _compute_progress(self):
        for log in self:
            if log.file_count > 0:
                percentage = (log.files / log.file_count) * 100
            else:
                percentage = 0.0
            percentage_str = f"{percentage:.0f}%"
            log.progress = f"{log.files} / {log.file_count} ({percentage_str})"

    # New ETA calculation
    @api.depends("start_date", "state", "files", "file_count")
    def _compute_eta(self):
        for log in self:
            if log.state == "running" and not log.end_date and log.start_date:
                now = fields.Datetime.now()
                start = fields.Datetime.to_datetime(log.start_date)
                elapsed = now - start
                elapsed_hours = elapsed.total_seconds() / 3600  # Elapsed time in hours

                if log.file_count > 0 and log.files <= log.file_count:
                    if log.files == 0:
                        log.eta = _("Estimating...")
                        continue
                    progress = log.files / log.file_count
                    total_estimated_time = elapsed_hours / progress
                    remaining_time = total_estimated_time - elapsed_hours
                    if remaining_time <= 0:
                        log.eta = _("About to complete")
                    else:
                        hours = int(remaining_time)
                        minutes = int((remaining_time - hours) * 60)
                        log.eta = f"{hours}h {minutes}m"
                else:
                    log.eta = _("Estimating...")
            else:
                log.eta = ""  # Empty if not running or completed
