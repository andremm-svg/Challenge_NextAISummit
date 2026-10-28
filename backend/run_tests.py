"""Ruleaza toate dosarele de test si compara verdictul cu cel asteptat.

    python run_tests.py              # offline, fara cheie API (determinist)
    python run_tests.py --mode llm   # cu agentul Featherless
    python run_tests.py --verbose    # afiseaza si constatarile
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sherlock.agent import investigate_folder  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="offline", choices=["offline", "llm", "auto"])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    expected = json.loads((ROOT / "tests" / "expected.json").read_text(encoding="utf-8"))
    out_dir = ROOT / "tests" / "rezultate"
    out_dir.mkdir(exist_ok=True)
    passed = 0
    print(f"\n{'DOSAR':<24}{'ASTEPTAT':<18}{'OBTINUT':<18}{'TIMP':>7}  REZULTAT")
    print("-" * 78)
    for case_id, exp in expected.items():
        report = investigate_folder(str(ROOT / "data" / "dosare" / case_id), mode=args.mode)
        (out_dir / f"{case_id}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        checks_hit = {f["verificare"] for f in report["constatari"] if f["severitate"] not in ("OK", "INFO")}
        ok = report["verdict"] == exp["verdict"] and set(exp["trebuie_sa_contina"]) <= checks_hit
        passed += ok
        print(f"{case_id:<24}{exp['verdict']:<18}{report['verdict']:<18}{report['durata_sec']:>6}s  {'PASS' if ok else 'FAIL'}")
        if args.verbose or not ok:
            for f in report["constatari"]:
                if f["severitate"] != "OK":
                    print(f"    [{f['severitate']}] {f['verificare']}: {f['mesaj']}")
            if report["verificari_completate_automat"]:
                print(f"    completate automat: {report['verificari_completate_automat']}")
    print("-" * 78)
    print(f"{passed}/{len(expected)} dosare corecte. Rapoartele complete sunt in tests/rezultate/\n")
    sys.exit(0 if passed == len(expected) else 1)


if __name__ == "__main__":
    main()
