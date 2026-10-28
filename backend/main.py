import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from sherlock_api import router as sherlock_router

app = FastAPI(title="BankFlow AI")

# Permite interfetei (Lovable) sa apeleze API-ul
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(sherlock_router)


@app.get("/")
def home():
    return {"message": "Backend-ul functioneaza!"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Incarca un fisier PDF."
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Fisierul este gol."
        )

    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise HTTPException(
                    status_code=400,
                    detail="PDF-ul este protejat cu parola."
                )

            page_count = len(document)
            text = "\n".join(
                page.get_text() for page in document
            ).strip()

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Fisierul nu poate fi citit ca PDF."
        )

    if not text:
        raise HTTPException(
            status_code=422,
            detail="PDF-ul nu contine text extractibil. Poate necesita OCR."
        )

    return {
        "filename": file.filename,
        "page_count": page_count,
        "text": text,
        "message": "Text extras cu succes!"
    }