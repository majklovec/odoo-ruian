# -*- coding: utf-8 -*-
import logging
import requests
import zipfile
import csv
from io import BytesIO, TextIOWrapper
from datetime import datetime, timedelta
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RuianImport(models.Model):
    _name = "ruian.import"
    _description = "RUIAN Data Import"

    def run_ruian_import(self):
        """Main entry point for RUIAN data import with full logging"""
        _logger.info("=== Starting RUIAN import process ===")

        try:
            # Calculate target date (last day of previous month)
            today = fields.Date.today()
            first_day = today.replace(day=1)
            last_month = first_day - timedelta(days=1)
            target_date = last_month.strftime("%Y%m%d")
            _logger.info("Calculated target date: %s", target_date)

            # Build download URL
            download_url = (
                f"https://vdp.cuzk.gov.cz/vymenny_format/csv/"
                f"{target_date}_OB_ADR_csv.zip"
            )
            _logger.info("Download URL: %s", download_url)

            # Download ZIP file
            _logger.info("Starting download...")
            headers = {"User-Agent": "Odoo-RUIAN-Importer/1.0"}
            response = requests.get(
                download_url, headers=headers, timeout=30, stream=True
            )
            response.raise_for_status()
            _logger.info(
                "Download completed (size: %s MB)",
                len(response.content) // 1024 // 1024,
            )

            # Validate ZIP
            _logger.info("Validating ZIP file...")
            try:
                zip_file = zipfile.ZipFile(BytesIO(response.content))
                bad_file = zip_file.testzip()
                if bad_file:
                    raise zipfile.BadZipFile(f"Corrupt file in ZIP: {bad_file}")
            except zipfile.BadZipFile as e:
                _logger.error("Invalid ZIP file: %s", str(e))
                raise UserError(_("Downloaded file is not a valid ZIP archive")) from e

            # Clear existing data
            _logger.info("Clearing existing data...")
            self._clear_existing_data()

            # Process ZIP contents
            _logger.info("Processing ZIP contents...")
            processed_files = 0
            for zip_info in zip_file.infolist():
                if zip_info.filename.endswith(".csv"):
                    _logger.info("Processing file: %s", zip_info.filename)
                    with zip_file.open(zip_info) as csv_file:
                        reader = csv.DictReader(
                            TextIOWrapper(csv_file, encoding="windows-1250"),
                            delimiter=";",
                        )
                        self._process_csv(reader)
                    processed_files += 1

            _logger.info("Processed %d CSV files", processed_files)
            _logger.info("=== RUIAN import completed successfully ===")

        except requests.exceptions.RequestException as e:
            _logger.error("Network error: %s", str(e), exc_info=True)
            raise UserError(_("Network error: %s") % str(e)) from e
        except Exception as e:
            _logger.error("Critical error during import: %s", str(e), exc_info=True)
            raise UserError(_("Import failed: %s") % str(e)) from e

    def _clear_existing_data(self):
        """Clear existing data in proper order"""
        tables = [
            # "ruian_street_number_rel",
            # "ruian_street_town_rel",
            "ruian_number",
            "ruian_street",
            "ruian_town",
        ]

        for table in tables:
            self.env.cr.execute(f"DELETE FROM {table}")
            _logger.info("Cleared table: %s", table)

    def _process_csv(self, reader):
        """Process CSV data with verbose logging"""
        _logger.info("🏁 Starting CSV processing...")

        # Data collectors
        towns = defaultdict(dict)
        streets = set()
        numbers = defaultdict(dict)
        street_towns = defaultdict(set)
        street_numbers = defaultdict(set)

        # Process records
        record_count = 0
        for record in reader:
            record_count += 1

            # Progress logging
            if record_count % 10000 == 0:
                _logger.info(
                    "📊 Processed %d records... (current: Town:%s|Street:%s|Number:%s)",
                    record_count,
                    record.get("Kód části obce", "N/A"),
                    record.get("Název ulice", "N/A"),
                    record.get("Kód ADM", "N/A"),
                )

            # Process Town
            town_code = record.get("Kód části obce")
            if town_code:
                towns[town_code] = {
                    "code": town_code,
                    "name": record.get("Název obce", ""),
                    "postal_code": record.get("PSČ", ""),
                }

            # Process Street
            street_name = record.get("Název ulice", "")
            if street_name:
                streets.add(street_name)
                if town_code:
                    street_towns[street_name].add(town_code)

            # Process Number
            number_code = record.get("Kód ADM")
            if number_code:
                numbers[number_code] = {
                    "code": number_code,
                    "name": self._get_number_name(record),
                    "town_code": town_code,
                    "coord_x": record.get("Souřadnice X"),
                    "coord_y": record.get("Souřadnice Y"),
                }
                if street_name:
                    street_numbers[street_name].add(number_code)

        _logger.info("✅ Finished CSV parsing")
        _logger.info("📦 Collected data statistics:")
        _logger.info("   Towns: %d unique entries", len(towns))
        _logger.info("   Streets: %d unique names", len(streets))
        _logger.info("   Numbers: %d unique entries", len(numbers))
        _logger.info(
            "   Street-Town relationships: %d",
            sum(len(v) for v in street_towns.values()),
        )
        _logger.info(
            "   Street-Number relationships: %d",
            sum(len(v) for v in street_numbers.values()),
        )

        # Batch create records
        _logger.info("🗄️ Starting database operations...")

        # Create towns
        _logger.info("🏘️ Creating %d towns...", len(towns))
        town_records = list(towns.values())
        created_towns = self.env["ruian.town"].create(town_records)
        _logger.info("   Successfully created %d towns", len(created_towns))
        town_code_to_id = {t.code: t.id for t in created_towns}
        _logger.debug(
            "   Sample town mapping: %s", dict(list(town_code_to_id.items())[:3])
        )

        # Create streets
        _logger.info("🛣️ Creating %d streets...", len(streets))
        street_records = [{"name": name} for name in streets]
        created_streets = self.env["ruian.street"].create(street_records)
        _logger.info("   Successfully created %d streets", len(created_streets))
        street_name_to_id = {s.name: s.id for s in created_streets}
        _logger.debug(
            "   Sample street mapping: %s", dict(list(street_name_to_id.items())[:3])
        )

        # Create numbers
        _logger.info("🏠 Creating %d numbers...", len(numbers))
        number_records = []
        for code, data in numbers.items():
            number_records.append(
                {
                    "code": code,
                    "name": data["name"],
                    "town_id": town_code_to_id.get(data["town_code"]),
                    "coord_x": data["coord_x"],
                    "coord_y": data["coord_y"],
                }
            )

        _logger.debug("Sample number record: %s", number_records[:1])
        created_numbers = self.env["ruian.number"].create(number_records)
        _logger.info("   Successfully created %d numbers", len(created_numbers))
        number_code_to_id = {n.code: n.id for n in created_numbers}
        _logger.debug(
            "   Sample number mapping: %s", dict(list(number_code_to_id.items())[:3])
        )

        # Process relationships
        _logger.info("🔗 Processing relationships...")

        # Street-Town relationships
        total_st = sum(len(v) for v in street_towns.values())
        _logger.info("   Processing %d street-town relationships", total_st)
        self._process_relationships(
            street_towns, street_name_to_id, town_code_to_id, "town_ids"
        )

        # Street-Number relationships
        total_sn = sum(len(v) for v in street_numbers.values())
        _logger.info("   Processing %d street-number relationships", total_sn)
        self._process_relationships(
            street_numbers, street_name_to_id, number_code_to_id, "number_ids"
        )

        _logger.info("🎉 CSV processing completed successfully!")

    def _get_number_name(self, record):
        """Generate display name for address number"""
        components = [
            record.get("Číslo domovní", ""),
            record.get("Číslo orientační", ""),
            record.get("Znak čísla orientačního", ""),
        ]
        return " ".join(filter(None, components)).strip()

    def _process_relationships(self, relations, street_map, target_map, field_name):
        """Relationship processor with detailed logging"""
        processed = 0
        skipped_streets = 0
        skipped_targets = 0

        for street_name, target_codes in relations.items():
            street_id = street_map.get(street_name)
            if not street_id:
                _logger.debug("🚨 Street not found: %s", street_name)
                skipped_streets += 1
                continue

            target_ids = []
            for code in target_codes:
                if code in target_map:
                    target_ids.append(target_map[code])
                else:
                    _logger.debug(
                        "   ⚠️ Target code not found: %s (street: %s)", code, street_name
                    )
                    skipped_targets += 1

            if target_ids:
                self.env["ruian.street"].browse(street_id).write(
                    {field_name: [(6, 0, target_ids)]}
                )
                processed += 1

        _logger.info("   Relationship processing results:")
        _logger.info("   - Successfully processed: %d", processed)
        _logger.info("   - Skipped streets: %d", skipped_streets)
        _logger.info("   - Skipped targets: %d", skipped_targets)
        _logger.info(
            "   - Total attempted relationships: %d",
            processed + skipped_streets + skipped_targets,
        )
