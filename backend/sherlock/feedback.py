"""Bucla de feedback: analistul confirma sau infirma constatarile, iar Sherlock propune praguri noi.

  1. inregistreaza(): decizia analistului + eticheta confirmata (FRAUDA / LEGITIM) + ce constatari au fost corecte
     + masuratorile din spatele lor (acoperirea fluxului, a salariilor etc.). Totul intr-o baza SQLite.
  2. raport(): cate alarme a confirmat analistul pentru fiecare verificare (precizia pe verificare), cate override-uri.
  3. propune_praguri(): pentru pragurile numerice, cauta valoarea care separa fraudele confirmate de dosarele
     legitime fara alarme false, pe feedback-ul existent. Sunt PROPUNERI.
  4. aplica(): un om aproba propunerile; abia atunci se scriu in config.yaml, cu jurnal (cine, cand, ce).

Pragurile nu se schimba niciodata singure: AI Act cere supraveghere umana, iar un prag gresit poate ascunde fraude.
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .firme import tools as T

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "feedback.db"
JURNAL = ROOT / "data" / "recalibrari.jsonl"

# prag -> (masuratoarea, directia: "sub" = valorile mici sunt suspecte, "peste" = valorile mari)
PRAGURI = {
    ("flux_cont", "critic_sub"): ("acoperire_flux", "sub"),
    ("salarii", "critic_sub"): ("acoperire_salarii", "sub"),
    ("contracte", "plati_critic_sub"): ("acoperire_plati_contract", "sub"),
    ("bilant_vs_anaf", "critic"): ("diferenta_bilant", "peste"),
}
MIN_EXEMPLE = 3


def _con(db: Path | None = None):
    con = sqlite3.connect(db or DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, dosar TEXT, analist TEXT, timestamp TEXT,
                   decizie TEXT, eticheta TEXT, verdict_sherlock TEXT, override INTEGER, comentariu TEXT,
                   constatari TEXT, masuratori TEXT)""")
    return con


def _override(verdict: str, decizie: str) -> bool:
    asteptat = {"CURAT": "aprobat_pentru_evaluare", "INCOMPLET": "cere_documente",
                "SUSPECT_FRAUDA": "trimis_antifrauda", "REVIZUIRE_UMANA": None}.get(verdict)
    return asteptat is not None and asteptat != decizie


def inregistreaza(dosar: str, analist: str, decizie: str, verdict_sherlock: str = "", eticheta: str | None = None,
                  constatari: list | None = None, masuratori: dict | None = None, comentariu: str = "", db: Path | None = None) -> dict:
    """constatari: [{"verificare": "flux_cont", "severitate": "CRITIC", "corecta": true}, ...]"""
    if eticheta not in (None, "FRAUDA", "LEGITIM"):
        raise ValueError("eticheta trebuie sa fie FRAUDA, LEGITIM sau goala")
    entry = {"dosar": dosar, "analist": analist, "timestamp": datetime.now().isoformat(timespec="seconds"),
             "decizie": decizie, "eticheta": eticheta, "verdict_sherlock": verdict_sherlock,
             "override": bool(verdict_sherlock) and _override(verdict_sherlock, decizie), "comentariu": comentariu,
             "constatari": constatari or [], "masuratori": masuratori or {}}
    with _con(db) as con:
        con.execute("INSERT INTO feedback(dosar, analist, timestamp, decizie, eticheta, verdict_sherlock, override, comentariu, "
                    "constatari, masuratori) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (dosar, analist, entry["timestamp"], decizie, eticheta, verdict_sherlock, int(entry["override"]), comentariu,
                     json.dumps(entry["constatari"], ensure_ascii=False), json.dumps(entry["masuratori"])))
    return entry


def toate(db: Path | None = None) -> list[dict]:
    """Ultimul feedback pentru fiecare dosar (un analist isi poate corecta decizia)."""
    with _con(db) as con:
        rows = con.execute("SELECT * FROM feedback ORDER BY id").fetchall()
    last = {}
    for r in rows:
        d = dict(r)
        d["constatari"], d["masuratori"], d["override"] = json.loads(d["constatari"]), json.loads(d["masuratori"]), bool(d["override"])
        last[d["dosar"]] = d
    return list(last.values())


def raport(db: Path | None = None) -> dict:
    fb = toate(db)
    pe_verificare = {}
    for f in fb:
        for c in f["constatari"]:
            if c.get("severitate") not in ("CRITIC", "AVERTIZARE"):
                continue
            v = pe_verificare.setdefault(c["verificare"], {"alarme": 0, "confirmate": 0, "infirmate": 0})
            v["alarme"] += 1
            v["confirmate" if c.get("corecta") else "infirmate"] += 1
    for v in pe_verificare.values():
        v["precizie"] = round(v["confirmate"] / v["alarme"], 3) if v["alarme"] else None
    return {"dosare_cu_feedback": len(fb), "fraude_confirmate": sum(f["eticheta"] == "FRAUDA" for f in fb),
            "legitime_confirmate": sum(f["eticheta"] == "LEGITIM" for f in fb),
            "override": sum(f["override"] for f in fb),
            "pe_verificare": dict(sorted(pe_verificare.items(), key=lambda kv: (kv[1]["precizie"] or 0)))}


def _impact(vals_f, vals_l, prag, directie):
    hit = (lambda v: v < prag) if directie == "sub" else (lambda v: abs(v) > prag)
    return sum(map(hit, vals_f)), sum(map(hit, vals_l))


def propune_praguri(db: Path | None = None, config: dict | None = None) -> list[dict]:
    config = config or T.CONFIG
    fb = [f for f in toate(db) if f["eticheta"]]
    out = []
    for (sectiune, cheie), (mas, directie) in PRAGURI.items():
        vf = [f["masuratori"][mas] for f in fb if f["eticheta"] == "FRAUDA" and mas in f["masuratori"]]
        vl = [f["masuratori"][mas] for f in fb if f["eticheta"] == "LEGITIM" and mas in f["masuratori"]]
        actual = config[sectiune][cheie]
        p = {"prag": f"{sectiune}.{cheie}", "masuratoare": mas, "actual": actual, "exemple_frauda": len(vf), "exemple_legitime": len(vl)}
        if len(vf) < MIN_EXEMPLE or len(vl) < MIN_EXEMPLE:
            out.append(p | {"propus": None, "motiv": f"date insuficiente (minim {MIN_EXEMPLE} fraude si {MIN_EXEMPLE} legitime confirmate)"})
            continue
        if directie == "peste":
            vf, vl = [abs(v) for v in vf], [abs(v) for v in vl]
        vals = sorted(set(vf + vl))
        cands = {actual} | {round((a + b) / 2, 3) for a, b in zip(vals, vals[1:])}
        tp0, fp0 = _impact(vf, vl, actual, directie)

        def score(t):  # nu pierde nicio frauda prinsa azi; apoi cat mai putine alarme false; apoi cat mai aproape de actual
            tp, fp = _impact(vf, vl, t, directie)
            return (tp >= tp0, -fp, tp, -abs(t - actual))

        best = max(sorted(cands), key=score)
        tp, fp = _impact(vf, vl, best, directie)
        if best == actual or (tp, fp) == (tp0, fp0):
            out.append(p | {"propus": None, "motiv": f"pragul actual e bun pe feedback ({tp0}/{len(vf)} fraude, {fp0} alarme false)"})
            continue
        out.append(p | {"propus": best, "efect_pe_feedback": {"fraude_prinse": f"{tp0} -> {tp} din {len(vf)}",
                                                             "alarme_false": f"{fp0} -> {fp} din {len(vl)}"},
                        "motiv": ("separa fraudele confirmate de dosarele legitime" if fp == 0 else "cel mai mic numar de alarme false"),
                        "valori": {"frauda_max" if directie == "sub" else "frauda_min": (max(vf) if directie == "sub" else min(vf)),
                                   "legitim_min" if directie == "sub" else "legitim_max": (min(vl) if directie == "sub" else max(vl))}})
    return out


def aplica(praguri: dict, analist: str, motiv: str = "", config_path: Path | None = None) -> dict:
    """praguri: {"flux_cont.critic_sub": 0.34}. Scrie in config.yaml (pastreaza comentariile) si in jurnal."""
    if not analist:
        raise ValueError("Recalibrarea trebuie aprobata de un analist (camp 'analist').")
    path = config_path or (T.BASE / "config.yaml")
    text = path.read_text(encoding="utf-8")
    vechi = {}
    for nume, val in praguri.items():
        sectiune, cheie = nume.split(".")
        if (sectiune, cheie) not in PRAGURI:
            raise ValueError(f"Prag necunoscut sau nemodificabil: {nume}")
        val = float(val)
        m = re.search(rf"(?ms)^{sectiune}:\n(.*?)(?=^\S|\Z)", text)
        if not m:
            raise ValueError(f"Sectiunea {sectiune} lipseste din config")
        bloc = m.group(1)
        nou_bloc, n = re.subn(rf"(?m)^(\s+{cheie}:\s*)([-\d.]+)", lambda x: f"{x.group(1)}{val}", bloc, count=1)
        if not n:
            raise ValueError(f"Cheia {nume} lipseste din config")
        vechi[nume] = T.CONFIG[sectiune][cheie]
        text = text[: m.start(1)] + nou_bloc + text[m.end(1):]
        T.CONFIG[sectiune][cheie] = val
    path.write_text(text, encoding="utf-8")
    entry = {"timestamp": datetime.now().isoformat(timespec="seconds"), "analist": analist, "motiv": motiv,
             "vechi": vechi, "nou": {k: float(v) for k, v in praguri.items()}}
    with JURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def din_raport(report: dict, eticheta: str | None) -> list[dict]:
    """Feedback-ul pe constatari dedus din eticheta confirmata: pe o frauda alarmele sunt corecte, pe un dosar legitim nu."""
    if eticheta is None:
        return []
    return [{"verificare": f["verificare"], "severitate": f["severitate"], "corecta": eticheta == "FRAUDA"}
            for f in report["constatari"] if f["severitate"] in ("CRITIC", "AVERTIZARE")]
