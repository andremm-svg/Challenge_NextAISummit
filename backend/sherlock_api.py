"""Endpoint-urile Sherlock. Se adauga in main.py cu:

    from sherlock_api import router as sherlock_router
    app.include_router(sherlock_router)
"""
import json
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sherlock.agent import investigate, investigate_folder

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / "data" / "dosare"
DECIZII = ROOT / "data" / "decizii_analist.jsonl"

router = APIRouter(prefix="/sherlock", tags=["Sherlock"])


@router.get("/dosare-demo")
def lista_dosare_demo():
    """Dosarele sintetice disponibile pentru demo."""
    return [{"dosar": d.name, "documente": sorted(f.name for f in d.glob("*.pdf"))} for d in sorted(DEMO.iterdir()) if d.is_dir()]


@router.post("/demo/{dosar}")
def analizeaza_demo(dosar: str, mode: str = "auto"):
    """Ruleaza agentul pe un dosar demo. mode: auto | llm | offline"""
    folder = DEMO / dosar
    if not folder.is_dir():
        raise HTTPException(404, f"Dosarul {dosar} nu exista")
    try:
        return investigate_folder(str(folder), mode=mode)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/demo/{dosar}/document/{fisier}")
def descarca_document_demo(dosar: str, fisier: str):
    """Returneaza PDF-ul, ca interfata sa il poata afisa."""
    path = (DEMO / dosar / fisier).resolve()
    if DEMO.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "Document inexistent")
    return FileResponse(path, media_type="application/pdf")


@router.post("/analizeaza")
async def analizeaza_upload(files: list[UploadFile] = File(...), mode: str = Form("auto"), domeniu: str = Form("auto")):
    """Incarca 1-6 fisiere (PDF, plus extras_cont.csv pentru firme) si ruleaza investigatia.
    domeniu: auto | persoane | firme"""
    if not 1 <= len(files) <= 6:
        raise HTTPException(400, "Trimite intre 1 si 6 fisiere")
    tmp = Path(tempfile.mkdtemp(prefix="dosar_")) / f"upload_{uuid.uuid4().hex[:6]}"
    tmp.mkdir()
    try:
        for f in files:
            if not (f.filename or "").lower().endswith((".pdf", ".csv")):
                raise HTTPException(400, f"{f.filename} nu este PDF sau CSV")
            (tmp / Path(f.filename).name).write_bytes(await f.read())
        return investigate_folder(str(tmp), mode=mode, domeniu=None if domeniu == "auto" else domeniu)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


# ====================================================================== FIRME SI PFA
FIRME = ROOT / "data" / "firme"


def _etichete() -> dict:
    return json.loads((FIRME / "etichete.json").read_text(encoding="utf-8"))


@router.get("/firme/dosare")
def lista_dosare_firme(set: str = "toate", arata_eticheta: bool = False):
    """Dosarele de credit ale firmelor/PFA. Eticheta reala e ascunsa implicit (o vede doar evaluarea)."""
    import sqlite3

    con = sqlite3.connect(FIRME / "sherlock.db")
    cereri = {r[0]: r[1:] for r in con.execute("SELECT dosar, data_cerere, suma FROM cereri_credit")}
    con.close()
    out = []
    for dosar, v in sorted(_etichete().items()):
        if set != "toate" and v["set"] != set:
            continue
        item = {"dosar": dosar, "denumire": v["denumire"], "tip": v["tip"], "suma": v["suma"],
                "data_cerere": cereri.get(dosar, (None,))[0], "set": v["set"]}
        if arata_eticheta:
            item |= {"eticheta": v["eticheta"], "tipar": v["tipar"]}
        out.append(item)
    return out


@router.post("/firme/analizeaza/{dosar}")
def analizeaza_dosar_firma(dosar: str, mode: str = "auto"):
    """Ruleaza agentul pe un dosar de firma/PFA. mode: auto | llm | offline"""
    folder = FIRME / "dosare" / dosar
    if not folder.is_dir():
        raise HTTPException(404, f"Dosarul {dosar} nu exista")
    try:
        return investigate_folder(str(folder), mode=mode, domeniu="firme")
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/firme/dosare/{dosar}/document/{fisier}")
def document_firma(dosar: str, fisier: str):
    path = (FIRME / "dosare" / dosar / fisier).resolve()
    if (FIRME / "dosare").resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "Document inexistent")
    return FileResponse(path, media_type="text/csv" if path.suffix == ".csv" else "application/pdf")


@router.get("/firme/retea/{dosar}")
def retea_dosar(dosar: str):
    """Graful de legaturi (noduri + muchii) pentru vizualizarea retelei in interfata."""
    from sherlock.firme.tools import load_case, verifica_retea

    folder = FIRME / "dosare" / dosar
    if not folder.is_dir():
        raise HTTPException(404, f"Dosarul {dosar} nu exista")
    case = load_case(dosar, sorted(str(f) for f in folder.iterdir()))
    verifica_retea(case)
    et = _etichete()
    nodes = [{"id": dosar, "denumire": et.get(dosar, {}).get("denumire"), "suma": et.get(dosar, {}).get("suma"), "central": True}]
    edges = []
    for l in case.state.get("retea", []):
        nodes.append({"id": l["dosar"], "denumire": l["denumire"], "suma": l["suma"], "central": False})
        edges.append({"de_la": dosar, "la": l["dosar"], "motive": l["motive"]})
    return {"noduri": nodes, "legaturi": edges}


@router.get("/firme/metrici")
def metrici(set: str = "test", mod: str = "offline", config: str = "complet"):
    """Metricile calculate de run_eval.py. config: complet (echipa + documente) | echipa | simplu"""
    path = FIRME / (f"metrici_{set}_{mod}" + ("" if config == "complet" else f"_{config}") + ".json")
    if not path.is_file():
        raise HTTPException(404, f"Rulati intai: python run_eval.py --set {set} --mode {mod} --config {config}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/firme/comparatie")
def comparatie(set: str = "test"):
    """Verificare clasica vs agent simplu vs echipa vs echipa + documente, pe aceleasi dosare."""
    path = FIRME / f"metrici_comparatie_{set}.json"
    if not path.is_file():
        raise HTTPException(404, f"Rulati intai: python run_eval.py --comparatie --set {set}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/firme/echipa/{dosar}")
def analizeaza_cu_echipa(dosar: str, mode: str = "auto"):
    """Echipa de detectivi: 3 specialisti, garda, avocatul diavolului, judecatorul si cererea de documente."""
    from sherlock.echipa import investigate_echipa_folder

    folder = FIRME / "dosare" / dosar
    if not folder.is_dir():
        raise HTTPException(404, f"Dosarul {dosar} nu exista")
    try:
        return investigate_echipa_folder(str(folder), mode=mode)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/firme/echipa/{dosar}/raspuns-client")
def simuleaza_raspuns_client(dosar: str, mode: str = "auto"):
    """Simuleaza raspunsul clientului la documentele cerute si reia investigatia (inainte / dupa).
    Simulare: clientii legitimi cu incasari la alta banca trimit extrasul; fraudatorii nu au ce trimite."""
    from sherlock.echipa import raspuns_client

    folder = FIRME / "dosare" / dosar
    if not folder.is_dir():
        raise HTTPException(404, f"Dosarul {dosar} nu exista")
    try:
        return raspuns_client(str(folder), str(FIRME / "suplimentare" / dosar), mode=mode)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


class Decizie(BaseModel):
    dosar: str
    decizie: str            # "aprobat_pentru_evaluare" | "respins" | "cere_documente" | "trimis_antifrauda"
    analist: str
    comentariu: str = ""
    verdict_sherlock: str = ""


@router.post("/decizie")
def inregistreaza_decizie(d: Decizie):
    """Omul ia decizia finala. O salvam in jurnalul de audit (inclusiv cand nu e de acord cu Sherlock)."""
    entry = d.model_dump() | {"timestamp": datetime.now().isoformat(timespec="seconds"),
                              "override": bool(d.verdict_sherlock) and _contrazice(d.verdict_sherlock, d.decizie)}
    with DECIZII.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"salvat": True, **entry}


@router.get("/decizii")
def lista_decizii():
    if not DECIZII.exists():
        return []
    return [json.loads(line) for line in DECIZII.read_text(encoding="utf-8").splitlines() if line.strip()]


def _contrazice(verdict: str, decizie: str) -> bool:
    asteptat = {"CURAT": "aprobat_pentru_evaluare", "INCOMPLET": "cere_documente",
                "SUSPECT_FRAUDA": "trimis_antifrauda", "REVIZUIRE_UMANA": None}.get(verdict)
    return asteptat is not None and asteptat != decizie
