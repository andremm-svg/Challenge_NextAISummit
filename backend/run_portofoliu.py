"""Scanarea portofoliului de credite.   python run_portofoliu.py [--date murdare] [--workers 8]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sherlock.portofoliu import scaneaza  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def lei(x):
    return f"{x:,.0f} lei".replace(",", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="curate", choices=["curate", "murdare"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    r = scaneaza(workers=a.workers, date=a.date)
    print(f"Portofoliu scanat: {r['dosare_scanate']} dosare, expunere {lei(r['expunere_totala'])} ({r['durata_sec']}s)\n")
    for v, x in r["pe_verdict"].items():
        print(f"  {v:16} {x['dosare']:>4} dosare   {lei(x['expunere']):>18}")
    print(f"\nExpunere la risc (suspect + revizuire): {lei(r['expunere_la_risc'])}")
    print(f"\nGrupuri de firme legate: {len(r['grupuri'])} (cu dosare suspecte: {r['grupuri_cu_dosare_suspecte']})")
    for g in r["grupuri"][:8]:
        print(f"  {len(g['dosare'])} firme, {lei(g['expunere'])}, {', '.join(g['motive'])}, suspecte {g['suspecte']}: {', '.join(g['dosare'])}")
    print("\nPrioritati pentru echipa antifrauda:")
    for p in r["prioritati"][:10]:
        print(f"  {p['dosar']} {p['denumire'][:28]:28} {p['verdict']:16} risc {p['scor_risc']:>3}  {lei(p['suma']):>15}  {(p['problema_principala'] or '')[:70]}")
    if r["schimbari_fata_de_scanarea_anterioara"] is not None:
        print(f"\nSchimbari fata de scanarea din {r['scanare_anterioara']}: {len(r['schimbari_fata_de_scanarea_anterioara'])}")
        for s in r["schimbari_fata_de_scanarea_anterioara"][:10]:
            print(f"  {s['dosar']} {s['denumire']}: {s['inainte']} -> {s['acum']}")


if __name__ == "__main__":
    main()
