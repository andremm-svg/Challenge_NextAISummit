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
async def analizeaza_upload(files: list[UploadFile] = File(...), mode: str = Form("auto")):
    """Incarca 1-6 PDF-uri ale unui dosar si ruleaza investigatia."""
    if not 1 <= len(files) <= 6:
        raise HTTPException(400, "Trimite intre 1 si 6 fisiere PDF")
    tmp = Path(tempfile.mkdtemp(prefix="dosar_"))
    try:
        paths = []
        for f in files:
            if not (f.filename or "").lower().endswith(".pdf"):
                raise HTTPException(400, f"{f.filename} nu este PDF")
            dest = tmp / Path(f.filename).name
            dest.write_bytes(await f.read())
            paths.append(str(dest))
        return investigate(f"upload_{uuid.uuid4().hex[:6]}", paths, mode=mode)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
