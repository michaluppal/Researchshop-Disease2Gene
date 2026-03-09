#!/usr/bin/env python3
"""
P1-C: Abstract screener threshold calibration.

Runs has_genetic_content() on a curated set of molecular genetics papers
(should all pass) and irrelevant papers (should all fail).

Usage: python scripts/threshold_calibration.py
"""
import json
import sys
from pathlib import Path

# Add python/ root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.abstract_screener import has_genetic_content

DATASET_PATH = Path(__file__).parent / "calibration_abstracts.json"
RESULTS_PATH = Path(__file__).parent / "calibration_results.json"
THRESHOLD = 5  # current default

def run_calibration():
    data = json.loads(DATASET_PATH.read_text())
    results = {"molecular_genetics": [], "irrelevant": [], "summary": {}}

    print(f"\n{'='*70}")
    print(f"Abstract Screener Threshold Calibration (threshold={THRESHOLD})")
    print(f"{'='*70}\n")

    # --- Molecular genetics papers (should all PASS) ---
    print("MOLECULAR GENETICS PAPERS (expected: all PASS)\n")
    mg_pass = 0
    for paper in data["molecular_genetics"]:
        ok, conf, details = has_genetic_content(paper["abstract"], paper["title"], threshold=THRESHOLD)
        status = "PASS" if ok else "FAIL"
        if ok:
            mg_pass += 1
        print(f"  {status}  [{paper['type']:25s}]  score={details['raw_score']:3d}  pmid={paper['pmid']}")
        if details.get("positive_keywords"):
            print(f"           keywords: {', '.join(details['positive_keywords'][:5])}")
        results["molecular_genetics"].append({
            "pmid": paper["pmid"], "type": paper["type"],
            "raw_score": details["raw_score"], "passed": ok,
            "positive_keywords": details.get("positive_keywords", []),
            "negative_keywords": details.get("negative_keywords", []),
        })

    # --- Irrelevant papers (should all FAIL) ---
    print(f"\nIRRELEVANT PAPERS (expected: all FAIL)\n")
    irr_fail = 0
    for paper in data["irrelevant"]:
        ok, conf, details = has_genetic_content(paper["abstract"], paper["title"], threshold=THRESHOLD)
        status = "PASS (false positive!)" if ok else "REJECT"
        if not ok:
            irr_fail += 1
        print(f"  {status}  [{paper['type']:25s}]  score={details['raw_score']:3d}  pmid={paper['pmid']}")
        results["irrelevant"].append({
            "pmid": paper["pmid"], "type": paper["type"],
            "raw_score": details["raw_score"], "passed": ok,
        })

    n_mg = len(data["molecular_genetics"])
    n_irr = len(data["irrelevant"])
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"  Molecular genetics: {mg_pass}/{n_mg} passed")
    print(f"  Irrelevant:         {irr_fail}/{n_irr} rejected")
    print(f"  Threshold:          {THRESHOLD} (current default)")
    if mg_pass < n_mg:
        print(f"\n  FALSE NEGATIVES DETECTED -- some molecular genetics papers scored below {THRESHOLD}")
        failed = [r for r in results["molecular_genetics"] if not r["passed"]]
        for f in failed:
            print(f"    - PMID {f['pmid']} ({f['type']}): score={f['raw_score']}")
    else:
        print(f"\n  No false negatives -- all molecular genetics papers pass at threshold={THRESHOLD}")
    fp = [r for r in results["irrelevant"] if r["passed"]]
    if fp:
        print(f"\n  FALSE POSITIVES DETECTED -- {len(fp)} irrelevant paper(s) passed screening")
    else:
        print(f"  No false positives -- all irrelevant papers correctly rejected")
    print(f"{'='*70}\n")

    results["summary"] = {
        "threshold": THRESHOLD,
        "mg_pass": mg_pass, "mg_total": n_mg,
        "irr_fail": irr_fail, "irr_total": n_irr,
        "false_negatives": [r for r in results["molecular_genetics"] if not r["passed"]],
        "false_positives": [r for r in results["irrelevant"] if r["passed"]],
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"Results saved to {RESULTS_PATH}")
    return results

if __name__ == "__main__":
    run_calibration()
