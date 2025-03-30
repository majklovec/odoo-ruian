# -*- coding: utf-8 -*-
import logging
import requests
import zipfile
import csv
from io import BytesIO, TextIOWrapper
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RuianImport(models.Model):
    _name = "ruian.import"
    _description = "RUIAN Data Import"
    _progress_step = 1000  # Log progress every X records

    def _safe_float(self, value):
        try:
            return float(str(value).replace(",", ".").strip()) if value else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _get_number_name(self, record):
        orient_number = record.get("Číslo orientační", "").strip()
        orient_letter = record.get("Číslo orientační písmeno", "").strip()
        if orient_number or orient_letter:
            return " ".join(filter(None, [orient_number, orient_letter]))
        domovni = record.get("Číslo domovní", "").strip()
        return domovni if domovni else _("Unknown")

    def _get_town_name(self, record):
        town = record.get("Název obce", "").strip()
        part = record.get("Název části obce", "").strip()

        if part and part != town:
            return f"{town} - {part}"
        else:
            return town

    def run_ruian_import(self):
        """Main import method with full error handling and progress tracking"""
        _logger.info("=== Starting RUIAN import process ===")

        today = fields.Date.today()
        target_date = (today.replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")

        start_time = datetime.now()

        log = self.env["ruian.log"].create(
            {
                "name": target_date,
                "state": "running",
                "start_date": fields.Datetime.now(),
            }
        )

        try:

            self._clear_existing_data()
            self.env.cr.commit()
            _logger.info("✅ Database cleared and committed")

            zip_file = self._download_zip(target_date)
            file_count = sum(
                1 for f in zip_file.infolist() if f.filename.endswith(".csv")
            )
            _logger.info("📦 Archive contains %d CSV files", file_count)

            processed_files = 0
            global_stats = {
                "towns": 0,
                "streets": 0,
                "numbers": 0,
                "rows": 0,
                "warnings": 0,
            }

            towns = {}
            streets = {}
            numbers = {}

            for zip_info in zip_file.infolist():
                if not zip_info.filename.endswith(".csv"):
                    continue

                processed_files += 1
                file_start = datetime.now()
                _logger.info(
                    "📁 Processing file %d/%d: %s",
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
                    self.env.cr.commit()

                    duration = (datetime.now() - file_start).total_seconds()
                    _logger.info(
                        "✅ Processed %d rows in %.2fs (T+:%d S+:%d N+:%d W:%d)",
                        file_stats["rows"],
                        duration,
                        file_stats["new_towns"],
                        file_stats["new_streets"],
                        file_stats["new_numbers"],
                        file_stats["warnings"],
                    )

                except Exception as e:
                    self.env.cr.rollback()
                    _logger.error(
                        "🚨 Rolling back changes for %s: %s", zip_info.filename, str(e)
                    )
                    global_stats["warnings"] += 1

            total_duration = (datetime.now() - start_time).total_seconds()
            _logger.info("=" * 60)
            _logger.info("🏁 Import completed in %.2f seconds", total_duration)
            _logger.info(
                "📊 Totals - Towns: %d, Streets: %d, Numbers: %d",
                global_stats["towns"],
                global_stats["streets"],
                global_stats["numbers"],
            )
            _logger.info("⚠️  Warnings: %d", global_stats["warnings"])
            _logger.info("=" * 60)

            log.write(
                {
                    "state": "done",
                    "end_date": fields.Datetime.now(),
                    "rows": global_stats["rows"],
                    "towns": global_stats["towns"],
                    "streets": global_stats["streets"],
                    "numbers": global_stats["numbers"],
                    "warnings": global_stats["warnings"],
                }
            )
            self.env.cr.commit()
            _logger.info("💾 Final commit completed")

        except Exception as e:
            self.env.cr.rollback()
            _logger.error("🚨 Critical import failure: %s", str(e), exc_info=True)
            raise UserError(_("Import failed: %s") % str(e)) from e

    def _process_csv_file(self, reader, towns, streets, numbers, global_stats):
        """Process individual CSV file with batch optimizations"""
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

            if file_stats["rows"] % self._progress_step == 0:
                _logger.debug("⏳ Processed %d rows...", file_stats["rows"])

            try:
                town = self._process_town(record, towns, file_stats, global_stats)

                street = self._process_street(
                    record, streets, town, file_stats, global_stats
                )

                self._process_number(
                    record, numbers, town, street, file_stats, global_stats
                )

                if file_stats["rows"] % 10000 == 0:
                    self.env.cr.commit()
                    _logger.debug(
                        "💾 Intermediate commit at row %d", file_stats["rows"]
                    )

            except Exception as e:
                _logger.warning("⚠️ Row %d error: %s", file_stats["rows"], str(e))
                file_stats["warnings"] += 1
                global_stats["warnings"] += 1

        return file_stats

    def _process_town(self, record, towns, file_stats, global_stats):
        """Handle town creation and validation"""
        town_code_str = record.get("Kód části obce")
        if not town_code_str:
            return None

        try:
            town_code = int(town_code_str)
            if town_code in towns:
                return towns[town_code]

            town_data = {
                "code": town_code,
                "name": self._get_town_name(record),
                "postal_code": record.get("PSČ", "").strip(),
            }

            if not town_data["name"] or not town_data["postal_code"]:
                raise ValueError("Invalid town data - missing name or postal code")

            town = self.env["ruian.town"].create(town_data)
            towns[town_code] = town
            file_stats["new_towns"] += 1
            global_stats["towns"] += 1
            _logger.debug("➕ Created town: %s (%d)", town_data["name"], town_code)
            return town

        except Exception as e:
            _logger.warning("⚠️ Town error in row %d: %s", file_stats["rows"], str(e))
            file_stats["warnings"] += 1
            return None

    def _process_street(self, record, streets, town, file_stats, global_stats):
        """Handle street creation and town linking"""
        street_name = record.get("Název ulice", "").strip()
        if not street_name:
            return None

        if street_name in streets:
            street = streets[street_name]
        else:
            street = self.env["ruian.street"].create({"name": street_name})
            streets[street_name] = street
            file_stats["new_streets"] += 1
            global_stats["streets"] += 1
            _logger.debug("➕ Created street: %s", street_name)

        if town and town.id not in street.town_ids.ids:
            street.write({"town_ids": [(4, town.id)]})
            _logger.debug("🔗 Linked street %s to town %s", street_name, town.name)

        return street

    def _process_number(self, record, numbers, town, street, file_stats, global_stats):
        """Handle number creation and relationships"""
        number_code_str = record.get("Kód ADM")
        if not number_code_str:
            return

        try:
            number_code = int(number_code_str)
            if number_code in numbers:
                number = numbers[number_code]
            else:
                number_data = {
                    "code": number_code,
                    "name": self._get_number_name(record),
                    "coord_x": self._safe_float(record.get("Souřadnice X")),
                    "coord_y": self._safe_float(record.get("Souřadnice Y")),
                    "town_id": town.id if town else False,
                    "street_id": street.id if street else False,
                }

                if not number_data["name"]:
                    raise ValueError("Missing number name")

                number = self.env["ruian.number"].create(number_data)
                numbers[number_code] = number
                file_stats["new_numbers"] += 1
                global_stats["numbers"] += 1
                _logger.debug(
                    "➕ Created number: %s (%d)", number_data["name"], number_code
                )

            if street and number.id not in street.number_ids.ids:
                street.write({"number_ids": [(4, number.id)]})
                _logger.debug(
                    "🔗 Linked number %s to street %s", number.name, street.name
                )

        except Exception as e:
            _logger.warning("⚠️ Number error in row %d: %s", file_stats["rows"], str(e))
            file_stats["warnings"] += 1

    def _clear_existing_data(self):
        """Clear existing RUIAN data"""
        _logger.info("Clearing existing data...")
        tables = [
            "ruian_street_number_rel",
            "ruian_street_town_rel",
            "ruian_number",
            "ruian_street",
            "ruian_town",
        ]
        for table in tables:
            self.env.cr.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = %s AND schemaname = 'public')",
                (table,),
            )
            exists = self.env.cr.fetchone()[0]
            if exists:
                _logger.info(f"Truncating table {table}...")
                self.env.cr.execute(f"TRUNCATE TABLE {table} CASCADE")
            else:
                _logger.warning(f"Table {table} does not exist, skipping truncate")
        self.env.cr.commit()
        _logger.info("Data cleared successfully")

    def _download_zip(self, target_date):
        """Secure file download without chunking"""
        url = f"https://vdp.cuzk.gov.cz/vymenny_format/csv/{target_date}_OB_ADR_csv.zip"
        _logger.info("⬇️ Downloading from: %s", url)

        try:
            start = datetime.now()
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            zip_buffer = BytesIO(response.content)

            _logger.info(
                "📥 Downloaded %.2f MB in %.2fs",
                len(zip_buffer.getvalue()) / (1024 * 1024),
                (datetime.now() - start).total_seconds(),
            )

            zip_file = zipfile.ZipFile(zip_buffer)
            if corrupt := zip_file.testzip():
                raise zipfile.BadZipFile(f"Corrupt file: {corrupt}")

            _logger.info("📦 Validated ZIP with %d files", len(zip_file.infolist()))
            return zip_file

        except requests.RequestException as e:
            _logger.error("🚨 Download failed: %s", str(e))
            raise UserError(_("Download failed: %s") % str(e)) from e
        except zipfile.BadZipFile as e:
            _logger.error("🚨 Corrupted ZIP: %s", str(e))
            raise UserError(_("Invalid ZIP archive")) from e
