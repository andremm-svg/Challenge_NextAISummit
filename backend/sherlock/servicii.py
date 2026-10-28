"""Operatii comune pentru API (interfata web) si serverul MCP (chat cu Sherlock)."""
import json
import re
import sqlite3

from .firme import citire
from .firme.tools import DATA, DB_PATH
from .multi_agent import investigate_multi_agent_folder

FOLDERE = {"curate": "dosare", "murdare": "dosare_murdare"}


def etichete() -> dict:
    return json.loads((DATA / "etichete.json").read_text(encoding="utf-8"))


def folder_dosar(dosar: str, date: str = "curate"):
    f = (DATA / FOLDERE.get(date, "dosare") / dosar).resolve()
    if (DATA / FOLDERE.get(date, "dosare")).resolve() not in f.parents or not f.is_dir():
        raise FileNotFoundError(f"Dosarul {dosar} nu exista")
    return f


def lista_dosare(set: str = "toate", cauta: str = "", arata_eticheta: bool = False) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    cereri = {r[0]: r[1:] for r in con.execute("SELECT c.dosar, c.data_cerere, f.cui FROM cereri_credit c JOIN firme f ON f.cui = c.cui")}
    con.close()
    q = citire.norm(cauta).strip()
    out = []
    for dosar, v in sorted(etichete().items()):
        if set != "toate" and v["set"] != set:
            continue
        data, cui = cereri.get(dosar, (None, None))
        if q and q not in citire.norm(f"{dosar} {v['denumire']} {cui}"):
            continue
        item = {"dosar": dosar, "denumire": v["denumire"], "tip": v["tip"], "suma": v["suma"], "data_cerere": data, "cui": cui,
                "set": v["set"], "are_contract": (DATA / "dosare" / dosar / "contract.pdf").is_file()}
        if arata_eticheta:
            item |= {"eticheta": v["eticheta"], "tipar": v["tipar"]}
        out.append(item)
    return out


def analizeaza(dosar: str, mode: str = "offline", date: str = "curate") -> dict:
    return investigate_multi_agent_folder(str(folder_dosar(dosar, date)), mode=mode)


def rezumat(r: dict, max_constatari: int = 8) -> dict:
    """Raportul, scurtat pentru chat: verdict, de ce, ce urmeaza."""
    probleme = [f for f in r["constatari"] if f["severitate"] in ("CRITIC", "LIPSA", "AVERTIZARE")]
    return {"dosar": r["dosar"], "tip": r["tip_entitate"], "verdict": r["verdict"], "eticheta": r["eticheta"],
            "scor_risc": r["scor_risc"], "explicatie": r["explicatie"],
            "constatari": [{"verificare": f["verificare"], "severitate": f["severitate"], "mesaj": f["mesaj"], "dovezi": f["dovezi"][:4]}
                           for f in probleme[:max_constatari]],
            "verificari_ok": sorted({f["verificare"] for f in r["constatari"] if f["severitate"] == "OK"}),
            "contraverificare": [{"verificare": d["verificare"], "acceptat": d["acceptat"], "decizie": d["decizia_coordonatorului"]}
                                 for d in r["contraverificare"]],
            "documente_cerute": r["documente_cerute"], "urmatorii_pasi": r["urmatorii_pasi"][:6],
            "masuratori": r.get("masuratori", {}), "documente_ilizibile": r.get("documente_ilizibile", []),
            "sub_agenti": [{"nume": s["nume"], "status": s.get("status"), "alarme": s["alarme"]} for s in r["sub_agenti"]]}


def cauta_firma(text: str) -> list[dict]:
    """Cauta in registrul sintetic dupa CUI sau denumire: date de registru, bilanturi ANAF, cereri de credit."""
    q = citire.norm(text).strip()
    if re.fullmatch(r"RO\s?\d+", q):
        q = q[2:].strip()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM firme WHERE cui = ? OR denumire LIKE ? LIMIT 10", (q, f"%{q}%")).fetchall()
    out = []
    for f in rows:
        d = dict(f)
        d["administratori"] = [dict(a) for a in con.execute("SELECT nume, de_la FROM administratori WHERE cui=?", (f["cui"],))]
        d["bilanturi_anaf"] = [dict(b) for b in con.execute("SELECT * FROM bilanturi_anaf WHERE cui=? ORDER BY an", (f["cui"],))]
        d["cereri_credit"] = [dict(c) for c in con.execute("SELECT dosar, data_cerere, suma FROM cereri_credit WHERE cui=?", (f["cui"],))]
        out.append(d)
    con.close()
    return out


def retea(dosar: str) -> dict:
    from .firme.tools import load_case, verifica_retea

    folder = folder_dosar(dosar)
    case = load_case(dosar, sorted(str(f) for f in folder.iterdir()))
    verifica_retea(case)
    et = etichete()
    nodes = [{"id": dosar, "denumire": et.get(dosar, {}).get("denumire"), "suma": et.get(dosar, {}).get("suma"), "central": True}]
    edges = []
    for l in case.state.get("retea", []):
        nodes.append({"id": l["dosar"], "denumire": l["denumire"], "suma": l["suma"], "central": False})
        edges.append({"de_la": dosar, "la": l["dosar"], "motive": l["motive"]})
    return {"noduri": nodes, "legaturi": edges}
