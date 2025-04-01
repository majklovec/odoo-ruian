# -*- coding: utf-8 -*-
import logging
import requests
import zipfile
import csv
from pyproj import Transformer
from io import BytesIO, TextIOWrapper
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RuianImport(models.Model):
    _name = "ruian.import"
    _description = "RUIAN Data Import"
    _progress_step = 1000  # Log progress every X records
    _transformer = Transformer.from_crs("EPSG:5514", "EPSG:4326", always_xy=True)

    @api.model
    def _register_hook(self):
        """Set 'running' logs to 'failed' on server restart."""
        res = super(RuianImport, self)._register_hook()
        logs = self.env["ruian.log"].search([("state", "=", "running")])
        if logs:
            logs.write({"state": "failed"})
            self.env.cr.commit()  # Ensure changes are saved immediately
        return res

    def _get_number_name(self, record):
        domovni = record.get("Číslo domovní", "").strip()
        orient_number = record.get("Číslo orientační", "").strip()
        orient_letter = record.get("Číslo orientační písmeno", "").strip()

        if orient_number:
            return f"{domovni}/{orient_number}{orient_letter}".strip()
        return domovni if domovni else _("Unknown")

    def _get_town_name(self, record):
        town = record.get("Název obce", "").strip()
        part = record.get("Název části obce", "").strip()

        if part and part != town:
            return f"{town} - {part}"
        else:
            return town

    def _convert_epsg5514_to_epsg4326(
        self, x_str: str, y_str: str
    ) -> tuple[float, float]:
        try:
            x, y = float(x_str), float(y_str)
            lon, lat = self._transformer.transform(x, y)
            return lat, lon
        except (ValueError, TypeError):
            return 0.0, 0.0

    def run_ruian_import(self):
        """Main import method with guaranteed log updates"""
        _logger.info("=== Starting RUIAN import ===")
        start_time = datetime.now()
        today = fields.Date.today()
        target_date = (
            (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            - timedelta(days=1)
        ).strftime("%Y%m%d")

        # Initialize log record
        log = self.env["ruian.log"].create(
            {
                "name": target_date,
                "state": "running",
                "start_date": fields.Datetime.now(),
            }
        )
        self.env.cr.commit()

        try:
            # Download and prepare data
            zip_file = self._download_zip(target_date)
            file_count = sum(
                1 for f in zip_file.infolist() if f.filename.endswith(".csv")
            )
            log.file_count = file_count
            self.env.cr.commit()

            _logger.info("Found %d CSV files in archive", file_count)

            # Initialize counters
            processed_files = 0
            global_stats = {
                "towns": 0,
                "streets": 0,
                "numbers": 0,
                "rows": 0,
                "warnings": 0,
                "files": 0,
            }

            # Caches for existing records
            towns = {}
            streets = {}
            numbers = {}

            for zip_info in zip_file.infolist():
                if not zip_info.filename.endswith(".csv"):
                    continue

                processed_files += 1
                file_start = datetime.now()
                _logger.debug(
                    "Processing file %d/%d: %s",
                    processed_files,
                    file_count,
                    zip_info.filename,
                )

                try:
                    with zip_file.open(zip_info) as csv_file:
                        reader = csv.DictReader(
                            TextIOWrapper(csv_file, encoding="windows-1250"),
                            delimiter=";",
                        )
                        file_stats = self._process_csv_file(
                            reader, towns, streets, numbers, global_stats
                        )

                    # Update global statistics
                    global_stats["files"] = processed_files
                    duration = (datetime.now() - file_start).total_seconds()

                    _logger.info(
                        "File %s processed: %d rows, %d towns, %d streets, %d numbers in %.2fs",
                        zip_info.filename,
                        file_stats["rows"],
                        file_stats["new_towns"],
                        file_stats["new_streets"],
                        file_stats["new_numbers"],
                        duration,
                    )

                    # Update log with current state
                    log.write(
                        {
                            "files": global_stats["files"],
                            "rows": global_stats["rows"],
                            "towns": global_stats["towns"],
                            "streets": global_stats["streets"],
                            "numbers": global_stats["numbers"],
                            "warnings": global_stats["warnings"],
                        }
                    )
                    self.env.cr.commit()

                except Exception as e:
                    _logger.error(
                        "File processing failed: %s - %s", zip_info.filename, str(e)
                    )
                    global_stats["warnings"] += 1
                    self.env.cr.rollback()
                    continue

            # Final log update
            total_duration = (datetime.now() - start_time).total_seconds()
            log.write(
                {
                    "state": "done",
                    "end_date": fields.Datetime.now(),
                    "duration": total_duration,
                }
            )
            self.env.cr.commit()

            _logger.info(
                "Import completed: %d files, %d rows, %d towns, %d streets, %d numbers in %.2fs",
                processed_files,
                global_stats["rows"],
                global_stats["towns"],
                global_stats["streets"],
                global_stats["numbers"],
                total_duration,
            )

        except Exception as e:
            self.env.cr.rollback()
            log.write(
                {
                    "state": "failed",
                    "end_date": fields.Datetime.now(),
                    "error_message": str(e)[:500],
                }
            )
            self.env.cr.commit()
            _logger.error("Import failed: %s", str(e))
            raise UserError(_("Import failed: %s") % str(e)) from e

        return True

    def _process_csv_file(self, reader, towns, streets, numbers, global_stats):
        """Process individual CSV file with progress tracking"""
        file_stats = {
            "rows": 0,
            "new_towns": 0,
            "new_streets": 0,
            "new_numbers": 0,
            "warnings": 0,
        }

        for record in reader:
            file_stats["rows"] += 1
            global_stats["rows"] += 1

            # Progress logging
            if file_stats["rows"] % self._progress_step == 0:
                _logger.debug("Processed %d rows...", file_stats["rows"])
                self.env.cr.commit()

            try:
                # Process records
                town = self._process_town(record, towns, file_stats, global_stats)
                street = self._process_street(
                    record, streets, town, file_stats, global_stats
                )
                self._process_number(
                    record, numbers, town, street, file_stats, global_stats
                )

            except Exception as e:
                file_stats["warnings"] += 1
                global_stats["warnings"] += 1
                _logger.warning("Row error: %s", str(e))

        return file_stats

    def _download_zip(self, target_date):
        """Secure ZIP file download"""
        url = f"https://vdp.cuzk.gov.cz/vymenny_format/csv/{target_date}_OB_ADR_csv.zip"
        _logger.info("Downloading ZIP from: %s", url)

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            zip_file = zipfile.ZipFile(BytesIO(response.content))
            if corrupt := zip_file.testzip():
                raise zipfile.BadZipFile(f"Corrupt file: {corrupt}")

            _logger.info("Downloaded valid ZIP archive")
            return zip_file

        except requests.RequestException as e:
            _logger.error("Download failed: %s", str(e))
            raise UserError(_("Download failed: %s") % str(e)) from e
        except zipfile.BadZipFile as e:
            _logger.error("Invalid ZIP file: %s", str(e))
            raise UserError(_("Invalid ZIP archive")) from e

    def _process_town(self, record, towns, file_stats, global_stats):
        """Process town record with caching"""
        town_code = record.get("Kód části obce")
        if not town_code:
            return None

        try:
            town_code = int(town_code)
            if town_code in towns:
                return towns[town_code]

            town_data = {
                "code": town_code,
                "name": self._get_town_name(record),
                "postal_code": record.get("PSČ", "").strip(),
            }

            existing = self.env["ruian.town"].search(
                [("code", "=", town_code)], limit=1
            )
            if existing:
                existing.write(town_data)
                town = existing
            else:
                town = self.env["ruian.town"].create(town_data)
                file_stats["new_towns"] += 1
                global_stats["towns"] += 1

            towns[town_code] = town
            return town

        except Exception as e:
            _logger.warning("Town processing error: %s", str(e))
            file_stats["warnings"] += 1
            global_stats["warnings"] += 1
            return None

    def _process_street(self, record, streets, town, file_stats, global_stats):
        """Process street record with town association"""
        street_name = record.get("Název ulice", "").strip()
        if not street_name:
            return None

        try:
            street_key = street_name  # (street_name, town.id if town else None)
            if street_key in streets:
                return streets[street_key]

            existing = self.env["ruian.street"].search(
                [
                    ("name", "=", street_name),
                    # ("town_ids", "in", [town.id] if town else []),
                ],
                limit=1,
            )

            if existing:
                street = existing
            else:
                street = self.env["ruian.street"].create({"name": street_name})
                file_stats["new_streets"] += 1
                global_stats["streets"] += 1

            if town and town.id not in street.town_ids.ids:
                street.write({"town_ids": [(4, town.id)]})

            streets[street_key] = street
            return street

        except Exception as e:
            _logger.warning("Street processing error: %s", str(e))
            file_stats["warnings"] += 1
            global_stats["warnings"] += 1
            return None

    def _process_number(self, record, numbers, town, street, file_stats, global_stats):
        """Process address number with geocoordinates"""
        number_code = record.get("Kód ADM")
        if not number_code:
            return

        try:
            number_code = int(number_code)
            if number_code in numbers:
                return numbers[number_code]

            lat, lon = self._convert_epsg5514_to_epsg4326(
                record.get("Souřadnice X"), record.get("Souřadnice Y")
            )
            number_data = {
                "code": number_code,
                "name": self._get_number_name(record),
                "lat": lat,
                "lon": lon,
                "town_id": town.id if town else False,
                "street_id": street.id if street else False,
            }

            existing = self.env["ruian.number"].search(
                [("code", "=", number_code)], limit=1
            )
            if existing:
                existing.write(number_data)
                number = existing
            else:
                number = self.env["ruian.number"].create(number_data)
                file_stats["new_numbers"] += 1
                global_stats["numbers"] += 1

            if street and number.id not in street.number_ids.ids:
                street.write({"number_ids": [(4, number.id)]})

            numbers[number_code] = number
            return number

        except Exception as e:
            _logger.warning("Number processing error: %s", str(e))
            file_stats["warnings"] += 1
            global_stats["warnings"] += 1
            return None
