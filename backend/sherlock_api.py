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

from sherlock.agent import investigate_folder

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
    scan = FIRME / "portofoliu_ultima_scanare.json"  # statusul din ultima scanare de portofoliu (aceleasi reguli)
    status = {d["dosar"]: d for d in json.loads(scan.read_text(encoding="utf-8"))["dosare"]} if scan.is_file() else {}
    out = []
    for dosar, v in sorted(_etichete().items()):
        if set != "toate" and v["set"] != set:
            continue
        st = status.get(dosar, {})
        item = {"dosar": dosar, "denumire": v["denumire"], "tip": v["tip"], "suma": v["suma"],
                "data_cerere": cereri.get(dosar, (None,))[0], "set": v["set"], "verdict": st.get("verdict"), "scor_risc": st.get("scor_risc")}
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
    """Metricile calculate de run_eval.py. config: complet (multi-agent + documente) | multi_agent | simplu"""
    path = FIRME / (f"metrici_{set}_{mod}" + ("" if config == "complet" else f"_{config}") + ".json")
    if not path.is_file():
        raise HTTPException(404, f"Rulati intai: python run_eval.py --set {set} --mode {mod} --config {config}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/firme/comparatie")
def comparatie(set: str = "test", varianta: str = ""):
    """Verificare clasica vs agent simplu vs multi-agent vs multi-agent + solicitare documente, pe aceleasi dosare.
    varianta: "" (toate dosarele curate) | murdare | extensie (doar dosarele noi D199+)"""
    if varianta not in ("", "murdare", "extensie"):
        raise HTTPException(400, "varianta: '' | murdare | extensie")
    path = FIRME / f"metrici_comparatie_{set}{'_' + varianta if varianta else ''}.json"
    if not path.is_file():
        flag = {"": "", "murdare": " --date murdare", "extensie": " --doar-extensie"}[varianta]
        raise HTTPException(404, f"Rulati intai: python run_eval.py --comparatie --set {set}{flag}")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/firme/multi-agent/{dosar}")
def analizeaza_multi_agent(dosar: str, mode: str = "auto", date: str = "curate"):
    """Sherlock multi-agent: agentii de documente, firma, financiar si contracte, controlul automat,
    contra-verificarea, decizia coordonatorului si solicitarea de documente. date: curate | murdare"""
    from sherlock.multi_agent import investigate_multi_agent_folder

    folder = FIRME / ("dosare_murdare" if date == "murdare" else "dosare") / dosar
    if not folder.is_dir():
        raise HTTPException(404, f"Dosarul {dosar} nu exista")
    try:
        return investigate_multi_agent_folder(str(folder), mode=mode)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/firme/multi-agent/{dosar}/raspuns-client")
def simuleaza_raspuns_client(dosar: str, mode: str = "auto", date: str = "curate"):
    """Simuleaza raspunsul clientului la documentele cerute si reia investigatia (inainte / dupa).
    Simulare: clientii legitimi cu incasari la alta banca trimit extrasul; fraudatorii nu au ce trimite."""
    from sherlock.multi_agent import raspuns_client

    murdar = date == "murdare"
    folder = FIRME / ("dosare_murdare" if murdar else "dosare") / dosar
    if not folder.is_dir():
        raise HTTPException(404, f"Dosarul {dosar} nu exista")
    try:
        return raspuns_client(str(folder), str(FIRME / ("suplimentare_murdare" if murdar else "suplimentare") / dosar), mode=mode)
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


# ====================================================================== APLICATIA: dosare, feedback, portofoliu
@router.get("/firme/dosare/{dosar}/documente")
def documente_dosar(dosar: str, date: str = "curate"):
    """Fisierele unui dosar (pentru previzualizare in aplicatie)."""
    from sherlock import servicii

    try:
        folder = servicii.folder_dosar(dosar, date)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return [{"fisier": f.name, "tip": f.suffix.lstrip(".").lower()} for f in sorted(folder.iterdir())]


@router.get("/firme/murdare/{dosar}/document/{fisier}")
def document_murdar(dosar: str, fisier: str):
    root = (FIRME / "dosare_murdare").resolve()
    path = (root / dosar / fisier).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Document inexistent")
    return FileResponse(path, media_type="text/csv" if path.suffix == ".csv" else "application/pdf")


@router.get("/llm/status")
def llm_status():
    """Raspunde Claude acum? Interfata arata starea in antet (de ex. token AWS expirat)."""
    from sherlock.llm import get_llm

    llm = get_llm()
    if llm is None:
        return {"ok": False, "furnizor": None, "model": None, "motiv": "LLM-ul nu e configurat în .env"}
    try:
        llm.complete("Raspunde doar: ok", max_tokens=20)
        return {"ok": True, "furnizor": llm.provider, "model": llm.model, "motiv": ""}
    except Exception as e:  # noqa: BLE001
        motiv = "tokenul AWS a expirat: actualizați cheile din .env" if "ExpiredToken" in str(e) else f"{type(e).__name__}: {str(e)[:160]}"
        return {"ok": False, "furnizor": llm.provider, "model": llm.model, "motiv": motiv}


# ------------------------------------------------------------------ dosarele incarcate din aplicatie (baza pornita goala)
async def _citeste(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not 1 <= len(files) <= 10:
        raise HTTPException(400, "Trimite între 1 și 10 fișiere")
    return [(f.filename or "", await f.read()) for f in files]


def _incarcate(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e


@router.get("/firme/incarcate")
def lista_incarcate():
    """Dosarele incarcate din aplicatie, cu statusul ultimei analize."""
    from sherlock import incarcate

    return incarcate.lista()


@router.post("/firme/incarcate")
async def incarca_dosar(files: list[UploadFile] = File(...), mode: str = Form("auto")):
    """Dosar nou: salveaza documentele in baza de date si ruleaza investigatia multi-agent."""
    from sherlock import incarcate

    return _incarcate(incarcate.creeaza, await _citeste(files), mode=mode)


@router.post("/firme/incarcate/{dosar}/documente")
async def adauga_documente(dosar: str, files: list[UploadFile] = File(...), inlocuieste: list[str] = Form([]), mode: str = Form("auto")):
    """Documente noi pentru un dosar incarcat (de ex. copia lizibila a unui document scanat). Investigatia se reia."""
    from sherlock import incarcate

    return _incarcate(incarcate.adauga_documente, dosar, await _citeste(files), inlocuieste=inlocuieste, mode=mode)


@router.get("/firme/incarcate/{dosar}")
def detalii_incarcat(dosar: str):
    from sherlock import incarcate

    return _incarcate(incarcate.detalii, dosar)


@router.get("/firme/incarcate/{dosar}/document/{fisier}")
def document_incarcat(dosar: str, fisier: str):
    from sherlock import incarcate

    path = _incarcate(incarcate.document, dosar, fisier)
    return FileResponse(path, media_type="text/csv" if path.suffix == ".csv" else "application/pdf")


@router.post("/firme/multi-agent-upload")
async def multi_agent_upload(files: list[UploadFile] = File(...), mode: str = Form("auto")):
    """Investigatia multi-agent pe un dosar incarcat (PDF-uri + extras CSV, in orice format)."""
    from sherlock.multi_agent import investigate_multi_agent

    if not 1 <= len(files) <= 10:
        raise HTTPException(400, "Trimite intre 1 si 10 fisiere")
    tmp = Path(tempfile.mkdtemp(prefix="dosar_"))
    try:
        paths = []
        for f in files:
            if not (f.filename or "").lower().endswith((".pdf", ".csv", ".txt")):
                raise HTTPException(400, f"{f.filename} nu este PDF sau CSV")
            p = tmp / Path(f.filename).name
            p.write_bytes(await f.read())
            paths.append(str(p))
        return investigate_multi_agent(f"upload_{uuid.uuid4().hex[:6]}", sorted(paths), mode=mode)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.get("/firme/firma")
def cauta_firma(q: str):
    """Cauta o firma in registrul sintetic dupa CUI sau denumire."""
    from sherlock import servicii

    return servicii.cauta_firma(q)


class Feedback(BaseModel):
    dosar: str
    analist: str
    decizie: str                  # aprobat_pentru_evaluare | respins | cere_documente | trimis_antifrauda
    verdict_sherlock: str = ""
    eticheta: str | None = None   # FRAUDA | LEGITIM | None (inca nu se stie)
    constatari: list[dict] = []   # [{"verificare", "severitate", "corecta": bool}]
    masuratori: dict = {}
    comentariu: str = ""


@router.post("/feedback")
def trimite_feedback(f: Feedback):
    """Decizia analistului + ce constatari au fost corecte. Intra in bucla de recalibrare (si in jurnalul deciziilor)."""
    from sherlock import feedback

    if not f.analist.strip():
        raise HTTPException(400, "Completati numele analistului")
    try:
        entry = feedback.inregistreaza(f.dosar, f.analist, f.decizie, f.verdict_sherlock, f.eticheta, f.constatari, f.masuratori, f.comentariu)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    inregistreaza_decizie(Decizie(dosar=f.dosar, decizie=f.decizie, analist=f.analist, comentariu=f.comentariu,
                                  verdict_sherlock=f.verdict_sherlock))
    return {"salvat": True, **entry}


@router.get("/feedback")
def lista_feedback():
    from sherlock import feedback

    return feedback.toate()


@router.get("/feedback/raport")
def raport_feedback():
    """Precizia alarmelor pe verificare + propunerile de praguri (necesita aprobare umana)."""
    from sherlock import feedback

    return {"raport": feedback.raport(), "propuneri": feedback.propune_praguri()}


@router.get("/feedback/simulare")
def feedback_simulare():
    path = FIRME / "feedback_simulare.json"
    if not path.is_file():
        raise HTTPException(404, "Rulati intai: python run_feedback.py")
    return json.loads(path.read_text(encoding="utf-8"))


class Recalibrare(BaseModel):
    praguri: dict                 # {"flux_cont.critic_sub": 0.384}
    analist: str
    motiv: str = ""


@router.post("/feedback/aplica")
def aplica_recalibrare(r: Recalibrare):
    """Un analist aproba propunerile; abia atunci se scriu in config.yaml (cu jurnal)."""
    from sherlock import feedback

    try:
        return feedback.aplica(r.praguri, r.analist, r.motiv)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/firme/portofoliu")
def portofoliu_ultima():
    from sherlock import portofoliu

    r = portofoliu.ultima()
    if not r:
        raise HTTPException(404, "Nicio scanare inca: POST /sherlock/firme/portofoliu/scaneaza sau python run_portofoliu.py")
    return {k: v for k, v in r.items() if k != "dosare"}


@router.post("/firme/portofoliu/scaneaza")
def portofoliu_scaneaza(date: str = "curate", workers: int = 8):
    """Re-verifica tot portofoliul (offline, cateva zeci de secunde) si cauta retele in toate cererile."""
    from sherlock import portofoliu

    r = portofoliu.scaneaza(workers=workers, date=date)
    return {k: v for k, v in r.items() if k != "dosare"}
