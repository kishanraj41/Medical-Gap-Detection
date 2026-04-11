"""Ctrl+Alt+Heal — 33 Agent Pipeline (GPU/CPU Dual Mode)
30 CPU-only agents + 3 GPU/CPU dual-mode agents (6, 15, 31)"""

from .agent_01_input_sources import InputSourcesAgent
from .agent_02_doc_type import DocumentTypeAgent
from .agent_03_doc_norm import DocumentNormAgent
from .agent_04_measurement_year import MeasurementYearAgent
from .agent_05_section_detection import SectionDetectionAgent
from .agent_06_clinical_extraction import ClinicalExtractionAgent
from .agent_06_med_extraction import MedicationExtractionAgent
from .agent_07_medical_norm import MedicalNormAgent
from .agent_08_unit_norm import UnitNormAgent
from .agent_09_context_validation import ContextValidationAgent
from .agent_10_lab_interpretation import LabInterpretationAgent
from .agent_11_phenotype_rules import PhenotypeRulesAgent
from .agent_12_evidence_aggregation import EvidenceAggregationAgent
from .agent_13_patient_aggregation import PatientAggregationAgent
from .agent_14_contradiction import ContradictionAgent
from .agent_15_reconciliation import ReconciliationAgent
from .agent_16_clinical_validity import ClinicalValidityAgent
from .agent_17_evidence_sufficiency import EvidenceSufficiencyAgent
from .agent_18_icd10_mapping import ICD10MappingAgent
from .agent_19_coding_validation import CodingValidationAgent
from .agent_20_deduplication import DeduplicationAgent
from .agent_21_meat_validation import MEATValidationAgent
from .agent_22_hcc_matching import HCCMatchingAgent
from .agent_23_encounter_eligibility import EncounterEligibilityAgent
from .agent_24_provider_attribution import ProviderAttributionAgent
from .agent_25_claims_comparison import ClaimsComparisonAgent
from .agent_26_gap_decision import GapDecisionAgent
from .agent_27_versioned_rules import VersionedRuleAgent
from .agent_28_cohort_processing import CohortProcessingAgent
from .agent_29_confidence import ConfidenceAgent
from .agent_30_audit_trail import AuditTrailAgent
from .agent_31_rag_retrieval import RAGRetrievalAgent
from .agent_33_output import OutputAgent

__all__ = [
    "InputSourcesAgent", "DocumentTypeAgent", "DocumentNormAgent",
    "MeasurementYearAgent", "SectionDetectionAgent",
    "ClinicalExtractionAgent", "MedicationExtractionAgent",
    "MedicalNormAgent", "UnitNormAgent",
    "ContextValidationAgent", "LabInterpretationAgent",
    "PhenotypeRulesAgent", "EvidenceAggregationAgent", "PatientAggregationAgent",
    "ContradictionAgent", "ReconciliationAgent",
    "ClinicalValidityAgent", "EvidenceSufficiencyAgent",
    "ICD10MappingAgent", "CodingValidationAgent", "DeduplicationAgent",
    "MEATValidationAgent", "HCCMatchingAgent",
    "EncounterEligibilityAgent", "ProviderAttributionAgent",
    "ClaimsComparisonAgent", "GapDecisionAgent",
    "VersionedRuleAgent", "CohortProcessingAgent",
    "ConfidenceAgent", "AuditTrailAgent",
    "RAGRetrievalAgent",
    "OutputAgent",
]

AGENT_COUNT = 33
AGENT_MODES = {
    "agent_06_clinical_extraction": "GPU/CPU dual (ClinicalBERT or regex NER)",
    "agent_15_reconciliation": "GPU/CPU dual (LLaMA or rule-based reasoning)",
    "agent_31_rag_retrieval": "GPU/CPU dual (ChromaDB or static guidelines)",
}
