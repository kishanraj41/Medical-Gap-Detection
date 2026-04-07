"""
FHIR REST Adapter — Replaces SQL-based data_extraction.py
Reads patient data from any FHIR R4 server via REST API.
Uses SHARP headers for context: X-FHIR-Server-URL, X-FHIR-Access-Token, X-Patient-ID

Output format is IDENTICAL to v20's PatientDataExtractor so all 33 agents work unchanged.
"""
import re
import logging
import requests
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Set

log = logging.getLogger("gapdetect.fhir")


class FHIRClient:
    """Connects to any FHIR R4 server using SHARP context headers."""

    def __init__(self, fhir_server_url: str, access_token: str = ""):
        self.base_url = fhir_server_url.rstrip("/")
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })
        if access_token:
            self.session.headers["Authorization"] = f"Bearer {access_token}"

    def get(self, resource_type: str, params: dict = None, resource_id: str = None) -> dict:
        """GET a FHIR resource or search."""
        if resource_id:
            url = f"{self.base_url}/{resource_type}/{resource_id}"
        else:
            url = f"{self.base_url}/{resource_type}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search(self, resource_type: str, params: dict) -> List[dict]:
        """Search and return all entries (handles pagination)."""
        all_entries = []
        params = dict(params)
        params.setdefault("_count", "100")
        url = f"{self.base_url}/{resource_type}"

        while url:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            bundle = resp.json()
            entries = bundle.get("entry", [])
            all_entries.extend([e.get("resource", {}) for e in entries])

            # Pagination — follow 'next' link
            url = None
            params = None  # params only on first request
            for link in bundle.get("link", []):
                if link.get("relation") == "next":
                    url = link.get("url")
                    break
        return all_entries


class FHIRPatientExtractor:
    """Extracts complete patient profile from FHIR R4 server.
    Output matches v20 PatientDataExtractor format exactly."""

    def __init__(self, client: FHIRClient):
        self.client = client

    def get_patient_demographics(self, patient_id: str) -> Dict:
        """Get patient demographics from FHIR Patient resource."""
        try:
            pt = self.client.get("Patient", resource_id=patient_id)
        except Exception as e:
            log.warning(f"Patient {patient_id} not found: {e}")
            return {"patient_id": patient_id, "found": False}

        # Parse name
        names = pt.get("name", [{}])
        official = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
        given = " ".join(official.get("given", []))
        family = official.get("family", "")
        full_name = f"{given} {family}".strip()

        # Parse DOB and age
        dob_str = pt.get("birthDate", "")
        age = None
        dob = None
        if dob_str:
            try:
                dob = datetime.strptime(dob_str[:10], "%Y-%m-%d").date()
                age = (date.today() - dob).days // 365
            except ValueError:
                pass

        age_category = ""
        if age is not None:
            age_category = "Child" if age < 18 else ("Adult" if age < 65 else "Old")

        # Parse address
        addresses = pt.get("address", [{}])
        addr = addresses[0] if addresses else {}
        city = addr.get("city", "")
        state = addr.get("state", "")
        postal = addr.get("postalCode", "")

        # Parse gender
        gender = pt.get("gender", "").lower()

        # Parse race/ethnicity from extensions (US Core)
        race = ""
        ethnicity = ""
        for ext in pt.get("extension", []):
            url = ext.get("url", "")
            if "us-core-race" in url:
                for sub in ext.get("extension", []):
                    if sub.get("url") == "text":
                        race = sub.get("valueString", "")
            elif "us-core-ethnicity" in url:
                for sub in ext.get("extension", []):
                    if sub.get("url") == "text":
                        ethnicity = sub.get("valueString", "")

        return {
            "patient_id": patient_id,
            "found": True,
            "first_name": given,
            "last_name": family,
            "full_name": full_name,
            "ensure_patient_id": patient_id,
            "dob": str(dob) if dob else None,
            "age": age,
            "age_category": age_category,
            "gender": gender,
            "address_city": city,
            "address_state": state,
            "address_postal": postal,
            "address": f"{city}, {state} {postal}".strip(", "),
            "country": "US",
            "race": race,
            "ethnicity": ethnicity,
            "insurance_name": "",
            "member_id": "",
        }

    def get_clinical_notes(self, patient_id: str) -> List[Dict]:
        """Get clinical notes from FHIR DocumentReference resources."""
        docs = self.client.search("DocumentReference", {"patient": patient_id})
        notes = []
        for doc in docs:
            for content in doc.get("content", []):
                att = content.get("attachment", {})
                data = att.get("data", "")
                ct = att.get("contentType", "")
                if not data or len(data) < 20:
                    continue
                try:
                    import base64
                    decoded = base64.b64decode(data).decode("utf-8", errors="replace")
                    if "html" in ct.lower():
                        clean = re.sub(r"<[^>]+>", " ", decoded)
                        clean = re.sub(r"\s+", " ", clean).strip()
                    else:
                        clean = decoded.strip()
                    if len(clean) < 20 or "not supported" in clean.lower():
                        continue

                    # Extract doc type
                    doc_type = ""
                    type_obj = doc.get("type", {})
                    codings = type_obj.get("coding", [])
                    if codings:
                        doc_type = codings[0].get("display", "") or codings[0].get("code", "")
                    if not doc_type:
                        doc_type = type_obj.get("text", "Clinical Note")

                    notes.append({
                        "attachment_id": doc.get("id", ""),
                        "doc_type": doc_type,
                        "doc_date": doc.get("date", "")[:10] if doc.get("date") else "",
                        "content_type": ct,
                        "text": clean,
                    })
                except Exception as e:
                    log.debug(f"Failed to decode note: {e}")
        log.info(f"Patient {patient_id}: extracted {len(notes)} clinical notes")
        return notes

    def get_observations(self, patient_id: str) -> List[Dict]:
        """Get observations/lab results from FHIR Observation resources."""
        obs_list = self.client.search("Observation", {
            "patient": patient_id,
            "category": "laboratory",
        })
        results = []
        for obs in obs_list:
            # Extract LOINC code
            code_obj = obs.get("code", {})
            codings = code_obj.get("coding", [])
            loinc = ""
            display = code_obj.get("text", "")
            for c in codings:
                if c.get("system", "") == "http://loinc.org":
                    loinc = c.get("code", "")
                    display = c.get("display", display)
                    break
            if not loinc and codings:
                loinc = codings[0].get("code", "")
                display = codings[0].get("display", display)

            # Extract value
            value = None
            unit = ""
            vq = obs.get("valueQuantity", {})
            if vq:
                value = vq.get("value")
                unit = vq.get("unit", "")
            elif obs.get("valueString"):
                try:
                    value = float(obs["valueString"])
                except (ValueError, TypeError):
                    pass

            # Reference range
            ref_low = None
            ref_high = None
            for rr in obs.get("referenceRange", []):
                low = rr.get("low", {})
                high = rr.get("high", {})
                if low.get("value") is not None:
                    ref_low = low["value"]
                if high.get("value") is not None:
                    ref_high = high["value"]

            # Interpretation
            interp = ""
            for i_obj in obs.get("interpretation", []):
                for ic in i_obj.get("coding", []):
                    interp = ic.get("code", "")
                    break

            results.append({
                "observation_id": obs.get("id", ""),
                "loinc": loinc,
                "name": display,
                "value": value,
                "unit": unit,
                "ref_range_low": ref_low,
                "ref_range_high": ref_high,
                "interpretation": interp,
                "date": (obs.get("effectiveDateTime", "") or obs.get("issued", ""))[:10],
                "status": obs.get("status", ""),
            })
        log.info(f"Patient {patient_id}: extracted {len(results)} observations")
        return results

    def get_medications(self, patient_id: str) -> List[Dict]:
        """Get medications from FHIR MedicationRequest resources."""
        meds = self.client.search("MedicationRequest", {"patient": patient_id})
        results = []
        for med in meds:
            # Extract medication name
            med_name = ""
            med_code = ""
            med_concept = med.get("medicationCodeableConcept", {})
            if med_concept:
                codings = med_concept.get("coding", [])
                if codings:
                    med_name = codings[0].get("display", "")
                    med_code = codings[0].get("code", "")
                if not med_name:
                    med_name = med_concept.get("text", "")

            # Dosage
            dosage_text = ""
            dosages = med.get("dosageInstruction", [])
            if dosages:
                dosage_text = dosages[0].get("text", "")

            results.append({
                "medication_id": med.get("id", ""),
                "name": med_name,
                "code": med_code,
                "status": med.get("status", ""),
                "dosage": dosage_text,
                "date": med.get("authoredOn", "")[:10] if med.get("authoredOn") else "",
            })
        log.info(f"Patient {patient_id}: extracted {len(results)} medications")
        return results

    def get_conditions(self, patient_id: str) -> List[Dict]:
        """Get coded conditions from FHIR Condition resources."""
        conditions = self.client.search("Condition", {"patient": patient_id})
        results = []
        for cond in conditions:
            code_obj = cond.get("code", {})
            codings = code_obj.get("coding", [])
            icd10 = ""
            display = code_obj.get("text", "")
            for c in codings:
                sys = c.get("system", "")
                if "icd-10" in sys.lower() or "icd10" in sys.lower():
                    icd10 = c.get("code", "")
                    display = c.get("display", display)
                    break
            if not icd10 and codings:
                icd10 = codings[0].get("code", "")
                display = codings[0].get("display", display)

            # Clinical status
            cs = cond.get("clinicalStatus", {})
            status_codings = cs.get("coding", [])
            clinical_status = status_codings[0].get("code", "") if status_codings else ""

            # Verification status
            vs = cond.get("verificationStatus", {})
            vs_codings = vs.get("coding", [])
            verification = vs_codings[0].get("code", "") if vs_codings else ""

            results.append({
                "condition_id": cond.get("id", ""),
                "icd10_code": icd10,
                "display": display,
                "clinical_status": clinical_status,
                "verification_status": verification,
                "onset_date": (cond.get("onsetDateTime", "") or "")[:10],
                "recorded_date": (cond.get("recordedDate", "") or "")[:10],
            })
        log.info(f"Patient {patient_id}: extracted {len(results)} conditions")
        return results

    def get_encounters(self, patient_id: str) -> List[Dict]:
        """Get encounters from FHIR Encounter resources."""
        encounters = self.client.search("Encounter", {"patient": patient_id})
        results = []
        for enc in encounters:
            enc_type = ""
            types = enc.get("type", [])
            if types:
                codings = types[0].get("coding", [])
                if codings:
                    enc_type = codings[0].get("display", "")
                if not enc_type:
                    enc_type = types[0].get("text", "")

            period = enc.get("period", {})
            results.append({
                "encounter_id": enc.get("id", ""),
                "type": enc_type,
                "status": enc.get("status", ""),
                "start_date": (period.get("start", "") or "")[:10],
                "end_date": (period.get("end", "") or "")[:10],
                "class": enc.get("class", {}).get("code", ""),
            })
        log.info(f"Patient {patient_id}: extracted {len(results)} encounters")
        return results

    def get_procedures(self, patient_id: str) -> List[Dict]:
        """Get procedures from FHIR Procedure resources."""
        procs = self.client.search("Procedure", {"patient": patient_id})
        results = []
        for proc in procs:
            code_obj = proc.get("code", {})
            codings = code_obj.get("coding", [])
            code = codings[0].get("code", "") if codings else ""
            name = codings[0].get("display", "") if codings else ""
            if not name:
                name = code_obj.get("text", "")

            results.append({
                "procedure_id": proc.get("id", ""),
                "code": code,
                "name": name,
                "date": (proc.get("performedDateTime", "") or proc.get("performedPeriod", {}).get("start", "") or "")[:10],
                "status": proc.get("status", ""),
            })
        log.info(f"Patient {patient_id}: extracted {len(results)} procedures")
        return results

    def get_coded_icd10_set(self, patient_id: str) -> Set[str]:
        """Get all ICD-10 codes from Condition resources for gap comparison."""
        conditions = self.get_conditions(patient_id)
        return {c["icd10_code"] for c in conditions if c.get("icd10_code")}

    def extract_patient(self, patient_id: str) -> Dict[str, Any]:
        """Extract complete clinical profile — matches v20 output format."""
        demographics = self.get_patient_demographics(patient_id)
        coded_conditions = self.get_coded_icd10_set(patient_id)

        profile = {
            "fhir_patient_id": patient_id,
            "ensure_patient_id": patient_id,
            "demographics": demographics,
            "clinical_notes": self.get_clinical_notes(patient_id),
            "observations": self.get_observations(patient_id),
            "medications": self.get_medications(patient_id),
            "conditions": self.get_conditions(patient_id),
            "encounters": self.get_encounters(patient_id),
            "procedures": self.get_procedures(patient_id),
            "claims_codes": coded_conditions,  # In FHIR-only mode, coded conditions = "claims"
        }
        log.info(
            f"Patient {patient_id}: FHIR profile extracted "
            f"({len(profile['clinical_notes'])} notes, "
            f"{len(profile['observations'])} labs, "
            f"{len(profile['medications'])} meds, "
            f"{len(profile['conditions'])} conditions, "
            f"{len(profile['encounters'])} encounters, "
            f"{len(profile['procedures'])} procedures)"
        )
        return profile

    def get_all_patient_ids(self, limit: int = 50) -> List[str]:
        """Get patient IDs from the FHIR server."""
        patients = self.client.search("Patient", {"_count": str(limit)})
        return [p.get("id", "") for p in patients if p.get("id")]
