"""
Agent 15: HCC Prioritization Agent
Maps gaps to HCC categories and revenue impact.
Knowledge: CMS V28 HCC mapping tables (free from CMS.gov).

The ICD-10 to HCC mapping file is downloaded from:
https://www.cms.gov/medicare/payment/medicare-advantage-rates-statistics/
risk-adjustment/2025-model-software/icd-10-mappings

This agent loads the FULL mapping file at startup — zero hardcoded entries.
It tries 4 sources in order:
  1. CMS_HCC_FILE environment variable
  2. Common file paths (data/hcc/*.csv)
  3. EnsureAI database table (tblHCC_ICD10_Mappings)
  4. If nothing found, logs download instructions
"""
import os
import csv
import logging
import pyodbc
from typing import Dict, List, Optional

log = logging.getLogger("ensureai.agents.hcc")

DEFAULT_HCC_DIR = os.environ.get("HCC_DATA_DIR", "data/hcc")


class HCCMatchingAgent:
    """Maps gaps to HCC categories and revenue impact.
    Loads FULL CMS V28 mapping file. Zero hardcoded entries."""

    def __init__(self):
        self.hcc_lookup = {}
        self._load_hcc_mappings()

    def _load_hcc_mappings(self):
        """Load HCC mappings. Try multiple sources in order."""

        # Source 1: Environment variable
        cms_file = os.environ.get("CMS_HCC_FILE", "")
        if cms_file and os.path.exists(cms_file):
            self._parse_cms_csv(cms_file)
            return

        # Source 2: Common file paths
        search_paths = [
            os.path.join(DEFAULT_HCC_DIR, "icd10_hcc_mappings.csv"),
            "data/hcc/icd10_hcc_mappings.csv",
            "data/cms_v28_mappings.csv",
            "icd10_hcc_mappings.csv",
        ]
        for path in search_paths:
            if os.path.exists(path):
                self._parse_cms_csv(path)
                return

        # Source 2b: Any CSV in HCC data dir
        if os.path.exists(DEFAULT_HCC_DIR):
            for f in os.listdir(DEFAULT_HCC_DIR):
                if f.endswith(".csv"):
                    self._parse_cms_csv(os.path.join(DEFAULT_HCC_DIR, f))
                    return

        # Source 3: EnsureAI database table
        try:
            self._load_from_database()
            if self.hcc_lookup:
                return
        except Exception:
            pass

        # Source 4: Nothing found — log instructions
        log.warning(
            "Agent 15 (HCC): No CMS V28 mapping file found.\n"
            "  To fix:\n"
            "  1. Download ICD-10→HCC mapping from CMS.gov:\n"
            "     https://www.cms.gov/medicare/payment/medicare-advantage-rates-statistics/"
            "risk-adjustment/2025-model-software/icd-10-mappings\n"
            "  2. Save CSV to: data/hcc/icd10_hcc_mappings.csv\n"
            "  3. Or set: CMS_HCC_FILE=/path/to/file.csv\n"
            "  4. Or create table tblHCC_ICD10_Mappings in EnsureAI database\n"
            "  HCC will return 'None' for all codes until loaded."
        )

    def _parse_cms_csv(self, filepath: str):
        """Parse CMS ICD-10→HCC CSV. Auto-detects column names."""
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                sample = f.read(2048)
                f.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t|")
                reader = csv.DictReader(f, dialect=dialect)
                fields = [fn.strip().lower().replace(" ", "_") for fn in (reader.fieldnames or [])]

                icd_col = self._find_col(fields, ["icd", "diagnosis_code", "icd10", "dx_code", "code"])
                hcc_col = self._find_col(fields, ["hcc", "cms_hcc", "hcc_category", "hcc_code", "payment_hcc"])
                desc_col = self._find_col(fields, ["description", "hcc_description", "label", "desc"])
                raf_col = self._find_col(fields, ["coefficient", "raf", "raf_value", "coeff"])

                if not icd_col or not hcc_col:
                    log.warning(f"HCC file {filepath}: cannot find ICD/HCC columns in: {fields}")
                    return

                count = 0
                for row in reader:
                    r = {k.strip().lower().replace(" ", "_"): (v.strip() if v else "") for k, v in row.items()}
                    icd = r.get(icd_col, "").upper()
                    hcc = r.get(hcc_col, "")
                    if not icd or not hcc:
                        continue
                    desc = r.get(desc_col, "") if desc_col else ""
                    raf = 0.0
                    if raf_col:
                        try:
                            raf = float(r.get(raf_col, "0"))
                        except (ValueError, TypeError):
                            raf = 0.0

                    entry = {
                        "hcc": f"HCC {hcc}" if not hcc.upper().startswith("HCC") else hcc,
                        "description": desc,
                        "raf": raf,
                    }
                    self.hcc_lookup[icd] = entry
                    self.hcc_lookup[icd.replace(".", "")] = entry
                    count += 1

                log.info(f"Agent 15 (HCC): Loaded {count} ICD-10→HCC mappings from {filepath}")
        except Exception as e:
            log.error(f"Agent 15 (HCC): Failed to parse {filepath}: {e}")

    def _load_from_database(self):
        """Load from tblHCC_ICD10_Mappings in EnsureAI database."""
        server = os.environ.get("DB_SERVER", "10.210.10.106")
        user = os.environ.get("DB_USER", "sa")
        pwd = os.environ.get("DB_PASSWORD", "Hari12@2026ab")
        db = os.environ.get("DB_ENSURE", "EnsureAI")
        driver = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
        if not all([server, user, pwd]):
            return

        conn = pyodbc.connect(
            f"DRIVER={{{driver}}};"
            f"SERVER={server};DATABASE={db};UID={user};PWD={pwd};"
            f"Encrypt=no;TrustServerCertificate=yes;Connection Timeout=30;"
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_NAME = 'tblHCC_ICD10_Mappings'"
        )
        if cursor.fetchone()[0] == 0:
            conn.close()
            return

        cursor.execute(
            "SELECT ICD10Code, HCCCategory, Description, RAFValue "
            "FROM tblHCC_ICD10_Mappings"
        )
        count = 0
        for row in cursor.fetchall():
            icd = str(row[0]).strip().upper()
            hcc = str(row[1]).strip()
            desc = str(row[2]).strip() if row[2] else ""
            raf = float(row[3]) if row[3] else 0.0
            entry = {
                "hcc": f"HCC {hcc}" if not hcc.upper().startswith("HCC") else hcc,
                "description": desc,
                "raf": raf,
            }
            self.hcc_lookup[icd] = entry
            self.hcc_lookup[icd.replace(".", "")] = entry
            count += 1
        conn.close()
        if count:
            log.info(f"Agent 15 (HCC): Loaded {count} mappings from tblHCC_ICD10_Mappings")

    def process(self, confidence_gaps: List[Dict]) -> List[Dict]:
        results = []
        for i, gap in enumerate(confidence_gaps):
            icd10 = gap.get("candidate_icd10", "")
            hcc = self._lookup_hcc(icd10)

            results.append({
                **gap,
                "hcc_category": hcc.get("hcc") if hcc else "None",
                "hcc_description": hcc.get("description") if hcc else "Not an HCC condition",
                "raf_value": hcc.get("raf", 0) if hcc else 0,
                "output_section": (
                    "Section A (lab-confirmed)"
                    if gap.get("evidence_strength") == "strong"
                    else "Section B (clinical-only)"
                ),
                "priority_rank": i + 1,
            })
        return results

    def _lookup_hcc(self, icd10: str) -> Optional[Dict]:
        """Lookup HCC. Exact match first, then progressive prefix."""
        if not icd10:
            return None
        icd = icd10.strip().upper()
        icd_nd = icd.replace(".", "")

        if icd in self.hcc_lookup:
            return self.hcc_lookup[icd]
        if icd_nd in self.hcc_lookup:
            return self.hcc_lookup[icd_nd]

        # Progressive prefix (E11.65 → E11.6 → E11)
        for length in range(len(icd_nd) - 1, 2, -1):
            prefix = icd_nd[:length]
            if prefix in self.hcc_lookup:
                return self.hcc_lookup[prefix]
        return None

    @staticmethod
    def _find_col(fields: List[str], candidates: List[str]) -> Optional[str]:
        for c in candidates:
            for f in fields:
                if c in f or f in c:
                    return f
        return None

    def get_stats(self) -> Dict:
        unique = len({v["hcc"] for v in self.hcc_lookup.values()})
        return {"total_icd_mappings": len(self.hcc_lookup) // 2, "unique_hccs": unique, "loaded": len(self.hcc_lookup) > 0}
