"""Evalueaza Sherlock pe dosarele de firme si PFA si il compara cu verificarea clasica la ANAF.

    python run_eval.py                          # setul de TEST, offline (determinist, cateva secunde)
    python run_eval.py --set calibrare          # setul pe care ajustam pragurile
    python run_eval.py --mode llm --limit 20    # agentul cu LLM, pe 20 de dosare din test
    python run_eval.py --mode llm --workers 4   # in paralel
    python run_eval.py --config simplu          # un singur agent (fara sub-agenti si fara solicitare de documente)
    python run_eval.py --comparatie             # verificare clasica vs agent simplu vs multi-agent vs multi-agent + documente

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
from sherlock.multi_agent import investigate_multi_agent_folder, raspuns_client  # noqa: E402
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


CONFIGS = {
    "simplu": "Agent simplu",
    "multi_agent": "Multi-agent",
    "complet": "Multi-agent + solicitare documente",
}


def run_case(case_id, config, llm):
    folder = str(DATA / "dosare" / case_id)
    mode = "llm" if llm else "offline"
    if config == "simplu":
        return investigate_folder(folder, mode=mode, domeniu="firme", llm=llm)
    if config == "multi_agent":
        return investigate_multi_agent_folder(folder, mode=mode, llm=llm)
    x = raspuns_client(folder, str(DATA / "suplimentare" / case_id), mode=mode, llm=llm)
    r = dict(x["dupa"])
    r["documente_cerute_initial"] = x["inainte"]["documente_cerute"]
    r["client_a_raspuns"] = x["client_a_raspuns"]
    r["verdict_inainte_de_documente"] = x["inainte"]["verdict"]
    r["durata_sec"] = round(x["inainte"]["durata_sec"] + (x["dupa"]["durata_sec"] if x["dupa"] is not x["inainte"] else 0), 2)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="test", choices=["test", "calibrare", "toate"])
    ap.add_argument("--mode", default="offline", choices=["offline", "llm", "auto"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--config", default="complet", choices=list(CONFIGS))
    ap.add_argument("--comparatie", action="store_true")
    args = ap.parse_args()
    if args.comparatie:
        return comparatie(args)

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
        r = run_case(case_id, args.config, llm)
        (out_dir / f"{case_id}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
        return case_id, r

    t0 = time.time()
    print(f"Evaluez {len(ids)} dosare (set={args.set}, mod={'llm' if llm else 'offline'}, configuratie={CONFIGS[args.config]})...")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        results = dict(ex.map(run, ids))
    metrici, ratate, alarme_false = evaluate(ids, labels, results, t0)
    metrici.update(set=args.set, mod="llm" if llm else "offline", configuratie=args.config)
    name = f"metrici_{args.set}_{metrici['mod']}" + ("" if args.config == "complet" else f"_{args.config}") + ".json"
    (DATA / name).write_text(json.dumps(metrici, indent=1, ensure_ascii=False), encoding="utf-8")
    report(metrici, ratate, alarme_false, args.verbose)
    print(f"\nMetrici salvate in data/firme/{name}")


def evaluate(ids, labels, results, t0):
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

    docs_cerute = sum(1 for i in ids if results[i].get("documente_cerute_initial"))
    m = {k: rate(*v) for k, v in conf.items()}
    n_legit = sum(1 for i in ids if labels[i]["eticheta"] != "FRAUDA")
    metrici = {
        "dosare": len(ids), "dosare_cu_documente_cerute": docs_cerute,
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
    return metrici, ratate, alarme_false


def report(metrici, ratate, alarme_false, verbose=False):
    s, c, bani, per_tipar = metrici["sherlock"], metrici["verificare_clasica_anaf"], metrici["bani"], metrici["pe_tipar_de_frauda"]
    print("\n" + "=" * 72)
    print(f"{'':34}{'Verificare clasica':>20}{'Sherlock':>16}")
    print("-" * 72)
    print(f"{'Fraude prinse (recall)':34}{c['recall']:>20.0%}{s['recall']:>16.0%}")
    print(f"{'Precizie (alarme corecte)':34}{c['precizie']:>20.0%}{s['precizie']:>16.0%}")
    print(f"{'Rata alarme false':34}{c['rata_alarme_false']:>20.1%}{s['rata_alarme_false']:>16.1%}")
    print(f"{'Credite frauduloase oprite':34}{lei(bani['oprite_de_verificarea_clasica']):>20}{lei(bani['oprite_de_sherlock']):>16}")
    print("-" * 72)
    print(f"Credite frauduloase in set: {lei(bani['credite_frauduloase_total'])}  |  pierderi evitate in plus: {lei(bani['pierderi_evitate_in_plus'])}")
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
        if verbose:
            for c_, t_, msgs in alarme_false:
                print(f"  {c_}: {msgs}")


def comparatie(args):
    """Aceleasi dosare, patru moduri de lucru: arata ce aduce fiecare strat al lui Sherlock."""
    labels = json.loads((DATA / "etichete.json").read_text(encoding="utf-8"))
    ids = [k for k, v in sorted(labels.items()) if args.set == "toate" or v["set"] == args.set]
    rows, clasic = [], None
    for cfg, nume in CONFIGS.items():
        t0 = time.time()
        results = {i: run_case(i, cfg, None) for i in ids}
        m, _, _ = evaluate(ids, labels, results, t0)
        clasic = clasic or m["verificare_clasica_anaf"] | {"bani": m["bani"]["oprite_de_verificarea_clasica"], "revizuire": None}
        rows.append({"configuratie": nume, "recall": m["sherlock"]["recall"], "precizie": m["sherlock"]["precizie"],
                     "alarme_false": m["sherlock"]["fp"], "legitime_la_revizuire": m["legitime_trimise_la_revizuire"],
                     "fraude_ajunse_la_analist": m["fraude_ajunse_la_analist"], "bani_opriti": m["bani"]["oprite_de_sherlock"],
                     "documente_cerute": m["dosare_cu_documente_cerute"]})
    rows.insert(0, {"configuratie": "Verificare clasica ANAF", "recall": clasic["recall"], "precizie": clasic["precizie"],
                    "alarme_false": clasic["fp"], "legitime_la_revizuire": None, "fraude_ajunse_la_analist": clasic["recall"],
                    "bani_opriti": clasic["bani"], "documente_cerute": 0})
    (DATA / f"metrici_comparatie_{args.set}.json").write_text(json.dumps({"set": args.set, "dosare": len(ids), "randuri": rows},
                                                                          indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nComparatie pe setul {args.set} ({len(ids)} dosare, offline)\n")
    print(f"{'Configuratie':38}{'Recall':>8}{'Precizie':>10}{'Alarme false':>14}{'Legit. la revizuire':>21}{'Bani opriti':>16}")
    print("-" * 107)
    for r in rows:
        rev = "-" if r["legitime_la_revizuire"] is None else f"{r['legitime_la_revizuire']:.0%}"
        print(f"{r['configuratie']:38}{r['recall']:>8.0%}{r['precizie']:>10.0%}{r['alarme_false']:>14}{rev:>21}{lei(r['bani_opriti']):>16}")
    print(f"\nSalvat in data/firme/metrici_comparatie_{args.set}.json")


if __name__ == "__main__":
    main()
