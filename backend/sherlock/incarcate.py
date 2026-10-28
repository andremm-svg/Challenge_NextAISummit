"""Dosarele incarcate din aplicatie: baza de date pornita goala, cu documentele si rezultatul fiecarei analize.

  data/incarcate/incarcate.db      dosare + documente (si cele inlocuite, pentru audit)
  data/incarcate/N001/             documentele active ale dosarului
  data/incarcate/N001/_inlocuite/  documentele ilizibile inlocuite la reincarcare

Fiecare incarcare (dosar nou sau documente noi) reia investigatia multi-agent pe documentele active.
"""
import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .multi_agent import investigate_multi_agent

ROOT = Path(__file__).resolve().parents[1] / "data" / "incarcate"
EXTENSII = (".pdf", ".csv", ".txt")

SCHEMA = """
CREATE TABLE IF NOT EXISTS dosare(id TEXT PRIMARY KEY, creat TEXT, actualizat TEXT, denumire TEXT, cui TEXT, suma REAL,
                                  verdict TEXT, scor_risc INTEGER, runde INTEGER DEFAULT 0, rezultat TEXT);
CREATE TABLE IF NOT EXISTS documente(dosar TEXT, fisier TEXT, tip TEXT, octeti INTEGER, incarcat TEXT, stare TEXT,
                                     PRIMARY KEY (dosar, fisier, incarcat));
"""


@contextmanager
def _db(root: Path = None):
    root = root or ROOT
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "incarcate.db")  # inchisa explicit: pe Windows un fisier deschis nu se poate sterge
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _acum() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _folder(dosar: str, root: Path = None) -> Path:
    root = (root or ROOT).resolve()
    f = (root / dosar).resolve()
    if root not in f.parents:
        raise FileNotFoundError(dosar)
    return f


def _nume_sigur(nume: str) -> str:
    nume = Path(nume or "").name
    if not nume.lower().endswith(EXTENSII):
        raise ValueError(f"{nume or 'fișierul'} nu este PDF sau CSV")
    return nume


def creeaza(fisiere: list[tuple[str, bytes]], mode: str = "auto", llm=None, root: Path = None) -> dict:
    """Dosar nou din fisierele incarcate. Returneaza raportul, cu id-ul dosarului."""
    for n, _ in fisiere:  # inainte de a crea dosarul: un upload refuzat nu lasa dosare goale
        _nume_sigur(n)
    with _db(root) as con:
        n = con.execute("SELECT COUNT(*) FROM dosare").fetchone()[0] + 1
        while con.execute("SELECT 1 FROM dosare WHERE id=?", (f"N{n:03d}",)).fetchone():
            n += 1
        dosar = f"N{n:03d}"
        con.execute("INSERT INTO dosare(id, creat, actualizat) VALUES (?,?,?)", (dosar, _acum(), _acum()))
    return adauga_documente(dosar, fisiere, mode=mode, llm=llm, root=root)


def adauga_documente(dosar: str, fisiere: list[tuple[str, bytes]], inlocuieste: list[str] | None = None,
                     mode: str = "auto", llm=None, root: Path = None) -> dict:
    """Adauga documente (sau inlocuieste documente ilizibile) si reia investigatia."""
    folder = _folder(dosar, root)
    with _db(root) as con:
        if not con.execute("SELECT 1 FROM dosare WHERE id=?", (dosar,)).fetchone():
            raise FileNotFoundError(f"Dosarul {dosar} nu exista")
    nume = [_nume_sigur(n) for n, _ in fisiere]
    folder.mkdir(parents=True, exist_ok=True)
    t = _acum()
    with _db(root) as con:
        for vechi in inlocuieste or []:
            vechi = Path(vechi).name
            if (folder / vechi).is_file():
                (folder / "_inlocuite").mkdir(exist_ok=True)
                shutil.move(folder / vechi, folder / "_inlocuite" / f"{t.replace(':', '')}_{vechi}")
                con.execute("UPDATE documente SET stare='inlocuit' WHERE dosar=? AND fisier=? AND stare='activ'", (dosar, vechi))
        for n, (_, data) in zip(nume, fisiere):
            (folder / n).write_bytes(data)
            con.execute("UPDATE documente SET stare='inlocuit' WHERE dosar=? AND fisier=? AND stare='activ'", (dosar, n))
            con.execute("INSERT OR REPLACE INTO documente VALUES (?,?,?,?,?,?)", (dosar, n, None, len(data), t, "activ"))
    return analizeaza(dosar, mode=mode, llm=llm, root=root)


def analizeaza(dosar: str, mode: str = "auto", llm=None, root: Path = None) -> dict:
    folder = _folder(dosar, root)
    paths = sorted(str(f) for f in folder.iterdir() if f.is_file() and f.suffix.lower() in EXTENSII)
    r = investigate_multi_agent(dosar, paths, mode=mode, llm=llm)
    tipuri = {v: k for k, v in r["documente"].items()}
    sol = r.get("solicitant") or {}
    with _db(root) as con:
        for fisier in (Path(p).name for p in paths):
            con.execute("UPDATE documente SET tip=? WHERE dosar=? AND fisier=? AND stare='activ'", (tipuri.get(fisier, "neidentificat"), dosar, fisier))
        con.execute("""UPDATE dosare SET actualizat=?, denumire=?, cui=?, suma=?, verdict=?, scor_risc=?, runde=runde+1, rezultat=?
                       WHERE id=?""", (_acum(), sol.get("denumire"), sol.get("cui"), sol.get("suma"), r["verdict"], r["scor_risc"],
                                      json.dumps(r, ensure_ascii=False), dosar))
    return r


def lista(root: Path = None) -> list[dict]:
    with _db(root) as con:
        rows = con.execute("SELECT id, creat, actualizat, denumire, cui, suma, verdict, scor_risc, runde, rezultat FROM dosare ORDER BY id").fetchall()
    out = []
    for r in rows:
        rez = json.loads(r["rezultat"]) if r["rezultat"] else {}
        out.append({"dosar": r["id"], "denumire": r["denumire"] or r["id"], "cui": r["cui"], "suma": r["suma"], "creat": r["creat"],
                    "actualizat": r["actualizat"], "verdict": r["verdict"], "scor_risc": r["scor_risc"], "runde": r["runde"],
                    "tip": rez.get("tip_entitate"), "agenti_fara_ok": [s["nume"] for s in rez.get("sub_agenti", []) if s.get("status") == "ALARMA"]})
    return out


def detalii(dosar: str, root: Path = None) -> dict:
    with _db(root) as con:
        r = con.execute("SELECT rezultat FROM dosare WHERE id=?", (dosar,)).fetchone()
        docs = [dict(d) for d in con.execute("SELECT fisier, tip, octeti, incarcat, stare FROM documente WHERE dosar=? ORDER BY incarcat, fisier", (dosar,))]
    if not r:
        raise FileNotFoundError(f"Dosarul {dosar} nu exista")
    return {"rezultat": json.loads(r["rezultat"]) if r["rezultat"] else None, "documente": docs}


def document(dosar: str, fisier: str, root: Path = None) -> Path:
    folder = _folder(dosar, root)
    p = (folder / Path(fisier).name).resolve()
    if folder not in p.parents or not p.is_file():
        raise FileNotFoundError(fisier)
    return p


def goleste(root: Path = None):
    """Sterge toate dosarele incarcate (baza porneste din nou goala). Pentru repetitia demo-ului."""
    root = root or ROOT
    if root.exists():
        shutil.rmtree(root)
