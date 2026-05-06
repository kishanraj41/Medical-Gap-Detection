"""
Lab NER Extraction from Clinical Notes
Extracts lab values directly from unstructured clinical text.

LOINC-specific NER label schema:
  LAB_ANALYTE    - what is being measured (glucose, hemoglobin, creatinine)
  LAB_SPECIMEN   - where it was measured from (blood, urine, serum)
  LAB_PROPERTY   - kind of measurement (mass, molar, presence, activity)
  LAB_TIMING     - when/under what condition (fasting, random, 2-hour)
  LAB_RESULT_VALUE - the observed value (180, 7.1, 96)
  LAB_UNIT       - measurement units (mg/dL, %, mEq/L)
  LAB_SCALE      - how results expressed (quantitative, ordinal, narrative)
  LAB_QUALIFIER  - modifiers (total, free, direct)
  LAB_BODY_SITE  - for swabs/tissue (nasal, throat, lung)
  LAB_METHOD     - testing method (enzymatic, immunoassay)

Pipeline: text → lab extraction → LOINC mapping → abnormal check → missed opportunity
"""
import re
import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("ensureai.agents")

# ── TOP 200 LAB DISAMBIGUATION RULES ──
# Maps common lab names/abbreviations to LOINC codes with full LOINC axis detail
LAB_DISAMBIGUATION = {
    # Diabetes
    "hba1c": {"loinc": "4548-4", "analyte": "Hemoglobin A1c", "specimen": "blood", "property": "mass fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "a1c": {"loinc": "4548-4", "analyte": "Hemoglobin A1c", "specimen": "blood", "property": "mass fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "hemoglobin a1c": {"loinc": "4548-4", "analyte": "Hemoglobin A1c", "specimen": "blood", "property": "mass fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "glycated hemoglobin": {"loinc": "4548-4", "analyte": "Hemoglobin A1c", "specimen": "blood", "property": "mass fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "glucose": {"loinc": "2345-7", "analyte": "Glucose", "specimen": "blood", "property": "mass concentration", "timing": "random", "scale": "quantitative", "unit": "mg/dL"},
    "fasting glucose": {"loinc": "1558-6", "analyte": "Glucose", "specimen": "blood", "property": "mass concentration", "timing": "fasting", "scale": "quantitative", "unit": "mg/dL"},
    "fbg": {"loinc": "1558-6", "analyte": "Glucose", "specimen": "blood", "property": "mass concentration", "timing": "fasting", "scale": "quantitative", "unit": "mg/dL"},
    "fbs": {"loinc": "1558-6", "analyte": "Glucose", "specimen": "blood", "property": "mass concentration", "timing": "fasting", "scale": "quantitative", "unit": "mg/dL"},
    "blood sugar": {"loinc": "2345-7", "analyte": "Glucose", "specimen": "blood", "property": "mass concentration", "timing": "random", "scale": "quantitative", "unit": "mg/dL"},
    "blood glucose": {"loinc": "2345-7", "analyte": "Glucose", "specimen": "blood", "property": "mass concentration", "timing": "random", "scale": "quantitative", "unit": "mg/dL"},
    # Kidney
    "egfr": {"loinc": "33914-3", "analyte": "eGFR", "specimen": "serum/plasma", "property": "volume rate", "timing": "", "scale": "quantitative", "unit": "mL/min/1.73m2"},
    "gfr": {"loinc": "33914-3", "analyte": "eGFR", "specimen": "serum/plasma", "property": "volume rate", "timing": "", "scale": "quantitative", "unit": "mL/min/1.73m2"},
    "creatinine": {"loinc": "2160-0", "analyte": "Creatinine", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "cr": {"loinc": "2160-0", "analyte": "Creatinine", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "bun": {"loinc": "3094-0", "analyte": "BUN", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "blood urea nitrogen": {"loinc": "3094-0", "analyte": "BUN", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "urea nitrogen": {"loinc": "3094-0", "analyte": "BUN", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "microalbumin": {"loinc": "14959-1", "analyte": "Microalbumin", "specimen": "urine", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/L"},
    "albumin creatinine ratio": {"loinc": "9318-7", "analyte": "Albumin/Creatinine Ratio", "specimen": "urine", "property": "mass ratio", "timing": "", "scale": "quantitative", "unit": "mg/g"},
    "acr": {"loinc": "9318-7", "analyte": "Albumin/Creatinine Ratio", "specimen": "urine", "property": "mass ratio", "timing": "", "scale": "quantitative", "unit": "mg/g"},
    # Lipids
    "cholesterol": {"loinc": "2093-3", "analyte": "Total Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "total cholesterol": {"loinc": "2093-3", "analyte": "Total Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "ldl": {"loinc": "2089-1", "analyte": "LDL Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "ldl cholesterol": {"loinc": "2089-1", "analyte": "LDL Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "ldl-c": {"loinc": "2089-1", "analyte": "LDL Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "hdl": {"loinc": "2085-9", "analyte": "HDL Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "hdl cholesterol": {"loinc": "2085-9", "analyte": "HDL Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "hdl-c": {"loinc": "2085-9", "analyte": "HDL Cholesterol", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "triglycerides": {"loinc": "2571-8", "analyte": "Triglycerides", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "tg": {"loinc": "2571-8", "analyte": "Triglycerides", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    # CBC
    "hemoglobin": {"loinc": "718-7", "analyte": "Hemoglobin", "specimen": "blood", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "g/dL"},
    "hgb": {"loinc": "718-7", "analyte": "Hemoglobin", "specimen": "blood", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "g/dL"},
    "hb": {"loinc": "718-7", "analyte": "Hemoglobin", "specimen": "blood", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "g/dL"},
    "hematocrit": {"loinc": "4544-3", "analyte": "Hematocrit", "specimen": "blood", "property": "volume fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "hct": {"loinc": "4544-3", "analyte": "Hematocrit", "specimen": "blood", "property": "volume fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "wbc": {"loinc": "6690-2", "analyte": "WBC", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*3/uL"},
    "white blood cell": {"loinc": "6690-2", "analyte": "WBC", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*3/uL"},
    "white blood cells": {"loinc": "6690-2", "analyte": "WBC", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*3/uL"},
    "platelet": {"loinc": "26515-7", "analyte": "Platelet Count", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*3/uL"},
    "platelets": {"loinc": "26515-7", "analyte": "Platelet Count", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*3/uL"},
    "plt": {"loinc": "26515-7", "analyte": "Platelet Count", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*3/uL"},
    "rbc": {"loinc": "789-8", "analyte": "RBC", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*6/uL"},
    "red blood cell": {"loinc": "789-8", "analyte": "RBC", "specimen": "blood", "property": "number concentration", "timing": "", "scale": "quantitative", "unit": "10*6/uL"},
    "mcv": {"loinc": "787-2", "analyte": "MCV", "specimen": "blood", "property": "volume", "timing": "", "scale": "quantitative", "unit": "fL"},
    "mch": {"loinc": "785-6", "analyte": "MCH", "specimen": "blood", "property": "mass", "timing": "", "scale": "quantitative", "unit": "pg"},
    "mchc": {"loinc": "786-4", "analyte": "MCHC", "specimen": "blood", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "g/dL"},
    "rdw": {"loinc": "788-0", "analyte": "RDW", "specimen": "blood", "property": "ratio", "timing": "", "scale": "quantitative", "unit": "%"},
    # CMP
    "sodium": {"loinc": "2951-2", "analyte": "Sodium", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "na": {"loinc": "2951-2", "analyte": "Sodium", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "potassium": {"loinc": "2823-3", "analyte": "Potassium", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "k": {"loinc": "2823-3", "analyte": "Potassium", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "chloride": {"loinc": "2075-0", "analyte": "Chloride", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "cl": {"loinc": "2075-0", "analyte": "Chloride", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "calcium": {"loinc": "17861-6", "analyte": "Calcium", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "ca": {"loinc": "17861-6", "analyte": "Calcium", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "magnesium": {"loinc": "2601-3", "analyte": "Magnesium", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "mg": {"loinc": "2601-3", "analyte": "Magnesium", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "phosphorus": {"loinc": "2777-1", "analyte": "Phosphorus", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "bicarbonate": {"loinc": "1963-8", "analyte": "Bicarbonate", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "co2": {"loinc": "2028-9", "analyte": "CO2", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mEq/L"},
    "albumin": {"loinc": "1968-7", "analyte": "Albumin", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "g/dL"},
    "total protein": {"loinc": "2885-2", "analyte": "Total Protein", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "g/dL"},
    # Liver
    "alt": {"loinc": "1742-6", "analyte": "ALT", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "sgpt": {"loinc": "1742-6", "analyte": "ALT", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "alanine aminotransferase": {"loinc": "1742-6", "analyte": "ALT", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "ast": {"loinc": "1920-8", "analyte": "AST", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "sgot": {"loinc": "1920-8", "analyte": "AST", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "aspartate aminotransferase": {"loinc": "1920-8", "analyte": "AST", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "bilirubin": {"loinc": "1975-2", "analyte": "Total Bilirubin", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "total bilirubin": {"loinc": "1975-2", "analyte": "Total Bilirubin", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    "direct bilirubin": {"loinc": "1968-7", "analyte": "Direct Bilirubin", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL", "qualifier": "direct"},
    "alkaline phosphatase": {"loinc": "1751-7", "analyte": "Alkaline Phosphatase", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "alk phos": {"loinc": "1751-7", "analyte": "Alkaline Phosphatase", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "alp": {"loinc": "1751-7", "analyte": "Alkaline Phosphatase", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "ldh": {"loinc": "2532-0", "analyte": "LDH", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "amylase": {"loinc": "1798-8", "analyte": "Amylase", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    # Thyroid
    "tsh": {"loinc": "3016-3", "analyte": "TSH", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mIU/L"},
    "thyroid stimulating hormone": {"loinc": "3016-3", "analyte": "TSH", "specimen": "serum/plasma", "property": "substance concentration", "timing": "", "scale": "quantitative", "unit": "mIU/L"},
    "free t4": {"loinc": "3024-7", "analyte": "Free T4", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/dL"},
    "ft4": {"loinc": "3024-7", "analyte": "Free T4", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/dL"},
    "t3": {"loinc": "3053-6", "analyte": "Total T3", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/dL"},
    "free t3": {"loinc": "3053-6", "analyte": "Free T3", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/dL"},
    # Cardiac
    "troponin": {"loinc": "10839-9", "analyte": "Troponin I", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    "troponin i": {"loinc": "10839-9", "analyte": "Troponin I", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    "troponin t": {"loinc": "49563-0", "analyte": "Troponin T (hs)", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "pg/mL"},
    "bnp": {"loinc": "30934-4", "analyte": "BNP", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "pg/mL"},
    "nt-probnp": {"loinc": "33762-6", "analyte": "NT-proBNP", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "pg/mL"},
    "pro-bnp": {"loinc": "33762-6", "analyte": "NT-proBNP", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "pg/mL"},
    "ck": {"loinc": "2157-6", "analyte": "CK", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "cpk": {"loinc": "2157-6", "analyte": "CK", "specimen": "serum/plasma", "property": "catalytic activity concentration", "timing": "", "scale": "quantitative", "unit": "U/L"},
    "ck-mb": {"loinc": "13969-1", "analyte": "CK-MB", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    # Coagulation
    "inr": {"loinc": "6301-6", "analyte": "INR", "specimen": "blood", "property": "ratio", "timing": "", "scale": "quantitative", "unit": "ratio"},
    "pt": {"loinc": "5902-2", "analyte": "Prothrombin Time", "specimen": "blood", "property": "time", "timing": "", "scale": "quantitative", "unit": "sec"},
    "ptt": {"loinc": "14979-9", "analyte": "aPTT", "specimen": "blood", "property": "time", "timing": "", "scale": "quantitative", "unit": "sec"},
    "aptt": {"loinc": "14979-9", "analyte": "aPTT", "specimen": "blood", "property": "time", "timing": "", "scale": "quantitative", "unit": "sec"},
    # Inflammation
    "crp": {"loinc": "1988-5", "analyte": "CRP", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/L"},
    "c-reactive protein": {"loinc": "1988-5", "analyte": "CRP", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/L"},
    "esr": {"loinc": "30341-2", "analyte": "ESR", "specimen": "blood", "property": "velocity", "timing": "", "scale": "quantitative", "unit": "mm/hr"},
    "sed rate": {"loinc": "30341-2", "analyte": "ESR", "specimen": "blood", "property": "velocity", "timing": "", "scale": "quantitative", "unit": "mm/hr"},
    # Iron
    "ferritin": {"loinc": "2276-4", "analyte": "Ferritin", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    "iron": {"loinc": "2498-4", "analyte": "Iron", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ug/dL"},
    "tibc": {"loinc": "2500-7", "analyte": "TIBC", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ug/dL"},
    "iron saturation": {"loinc": "14798-3", "analyte": "Iron Saturation", "specimen": "serum/plasma", "property": "mass fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    # Vitamins
    "vitamin d": {"loinc": "1989-3", "analyte": "Vitamin D (25-OH)", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    "vit d": {"loinc": "1989-3", "analyte": "Vitamin D (25-OH)", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    "25-oh vitamin d": {"loinc": "1989-3", "analyte": "Vitamin D (25-OH)", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    "vitamin b12": {"loinc": "2132-9", "analyte": "Vitamin B12", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "pg/mL"},
    "b12": {"loinc": "2132-9", "analyte": "Vitamin B12", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "pg/mL"},
    "folate": {"loinc": "2284-8", "analyte": "Folate", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    "folic acid": {"loinc": "2284-8", "analyte": "Folate", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    # Uric acid
    "uric acid": {"loinc": "3084-1", "analyte": "Uric Acid", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "mg/dL"},
    # PSA
    "psa": {"loinc": "2857-1", "analyte": "PSA", "specimen": "serum/plasma", "property": "mass concentration", "timing": "", "scale": "quantitative", "unit": "ng/mL"},
    # Urinalysis
    "ua": {"loinc": "5792-7", "analyte": "Urinalysis", "specimen": "urine", "property": "presence", "timing": "", "scale": "ordinal", "unit": ""},
    "urinalysis": {"loinc": "5792-7", "analyte": "Urinalysis", "specimen": "urine", "property": "presence", "timing": "", "scale": "ordinal", "unit": ""},
    "specific gravity": {"loinc": "5811-5", "analyte": "Specific Gravity", "specimen": "urine", "property": "relative density", "timing": "", "scale": "quantitative", "unit": ""},
    # ABG
    "pco2": {"loinc": "2019-8", "analyte": "pCO2", "specimen": "arterial blood", "property": "partial pressure", "timing": "", "scale": "quantitative", "unit": "mmHg"},
    "po2": {"loinc": "2703-7", "analyte": "pO2", "specimen": "arterial blood", "property": "partial pressure", "timing": "", "scale": "quantitative", "unit": "mmHg"},
    "o2 sat": {"loinc": "2708-6", "analyte": "O2 Saturation", "specimen": "blood", "property": "mass fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "spo2": {"loinc": "2708-6", "analyte": "O2 Saturation", "specimen": "blood", "property": "mass fraction", "timing": "", "scale": "quantitative", "unit": "%"},
    "ph": {"loinc": "2744-1", "analyte": "pH", "specimen": "arterial blood", "property": "concentration", "timing": "", "scale": "quantitative", "unit": ""},
}

# Regex to find lab value patterns in text: "Lab Name value unit" or "Lab Name: value"
LAB_VALUE_PATTERNS = [
    # "HbA1c 6.0" or "A1c = 7.1"
    re.compile(r'\b(' + '|'.join(re.escape(k) for k in sorted(LAB_DISAMBIGUATION.keys(), key=len, reverse=True)) + r')\s*[:=]?\s*(\d+\.?\d*)\s*(mg/dl|g/dl|%|meq/l|miu/l|ng/ml|pg/ml|u/l|ng/dl|fl|pg|mmhg|mm/hr|ug/dl|ng/ml|ml/min|ratio|sec)?', re.IGNORECASE),
    # "Hb 16.6" or "GFR 91" or "LDL 96"
    re.compile(r'\b(' + '|'.join(re.escape(k) for k in sorted(LAB_DISAMBIGUATION.keys(), key=len, reverse=True)) + r')\s+(\d+\.?\d*)', re.IGNORECASE),
]

# "wnl" / "normal" / "negative" pattern
WNL_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(k) for k in sorted(LAB_DISAMBIGUATION.keys(), key=len, reverse=True)) + r')\s+(wnl|normal|negative|within normal limits|unremarkable)', re.IGNORECASE)


class LabNERExtractor:
    """Extracts lab values from clinical note text using LOINC-specific NER labels.
    Pipeline: text → lab extraction → LOINC mapping → abnormal check → missed opportunity"""

    def __init__(self):
        self.lab_map = LAB_DISAMBIGUATION
        log.info(f"Lab NER: {len(self.lab_map)} lab disambiguation rules loaded")

    def extract_labs_from_text(self, text: str) -> List[Dict]:
        """Extract all lab mentions with values from clinical note text.
        Returns list of structured lab results with LOINC NER labels."""
        results = []
        seen = set()

        # Pattern 1: Lab name + numeric value (+ optional unit)
        for pattern in LAB_VALUE_PATTERNS:
            for match in pattern.finditer(text):
                lab_name = match.group(1).lower().strip()
                value_str = match.group(2)
                unit = match.group(3) if match.lastindex >= 3 and match.group(3) else ""

                if lab_name in self.lab_map:
                    info = self.lab_map[lab_name]
                    key = f"{info['loinc']}_{value_str}"
                    if key in seen:
                        continue
                    seen.add(key)

                    try:
                        value = float(value_str)
                    except ValueError:
                        continue

                    results.append({
                        "LAB_ANALYTE": info["analyte"],
                        "LAB_SPECIMEN": info["specimen"],
                        "LAB_PROPERTY": info["property"],
                        "LAB_TIMING": info.get("timing", ""),
                        "LAB_RESULT_VALUE": value,
                        "LAB_UNIT": unit or info["unit"],
                        "LAB_SCALE": info["scale"],
                        "LAB_QUALIFIER": info.get("qualifier", ""),
                        "LAB_BODY_SITE": "",
                        "LAB_METHOD": "",
                        "loinc": info["loinc"],
                        "raw_text": match.group(0),
                        "source": "clinical_note_extraction",
                    })

        # Pattern 2: Lab name + "wnl"/"normal" (no numeric value)
        for match in WNL_PATTERN.finditer(text):
            lab_name = match.group(1).lower().strip()
            status = match.group(2).lower()
            if lab_name in self.lab_map:
                info = self.lab_map[lab_name]
                key = f"{info['loinc']}_wnl"
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "LAB_ANALYTE": info["analyte"],
                    "LAB_SPECIMEN": info["specimen"],
                    "LAB_PROPERTY": info["property"],
                    "LAB_TIMING": info.get("timing", ""),
                    "LAB_RESULT_VALUE": None,
                    "LAB_UNIT": info["unit"],
                    "LAB_SCALE": info["scale"],
                    "LAB_QUALIFIER": info.get("qualifier", ""),
                    "LAB_BODY_SITE": "",
                    "LAB_METHOD": "",
                    "loinc": info["loinc"],
                    "raw_text": match.group(0),
                    "source": "clinical_note_wnl",
                    "interpretation": "normal/wnl",
                })

        log.info(f"Lab NER: extracted {len(results)} lab values from text "
                 f"({sum(1 for r in results if r['LAB_RESULT_VALUE'] is not None)} with values, "
                 f"{sum(1 for r in results if r['LAB_RESULT_VALUE'] is None)} wnl)")
        return results

    def resolve_loinc_with_llm(self, text: str, lab_name: str) -> Optional[Dict]:
        """Fallback: Use LLaMA to resolve ambiguous lab names to LOINC codes.
        Called when regex patterns don't match but LLM might understand context."""
        try:
            import requests
            prompt = (
                f"Given this clinical text: '{text[:500]}'\n"
                f"What LOINC code corresponds to the lab test '{lab_name}'?\n"
                f"Reply with ONLY the LOINC code (e.g., '4548-4') or 'UNKNOWN' if unsure."
            )
            resp = requests.post("http://localhost:11434/api/generate",
                                 json={"model": "llama3.1:8b", "prompt": prompt, "stream": False},
                                 timeout=30)
            if resp.status_code == 200:
                answer = resp.json().get("response", "").strip()
                # Validate it looks like a LOINC code
                if re.match(r'^\d{1,5}-\d$', answer):
                    return {"loinc": answer, "source": "llm_resolution"}
        except Exception:
            pass
        return None
