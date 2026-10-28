"""Scanarea portofoliului: Sherlock re-verifica toti clientii, nu doar dosarul de azi.

  - fiecare dosar trece prin investigatia multi-agent (cu registrele de azi: statut fiscal, datorii, bilanturi noi);
  - retelele se cauta in TOT portofoliul, fara fereastra de timp: grupuri de firme legate prin acelasi
    administrator, telefon sau adresa, cu expunerea totala a bancii pe grup;
  - fata de scanarea anterioara se raporteaza ce s-a schimbat (dosare care au devenit suspecte).

Rezultatul e o lista de prioritati pentru echipa antifrauda, nu decizii.
"""
import json
import sqlite3
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .agent import SEV_ORDER, VERDICTE
from .firme import citire
from .firme.tools import DATA, DB_PATH
from .multi_agent import raspuns_client

ULTIMA = DATA / "portofoliu_ultima_scanare.json"


def _grupuri() -> list[dict]:
    """Componente conexe in graful solicitantilor (muchie = administrator / telefon / adresa comune)."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""SELECT c.dosar, c.suma, f.cui, f.denumire, f.adresa, f.telefon, a.nume AS admin
                                            FROM cereri_credit c JOIN firme f ON f.cui = c.cui
                                            LEFT JOIN administratori a ON a.cui = f.cui""")]
    con.close()
    parent = {r["dosar"]: r["dosar"] for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    motive = defaultdict(set)
    for cheie, eticheta in (("admin", "acelasi administrator"), ("telefon", "acelasi telefon"), ("adresa", "aceeasi adresa")):
        idx = defaultdict(list)
        for r in rows:
            if r[cheie] and not (cheie == "admin" and r["denumire"].endswith(" PFA")):  # PFA: titularul e chiar administratorul
                idx[citire.norm_key(r[cheie])].append(r["dosar"])
        for membri in idx.values():
            for m in membri[1:]:
                parent[find(m)] = find(membri[0])
            if len(membri) > 1:
                for m in membri:
                    motive[m].add(eticheta)
    comp = defaultdict(list)
    for r in rows:
        comp[find(r["dosar"])].append(r)
    out = []
    for membri in comp.values():
        if len(membri) < 2:
            continue
        out.append({"dosare": sorted(m["dosar"] for m in membri), "firme": sorted(m["denumire"] for m in membri),
                    "expunere": sum(m["suma"] for m in membri),
                    "motive": sorted(set().union(*(motive[m["dosar"]] for m in membri)))})
    return sorted(out, key=lambda g: (-len(g["dosare"]), -g["expunere"]))


def scaneaza(ids: list[str] | None = None, mode: str = "offline", workers: int = 4, date: str = "curate") -> dict:
    t0 = time.time()
    folder = DATA / ("dosare" if date == "curate" else "dosare_murdare")
    sup = DATA / ("suplimentare" if date == "curate" else "suplimentare_murdare")
    ids = ids or sorted(p.name for p in folder.iterdir() if p.is_dir())

    def run(k):
        x = raspuns_client(str(folder / k), str(sup / k), mode=mode)  # cu documentele trimise de client, daca s-au cerut
        r = x["dupa"]
        probleme = [f for f in r["constatari"] if f["severitate"] in ("CRITIC", "LIPSA", "AVERTIZARE")]
        return {"dosar": k, "verdict": r["verdict"], "scor_risc": r["scor_risc"], "tip": r["tip_entitate"],
                "problema_principala": probleme[0]["mesaj"] if probleme else None,
                "verificari_cu_probleme": sorted({f["verificare"] for f in probleme}),
                "documente_cerute": [c["document"] for c in x["inainte"]["documente_cerute"]],
                "client_a_raspuns": x["client_a_raspuns"]}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        rez = list(ex.map(run, ids))
    con = sqlite3.connect(DB_PATH)
    info = {r[0]: r[1:] for r in con.execute("SELECT c.dosar, f.denumire, c.suma FROM cereri_credit c JOIN firme f ON f.cui = c.cui")}
    con.close()
    for r in rez:
        r["denumire"], r["suma"] = info.get(r["dosar"], (None, 0))

    pe_verdict = {}
    for v in VERDICTE:
        sel = [r for r in rez if r["verdict"] == v]
        pe_verdict[v] = {"dosare": len(sel), "expunere": sum(r["suma"] for r in sel)}
    grupuri = _grupuri()
    verdict_dosar = {r["dosar"]: r["verdict"] for r in rez}
    for g in grupuri:
        g["suspecte"] = sum(verdict_dosar.get(d) == "SUSPECT_FRAUDA" for d in g["dosare"])

    anterior = json.loads(ULTIMA.read_text(encoding="utf-8")) if ULTIMA.is_file() else None
    schimbari = []
    if anterior:
        vechi = {r["dosar"]: r["verdict"] for r in anterior["dosare"]}
        for r in rez:
            if r["dosar"] in vechi and vechi[r["dosar"]] != r["verdict"]:
                schimbari.append({"dosar": r["dosar"], "denumire": r["denumire"], "inainte": vechi[r["dosar"]], "acum": r["verdict"]})
            elif r["dosar"] not in vechi:
                schimbari.append({"dosar": r["dosar"], "denumire": r["denumire"], "inainte": None, "acum": r["verdict"]})
    prioritati = sorted(rez, key=lambda r: (SEV_ORDER.get({"SUSPECT_FRAUDA": "CRITIC", "INCOMPLET": "LIPSA",
                                                           "REVIZUIRE_UMANA": "AVERTIZARE"}.get(r["verdict"], "OK")), -r["scor_risc"], -r["suma"]))
    out = {"data_scanarii": datetime.now().isoformat(timespec="seconds"), "mod": mode, "date": date, "dosare_scanate": len(rez),
           "expunere_totala": sum(r["suma"] for r in rez), "pe_verdict": pe_verdict,
           "expunere_la_risc": pe_verdict["SUSPECT_FRAUDA"]["expunere"] + pe_verdict["REVIZUIRE_UMANA"]["expunere"],
           "prioritati": [r for r in prioritati if r["verdict"] != "CURAT"][:25],
           "grupuri": grupuri, "grupuri_cu_dosare_suspecte": sum(1 for g in grupuri if g["suspecte"]),
           "schimbari_fata_de_scanarea_anterioara": schimbari if anterior else None,
           "scanare_anterioara": anterior["data_scanarii"] if anterior else None,
           "durata_sec": round(time.time() - t0, 1), "dosare": rez}
    if ULTIMA.is_file():
        ULTIMA.replace(ULTIMA.with_name("portofoliu_scanarea_anterioara.json"))
    ULTIMA.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def ultima() -> dict | None:
    return json.loads(ULTIMA.read_text(encoding="utf-8")) if ULTIMA.is_file() else None
