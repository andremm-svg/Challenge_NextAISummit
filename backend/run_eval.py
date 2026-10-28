"""Evalueaza Sherlock pe dosarele de firme si PFA si il compara cu verificarea clasica la ANAF.

    python run_eval.py                          # setul de TEST, offline (determinist, cateva secunde)
    python run_eval.py --set calibrare          # setul pe care ajustam pragurile
    python run_eval.py --mode llm --limit 20    # agentul cu LLM, pe 20 de dosare din test
    python run_eval.py --mode llm --workers 4   # in paralel

Reguli de onestitate: pragurile se ajusteaza DOAR pe setul de calibrare; rezultatele raportate sunt pe TEST.
"Verificarea clasica" = ce face azi o banca: identitate + statut fiscal + bilant comparat cu ANAF.
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sherlock.agent import investigate_folder, verdict_from  # noqa: E402
from sherlock.firme.tools import CHECKS_VERIFICARE_CLASICA, DATA  # noqa: E402
from sherlock.llm import get_llm  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def lei(x: float) -> str:
    return f"{x:,.0f} lei".replace(",", ".")


def rate(tp, fp, fn, tn):
    recall = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "recall": round(recall, 3), "precizie": round(precision, 3),
            "f1": round(f1, 3), "rata_alarme_false": round(fp / (fp + tn), 3) if fp + tn else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="test", choices=["test", "calibrare", "toate"])
    ap.add_argument("--mode", default="offline", choices=["offline", "llm", "auto"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    labels = json.loads((DATA / "etichete.json").read_text(encoding="utf-8"))
    ids = [k for k, v in sorted(labels.items()) if args.set == "toate" or v["set"] == args.set]
    if args.limit:  # esantion care pastreaza si fraude si dosare legitime
        fr = [i for i in ids if labels[i]["eticheta"] == "FRAUDA"]
        lg = [i for i in ids if labels[i]["eticheta"] != "FRAUDA"]
        k = max(1, round(args.limit * len(fr) / len(ids)))
        ids = sorted(fr[:k] + lg[: args.limit - k])

    llm = get_llm() if args.mode in ("llm", "auto") else None
    if args.mode == "llm" and llm is None:
        sys.exit("Mod llm cerut, dar LLM-ul nu e configurat in .env")
    out_dir = DATA / "rezultate" / ("llm" if llm else "offline")
    out_dir.mkdir(parents=True, exist_ok=True)

    def run(case_id):
        r = investigate_folder(str(DATA / "dosare" / case_id), mode="llm" if llm else "offline", domeniu="firme", llm=llm)
        (out_dir / f"{case_id}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        return case_id, r

    t0 = time.time()
    print(f"Evaluez {len(ids)} dosare (set={args.set}, mod={'llm' if llm else 'offline'})...")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        results = dict(ex.map(run, ids))

    conf = {"sherlock": [0, 0, 0, 0], "clasic": [0, 0, 0, 0]}  # tp, fp, fn, tn
    bani = {"sherlock": 0.0, "clasic": 0.0, "total_frauda": 0.0}
    per_tipar = defaultdict(lambda: {"total": 0, "sherlock": 0, "clasic": 0})
    revizuire_legit, timpi, ratate, alarme_false, frauda_la_om = 0, [], [], [], 0
    for cid in ids:
        lab, r = labels[cid], results[cid]
        is_fraud = lab["eticheta"] == "FRAUDA"
        flags = {"sherlock": r["verdict"] == "SUSPECT_FRAUDA",
                 "clasic": verdict_from(r["constatari"], CHECKS_VERIFICARE_CLASICA) == "SUSPECT_FRAUDA"}
        timpi.append(r["durata_sec"])
        for name, flag in flags.items():
            idx = (0 if flag else 2) if is_fraud else (1 if flag else 3)
            conf[name][idx] += 1
        if is_fraud:
            bani["total_frauda"] += lab["suma"]
            t = per_tipar[lab["tipar"]]
            t["total"] += 1
            for name, flag in flags.items():
                if flag:
                    t[name] += 1
                    bani[name] += lab["suma"]
            frauda_la_om += r["verdict"] in ("SUSPECT_FRAUDA", "REVIZUIRE_UMANA")
            if not flags["sherlock"]:
                ratate.append((cid, lab["tipar"], r["verdict"]))
        else:
            revizuire_legit += r["verdict"] == "REVIZUIRE_UMANA"
            if flags["sherlock"]:
                alarme_false.append((cid, lab["tipar"], [f["mesaj"] for f in r["constatari"] if f["severitate"] == "CRITIC"]))

    m = {k: rate(*v) for k, v in conf.items()}
    n_legit = sum(1 for i in ids if labels[i]["eticheta"] != "FRAUDA")
    metrici = {
        "set": args.set, "mod": "llm" if llm else "offline", "dosare": len(ids),
        "fraude": conf["sherlock"][0] + conf["sherlock"][2], "legitime": n_legit,
        "sherlock": m["sherlock"], "verificare_clasica_anaf": m["clasic"],
        "bani": {"credite_frauduloase_total": bani["total_frauda"], "oprite_de_sherlock": bani["sherlock"],
                 "oprite_de_verificarea_clasica": bani["clasic"],
                 "pierderi_evitate_in_plus": bani["sherlock"] - bani["clasic"]},
        "pe_tipar_de_frauda": dict(per_tipar),
        "fraude_ajunse_la_analist": round(frauda_la_om / max(1, conf["sherlock"][0] + conf["sherlock"][2]), 3),
        "legitime_trimise_la_revizuire": round(revizuire_legit / n_legit, 3) if n_legit else 0,
        "timp_mediu_sec": round(sum(timpi) / len(timpi), 2), "durata_totala_sec": round(time.time() - t0, 1),
        "ipoteza": "Un credit fraudulos e considerat pierdut integral (fara recuperari).",
    }
    (DATA / f"metrici_{args.set}_{metrici['mod']}.json").write_text(json.dumps(metrici, indent=1, ensure_ascii=False), encoding="utf-8")

    s, c = m["sherlock"], m["clasic"]
    print("\n" + "=" * 72)
    print(f"{'':34}{'Verificare clasica':>20}{'Sherlock':>16}")
    print("-" * 72)
    print(f"{'Fraude prinse (recall)':34}{c['recall']:>20.0%}{s['recall']:>16.0%}")
    print(f"{'Precizie (alarme corecte)':34}{c['precizie']:>20.0%}{s['precizie']:>16.0%}")
    print(f"{'Rata alarme false':34}{c['rata_alarme_false']:>20.1%}{s['rata_alarme_false']:>16.1%}")
    print(f"{'Credite frauduloase oprite':34}{lei(bani['clasic']):>20}{lei(bani['sherlock']):>16}")
    print("-" * 72)
    print(f"Credite frauduloase in set: {lei(bani['total_frauda'])}  |  pierderi evitate in plus: {lei(bani['sherlock'] - bani['clasic'])}")
    print(f"Fraude care NU au trecut neobservate (suspect sau revizuire umana): {metrici['fraude_ajunse_la_analist']:.0%}")
    print(f"Dosare legitime trimise la revizuire umana: {metrici['legitime_trimise_la_revizuire']:.0%}  |  "
          f"timp mediu: {metrici['timp_mediu_sec']}s / dosar")
    print("\nPe tipar de frauda (prinse / total):")
    for tipar, t in sorted(per_tipar.items()):
        print(f"  {tipar:22} clasic {t['clasic']}/{t['total']}   Sherlock {t['sherlock']}/{t['total']}")
    if ratate:
        print("\nFraude ratate de Sherlock:", ", ".join(f"{c_} ({t_}, {v_})" for c_, t_, v_ in ratate))
    if alarme_false:
        print("Alarme false:", ", ".join(f"{c_} ({t_})" for c_, t_, _ in alarme_false))
        if args.verbose:
            for c_, t_, msgs in alarme_false:
                print(f"  {c_}: {msgs}")
    print(f"\nMetrici salvate in data/firme/metrici_{args.set}_{metrici['mod']}.json")


if __name__ == "__main__":
    main()
