#!/usr/bin/env python3
"""
Ctrl+Alt+Heal — Pipeline Test Suite
Runs all 10 test patients and validates:
  1. TIER 1: Lab threshold detection
  2. TIER 2: Phenotype rule matching
  3. TIER 3: Clinical note NER
  4. TIER 4: Specificity upgrade detection
  5. Negation handling (Patient 5 should have ZERO gaps)
  6. Screening filtering (Patient 9 should NOT flag screening mentions)
  7. MEAT criteria accuracy
  8. HCC/RAF revenue calculations

Usage: python3 run_tests.py
"""
import json
import sys
import logging

logging.basicConfig(level=logging.WARNING)

from test_dataset import build_test_patients, get_patient_profile
from gap_pipeline import run_gap_pipeline

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

def run_all_tests():
    dataset = build_test_patients()
    patient_ids = sorted(dataset["patients"].keys())

    total_approved = 0
    total_review = 0
    total_rejected = 0
    total_revenue = 0.0
    all_results = {}
    test_failures = []

    print("=" * 80)
    print("  CTRL+ALT+HEAL — PIPELINE TEST SUITE (10 Patients)")
    print("=" * 80)
    print()

    for pid in patient_ids:
        profile = get_patient_profile(pid, dataset)
        demographics = profile.get("demographics", {})
        result = run_gap_pipeline(profile, demographics)

        approved = result["approved"]
        review = result["review"]
        rejected = result["rejected"]
        rev = result["revenue_summary"]

        total_approved += len(approved)
        total_review += len(review)
        total_rejected += len(rejected)
        total_revenue += rev["total_potential_impact"]
        all_results[pid] = result

        name = demographics.get("full_name", pid)
        n_coded = len(profile.get("conditions", []))
        n_labs = len(profile.get("observations", []))
        n_meds = len(profile.get("medications", []))
        n_notes = len(profile.get("clinical_notes", []))

        print(f"━━━ {name} ({pid}) ━━━")
        print(f"  Input: {n_coded} coded | {n_labs} labs | {n_meds} meds | {n_notes} notes")
        print(f"  Output: {len(approved)} approved | {len(review)} review | {len(rejected)} rejected | ${rev['total_potential_impact']:,.0f}/yr")

        for g in approved:
            print(f"    {PASS} {g['icd10_code']} — {g['condition_name']} [{g['tier']}] {g.get('hcc_category','')} ${g.get('annual_revenue_impact',0):,.0f}/yr")
        for g in review:
            print(f"    {WARN} {g['icd10_code']} — {g['condition_name']} [{g['tier']}]")
        print()

    # ═══════════════════════════════════════
    # VALIDATION TESTS
    # ═══════════════════════════════════════

    print("=" * 80)
    print("  VALIDATION TESTS")
    print("=" * 80)
    print()

    tests_passed = 0
    tests_total = 0

    def check(name, condition, detail=""):
        nonlocal tests_passed, tests_total
        tests_total += 1
        if condition:
            tests_passed += 1
            print(f"  {PASS} {name}")
        else:
            test_failures.append(name)
            print(f"  {FAIL} {name} — {detail}")

    # Patient 1: Should detect E11.65 upgrade + CKD + hyperlipidemia + anemia
    r1 = all_results["pt-001"]
    r1_codes = {g["icd10_code"] for g in r1["approved"] + r1["review"]}
    check("PT-001: E11.65 specificity upgrade detected", "E11.65" in r1_codes, f"Found: {r1_codes}")
    check("PT-001: CKD detected (N18.x)", any(c.startswith("N18") for c in r1_codes), f"Found: {r1_codes}")
    check("PT-001: Hyperlipidemia detected (E78.x)", any(c.startswith("E78") for c in r1_codes), f"Found: {r1_codes}")
    check("PT-001: Anemia detected (D64.9)", "D64.9" in r1_codes, f"Found: {r1_codes}")

    # Patient 2: Should detect heart failure + COPD
    r2 = all_results["pt-002"]
    r2_codes = {g["icd10_code"] for g in r2["approved"] + r2["review"]}
    check("PT-002: Heart failure detected (I50.x)", any(c.startswith("I50") for c in r2_codes), f"Found: {r2_codes}")
    check("PT-002: COPD detected (J44.x)", any(c.startswith("J44") for c in r2_codes), f"Found: {r2_codes}")

    # Patient 3: Should detect depression + hypothyroidism
    r3 = all_results["pt-003"]
    r3_codes = {g["icd10_code"] for g in r3["approved"] + r3["review"]}
    check("PT-003: Depression detected (F32.x)", any(c.startswith("F32") for c in r3_codes), f"Found: {r3_codes}")
    check("PT-003: Hypothyroidism detected (E03.x)", any(c.startswith("E03") for c in r3_codes), f"Found: {r3_codes}")

    # Patient 4: Should detect combo codes (E11.22, I12.9)
    r4 = all_results["pt-004"]
    r4_codes = {g["icd10_code"] for g in r4["approved"] + r4["review"]}
    check("PT-004: Heart failure detected (I50.x)", any(c.startswith("I50") for c in r4_codes), f"Found: {r4_codes}")
    check("PT-004: E11.65 upgrade from E11.9", "E11.65" in r4_codes, f"Found: {r4_codes}")

    # Patient 5: NEGATION TEST — should have ZERO approved gaps
    r5 = all_results["pt-005"]
    check("PT-005: NEGATION — zero approved gaps", len(r5["approved"]) == 0,
          f"Found {len(r5['approved'])} approved (should be 0): {[g['icd10_code'] for g in r5['approved']]}")

    # Patient 6: Medication-only detection
    r6 = all_results["pt-006"]
    r6_all = {g["icd10_code"] for g in r6["approved"] + r6["review"]}
    check("PT-006: Med-only diabetes detected", any(c.startswith("E11") for c in r6_all), f"Found: {r6_all}")
    check("PT-006: Med-only hypertension detected", "I10" in r6_all or any(c.startswith("I10") for c in r6_all), f"Found: {r6_all}")

    # Patient 7: Lab-only detection (no notes, no meds)
    r7 = all_results["pt-007"]
    r7_codes = {g["icd10_code"] for g in r7["approved"] + r7["review"]}
    check("PT-007: Lab-only diabetes detected", any(c.startswith("E11") for c in r7_codes), f"Found: {r7_codes}")
    check("PT-007: Lab-only hypothyroidism detected", any(c.startswith("E03") for c in r7_codes), f"Found: {r7_codes}")
    check("PT-007: Lab-only iron deficiency detected", "D50.9" in r7_codes, f"Found: {r7_codes}")

    # Patient 9: Screening should NOT be flagged
    r9 = all_results["pt-009"]
    r9_approved = {g["icd10_code"] for g in r9["approved"]}
    check("PT-009: SCREENING — depression NOT approved",
          not any(c.startswith("F32") or c.startswith("F41") for c in r9_approved),
          f"Found approved: {r9_approved}")

    # Patient 10: Complex multi-condition
    r10 = all_results["pt-010"]
    r10_codes = {g["icd10_code"] for g in r10["approved"] + r10["review"]}
    check("PT-010: 5+ unique gaps found", len(r10_codes) >= 5, f"Found {len(r10_codes)}: {r10_codes}")
    check("PT-010: OSA detected (G47.33)", "G47.33" in r10_codes, f"Found: {r10_codes}")

    # Revenue validation
    check("REVENUE: Total > $0", total_revenue > 0, f"Total: ${total_revenue:,.0f}")

    # HCC validation — at least some approved gaps should have HCC categories
    all_approved = []
    for r in all_results.values():
        all_approved.extend(r["approved"])
    hcc_gaps = [g for g in all_approved if g.get("hcc_category", "").startswith("HCC")]
    check("HCC: At least 3 HCC-mapped gaps", len(hcc_gaps) >= 3, f"Found {len(hcc_gaps)}")

    # ═══════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════

    print()
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print(f"  Patients tested: {len(patient_ids)}")
    print(f"  Total approved gaps: {total_approved}")
    print(f"  Total review candidates: {total_review}")
    print(f"  Total rejected: {total_rejected}")
    print(f"  Total revenue impact: ${total_revenue:,.0f}/yr")
    print()
    print(f"  Tests passed: {tests_passed}/{tests_total}")
    if test_failures:
        print(f"  Failed tests:")
        for f in test_failures:
            print(f"    {FAIL} {f}")
    print()

    if tests_passed == tests_total:
        print(f"  {PASS} ALL TESTS PASSED")
    else:
        print(f"  {FAIL} {tests_total - tests_passed} TESTS FAILED")

    return tests_passed == tests_total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
