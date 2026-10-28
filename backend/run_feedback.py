"""Bucla de feedback, simulata pe datele sintetice.

    python run_feedback.py               # analistii confirma dosarele din CALIBRARE -> propuneri de praguri -> efect pe TEST
    python run_feedback.py --aplica --analist "Ana Pop"   # scrie propunerile in config.yaml (aprobare umana, cu jurnal)

Simularea: pentru fiecare dosar din setul de calibrare, "analistul" confirma eticheta reala (FRAUDA / LEGITIM).
Feedback-ul se scrie intr-o baza separata (data/feedback_simulare.db), nu in cea reala.
Masuratorile vin din prima runda a investigatiei (inainte de documentele cerute clientului), unde actioneaza pragurile.
Efectul se masoara pe setul de TEST, pe care pragurile propuse nu l-au vazut.
"""
import argparse
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from run_eval import evaluate, run_case  # noqa: E402
from sherlock import feedback  # noqa: E402
from sherlock.firme import tools as T  # noqa: E402
from sherlock.multi_agent import investigate_multi_agent_folder  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_SIM = ROOT / "data" / "feedback_simulare.db"


def simuleaza_feedback(labels) -> None:
    DB_SIM.unlink(missing_ok=True)
    ids = [k for k, v in sorted(labels.items()) if v["set"] == "calibrare"]
    for k in ids:
        r = investigate_multi_agent_folder(str(T.DATA / "dosare" / k), mode="offline")
        et = labels[k]["eticheta"]
        decizie = "trimis_antifrauda" if et == "FRAUDA" else "aprobat_pentru_evaluare"
        feedback.inregistreaza(k, "analist_simulat", decizie, r["verdict"], et, feedback.din_raport(r, et), r["masuratori"], db=DB_SIM)
    print(f"Feedback simulat pentru {len(ids)} dosare din setul de calibrare -> {DB_SIM.name}")


def metrici_test(labels, config: str) -> dict:
    ids = [k for k, v in sorted(labels.items()) if v["set"] == "test"]
    t0 = time.time()
    m, _, _ = evaluate(ids, labels, {i: run_case(i, config, None) for i in ids}, t0)
    return {"recall": m["sherlock"]["recall"], "precizie": m["sherlock"]["precizie"], "alarme_false": m["sherlock"]["fp"],
            "legitime_la_revizuire": m["legitime_trimise_la_revizuire"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplica", action="store_true")
    ap.add_argument("--analist", default="")
    args = ap.parse_args()
    labels = json.loads((T.DATA / "etichete.json").read_text(encoding="utf-8"))
    simuleaza_feedback(labels)

    rap = feedback.raport(DB_SIM)
    print("\nPrecizia alarmelor, pe verificare (feedback-ul analistilor):")
    for v, x in rap["pe_verificare"].items():
        print(f"  {v:22} {x['confirmate']:>3}/{x['alarme']:<3} confirmate  ({x['precizie']:.0%})")

    propuneri = feedback.propune_praguri(DB_SIM)
    print("\nPropuneri de recalibrare (necesita aprobare umana):")
    for p in propuneri:
        if p["propus"] is None:
            print(f"  {p['prag']:30} {p['actual']} -> neschimbat: {p['motiv']}")
        else:
            print(f"  {p['prag']:30} {p['actual']} -> {p['propus']}  ({p['motiv']}; pe feedback: fraude {p['efect_pe_feedback']['fraude_prinse']}, "
                  f"alarme false {p['efect_pe_feedback']['alarme_false']})")
    noi = {p["prag"]: p["propus"] for p in propuneri if p["propus"] is not None}
    if not noi:
        print("\nNicio schimbare propusa.")
        return

    print("\nValidare pe setul de TEST (nevazut la propunere), fiecare propunere separat:")
    original = copy.deepcopy(T.CONFIG)
    baza = {cfg: metrici_test(labels, cfg) for cfg in ("simplu", "complet")}
    validare, recomandate = {}, {}
    for k, v in noi.items():
        s, c = k.split(".")
        T.CONFIG[s][c] = v
        dupa = {cfg: metrici_test(labels, cfg) for cfg in baza}
        T.CONFIG.clear()
        T.CONFIG.update(copy.deepcopy(original))
        ok = all(dupa[x]["recall"] >= baza[x]["recall"] and dupa[x]["alarme_false"] <= baza[x]["alarme_false"] for x in baza)
        validare[k] = {"propus": v, "inainte": baza, "dupa": dupa, "recomandat": ok}
        if ok:
            recomandate[k] = v
        for cfg in baza:
            i, d = baza[cfg], dupa[cfg]
            print(f"  {k:28} {cfg:8} recall {i['recall']:.0%} -> {d['recall']:.0%} | alarme false {i['alarme_false']} -> {d['alarme_false']} | "
                  f"legitime la analist {i['legitime_la_revizuire']:.0%} -> {d['legitime_la_revizuire']:.0%}")
        print(f"  {'':28} => {'RECOMANDAT' if ok else 'RESPINS: pe date noi pierde fraude sau adauga alarme false'}")
    (T.DATA / "feedback_simulare.json").write_text(json.dumps({"raport": rap, "propuneri": propuneri, "validare_test": validare},
                                                               indent=1, ensure_ascii=False), encoding="utf-8")
    if not recomandate:
        print("\nNicio propunere nu trece validarea; pragurile raman neschimbate (de aceea nu se schimba automat).")
    elif args.aplica:
        e = feedback.aplica(recomandate, args.analist, "propuneri din feedback, validate pe setul de test")
        print(f"\nAplicat de {e['analist']}: {e['vechi']} -> {e['nou']} (jurnal: data/recalibrari.jsonl)")
    else:
        print(f"\nRecomandate: {recomandate}. Pentru a aplica: python run_feedback.py --aplica --analist \"Nume Prenume\"")


if __name__ == "__main__":
    main()
