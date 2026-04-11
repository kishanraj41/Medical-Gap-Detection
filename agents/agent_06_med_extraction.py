"""
Agent 3: Medication Normalization Agent

Full pipeline matching the clinical workflow:
  EHR drug name → RxNorm (RxCUI) → RxClass → ATC + MED-RT

  RxNorm  = "What drug is this?" (standardize name → RxCUI)
  RxClass = "What class does it belong to?" (hub for ATC + MED-RT)
  ATC     = "How is it grouped globally?" (WHO classification)
  MED-RT  = "How does it work & what does it treat?" (mechanism + indication)

All APIs are free from NIH (rxnav.nlm.nih.gov). No key needed.
"""
import logging
import requests
from typing import Dict, List, Optional

log = logging.getLogger("ensureai.agents")


class MedicationExtractionAgent:
    """Normalizes medications via RxNorm + classifies via ATC and MED-RT.

    Pipeline:
      1. RxNorm API → get RxCUI (standard drug identifier)
      2. RxNorm API → get generic name
      3. RxClass API (relaSource=ATC) → WHO drug class hierarchy
      4. RxClass API (relaSource=MED-RT) → mechanism of action + drug→disease indication
      5. Merge ATC + MED-RT → inferred condition with confidence

    MED-RT provides EXPLICIT drug→disease links:
      - "may_treat" relationship: metformin may_treat Diabetes Mellitus
      - "mechanism_of_action": metformin → Biguanide → decreases hepatic glucose production
    ATC provides POPULATION-LEVEL grouping:
      - A10BA02 = Alimentary > Antidiabetics > Biguanides > Metformin

    Using BOTH gives us:
      - ATC: broad disease area (diabetes, cardiovascular, etc.)
      - MED-RT: specific disease the drug treats + how it works
    """

    RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"

    def __init__(self):
        """Initialize with PyHealth ATC lookup if available."""
        self.pyhealth_atc = None
        try:
            from pyhealth.medcode import InnerMap
            self.pyhealth_atc = InnerMap.load("ATC")
            log.info("Agent 3: PyHealth ATC loaded — drug indication lookup available")
        except Exception as e:
            log.info(f"Agent 3: PyHealth ATC not available ({e}), using RxNorm API only")

        # fhir.resources for medication status validation
        self.fhir_available = False
        try:
            from fhir.resources.medicationrequest import MedicationRequest
            self.fhir_available = True
            log.info("Agent 3: fhir.resources loaded — FHIR medication validation active")
        except ImportError:
            pass

        # OpenFDA for drug labeling (indications, warnings, interactions)
        self.openfda = None
        try:
            from .clinical_apis import get_openfda
            self.openfda = get_openfda()
            log.info("Agent 3: OpenFDA API loaded — drug label lookup active")
        except Exception:
            log.info("Agent 3: OpenFDA not available, using RxNorm/RxClass only")

    def process(self, extracted: Dict) -> List[Dict]:
        normalized = []
        for med in extracted.get("medications", []):
            drug_name = med.get("drug", "").strip()
            if not drug_name:
                continue

            # Step 1: Standardize drug name → RxCUI
            rxcui = self._lookup_rxcui(drug_name)

            # Step 2: Get generic name
            generic = self._lookup_generic(rxcui) if rxcui else drug_name

            # Step 3: ATC classification (population-level grouping)
            atc_info = self._lookup_rxclass(rxcui, "ATC") if rxcui else None

            # Step 4: MED-RT classification (mechanism + drug→disease indication)
            medrt_info = self._lookup_rxclass(rxcui, "MED-RT") if rxcui else None

            # Step 5: Merge — MED-RT indication takes priority, then ATC, then PyHealth
            inferred_condition = None
            indication_source = None

            if medrt_info and medrt_info.get("indication"):
                inferred_condition = medrt_info["indication"]
                indication_source = "MED-RT may_treat"
            elif atc_info and atc_info.get("inferred_condition"):
                inferred_condition = atc_info["inferred_condition"]
                indication_source = "ATC class inference"

            # Step 6: PyHealth ATC indication lookup (if available and no indication yet)
            pyhealth_indication = None
            if self.pyhealth_atc and atc_info and atc_info.get("class_id"):
                try:
                    pyhealth_indication = self.pyhealth_atc.lookup(
                        atc_info["class_id"], "indication"
                    )
                except Exception:
                    pass
            if not inferred_condition and pyhealth_indication:
                inferred_condition = str(pyhealth_indication)[:100]
                indication_source = "PyHealth ATC indication"

            normalized.append({
                "raw_name": drug_name,
                "rxnorm_code": rxcui,
                "generic_name": generic,
                # ATC fields
                "atc_code": atc_info.get("class_id") if atc_info else None,
                "atc_class": atc_info.get("class_name") if atc_info else None,
                "atc_parent": atc_info.get("parent_class") if atc_info else None,
                # MED-RT fields
                "medrt_indication": medrt_info.get("indication") if medrt_info else None,
                "medrt_mechanism": medrt_info.get("mechanism") if medrt_info else None,
                "medrt_class": medrt_info.get("class_name") if medrt_info else None,
                # Merged result
                "inferred_condition": inferred_condition,
                "indication_source": indication_source,
                "source": "RxNorm+RxClass API" if rxcui else "lookup_failed",
                "section": med.get("section"),
            })
        return normalized

    # ─── RxNorm: Standardize drug name → RxCUI ───

    def _lookup_rxcui(self, drug_name: str) -> Optional[str]:
        """RxNorm = 'What drug is this?' Returns unique RxCUI identifier."""
        try:
            resp = requests.get(
                f"{self.RXNORM_BASE}/rxcui.json",
                params={"name": drug_name},
                timeout=10,
            )
            data = resp.json()
            ids = data.get("idGroup", {}).get("rxnormId", [])
            if ids:
                return ids[0]
            # Try approximate match if exact fails
            resp2 = requests.get(
                f"{self.RXNORM_BASE}/approximateTerm.json",
                params={"term": drug_name, "maxEntries": 1},
                timeout=10,
            )
            data2 = resp2.json()
            candidates = data2.get("approximateGroup", {}).get("candidate", [])
            return candidates[0].get("rxcui") if candidates else None
        except Exception as e:
            log.warning(f"RxNorm lookup failed for {drug_name}: {e}")
            return None

    def _lookup_generic(self, rxcui: str) -> Optional[str]:
        """Get the standard generic name for a drug from RxCUI."""
        try:
            resp = requests.get(
                f"{self.RXNORM_BASE}/rxcui/{rxcui}/properties.json",
                timeout=10,
            )
            props = resp.json().get("properties", {})
            return props.get("name")
        except Exception:
            return None

    # ─── RxClass: Classification hub (ATC + MED-RT) ───

    def _lookup_rxclass(self, rxcui: str, source: str) -> Optional[Dict]:
        """RxClass = 'What class does it belong to?'
        source='ATC' → WHO population-level classification
        source='MED-RT' → mechanism of action + drug→disease indication"""
        try:
            resp = requests.get(
                f"{self.RXNORM_BASE}/rxclass/class/byRxcui.json",
                params={"rxcui": rxcui, "relaSource": source},
                timeout=10,
            )
            data = resp.json()
            classes = data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
            if not classes:
                return None

            if source == "ATC":
                return self._parse_atc(classes)
            elif source == "MED-RT":
                return self._parse_medrt(classes)
            return None
        except Exception as e:
            log.debug(f"RxClass {source} lookup failed for rxcui {rxcui}: {e}")
            return None

    def _parse_atc(self, classes: List[Dict]) -> Dict:
        """Parse ATC response. ATC = 'How is it grouped globally?'
        Returns the most specific ATC class + inferred disease area."""
        cls = classes[0].get("rxclassMinConceptItem", {})
        class_id = cls.get("classId", "")
        class_name = cls.get("className", "")
        inferred = self._atc_to_condition(class_id)
        return {
            "class_id": class_id,
            "class_name": class_name,
            "parent_class": class_id[:3] if len(class_id) >= 3 else class_id,
            "inferred_condition": inferred,
        }

    def _parse_medrt(self, classes: List[Dict]) -> Dict:
        """Parse MED-RT response. MED-RT = 'How does it work & what does it treat?'
        Extracts:
          - may_treat / may_prevent → disease indication
          - mechanism_of_action → how the drug works
          - pharmacokinetics → drug class"""
        indication = None
        mechanism = None
        class_name = None

        for entry in classes:
            concept = entry.get("rxclassMinConceptItem", {})
            rela = entry.get("minConcept", {}).get("rela", "") or entry.get("rela", "")
            name = concept.get("className", "")
            class_type = concept.get("classType", "")

            # may_treat = explicit drug→disease link
            if "may_treat" in rela.lower() or "may_prevent" in rela.lower():
                if not indication:
                    indication = name
            # mechanism_of_action
            elif "mechanism" in rela.lower() or class_type == "MOA":
                if not mechanism:
                    mechanism = name
            # pharmacokinetics / drug class
            elif class_type in ("PE", "PK", "EPC"):
                if not class_name:
                    class_name = name

        # If no explicit may_treat, try to get indication from class type
        if not indication:
            for entry in classes:
                concept = entry.get("rxclassMinConceptItem", {})
                ct = concept.get("classType", "")
                if ct == "DISEASE" or ct == "DIS":
                    indication = concept.get("className", "")
                    break

        return {
            "indication": indication,
            "mechanism": mechanism,
            "class_name": class_name or indication,
        }

    # ─── ATC fallback: broad disease area from ATC code prefix ───

    @staticmethod
    def _atc_to_condition(atc_code: str) -> Optional[str]:
        """Fallback: infer disease area from ATC hierarchy.
        Used when MED-RT does not return a may_treat indication.
        Based on WHO ATC classification structure."""
        atc_map = {
            "A02": "GERD/Acid Reflux",
            "A10": "Diabetes",
            "B01": "Thromboembolic Disorders",
            "B03": "Anemia",
            "C01": "Cardiac Disease",
            "C02": "Hypertension",
            "C03": "Hypertension/Edema",
            "C07": "Hypertension/Heart Disease",
            "C08": "Hypertension/Angina",
            "C09": "Hypertension/Heart Failure",
            "C10": "Hyperlipidemia",
            "G04": "Urology",
            "H02": "Inflammation/Autoimmune",
            "H03": "Thyroid Disease",
            "J01": "Bacterial Infection",
            "L01": "Cancer",
            "L04": "Immunosuppression/Autoimmune",
            "M01": "Musculoskeletal/Pain",
            "M05": "Osteoporosis",
            "N02": "Pain",
            "N03": "Epilepsy",
            "N05": "Psychiatric Disorders",
            "N05A": "Schizophrenia/Psychosis",
            "N06A": "Depression",
            "N06D": "Dementia",
            "R03": "Asthma/COPD",
            "S01": "Eye Disease",
            "V03": "Antidote/Detoxification",
        }
        for prefix, condition in sorted(atc_map.items(), key=lambda x: -len(x[0])):
            if atc_code.startswith(prefix):
                return condition
        return None
