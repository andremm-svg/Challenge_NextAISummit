"""Teste pentru dosarele demo, baza dosarelor incarcate si agentul de lizibilitate.
    python tests/test_demo.py"""
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sherlock import incarcate  # noqa: E402
from sherlock.multi_agent import investigate_multi_agent  # noqa: E402

DEMO = ROOT.parent / "demo_dosare"


def _fisiere(folder: str) -> list[tuple[str, bytes]]:
    return [(f.name, f.read_bytes()) for f in sorted((DEMO / folder).iterdir())]


def _run(folder: str) -> dict:
    return investigate_multi_agent(folder, sorted(str(f) for f in (DEMO / folder).iterdir()), mode="offline")


def _status(r: dict) -> dict:
    return {s["id"]: s["status"] for s in r["sub_agenti"]}


def test_dosar_eligibil():
    r = _run("1_dosar_eligibil")
    assert r["verdict"] == "CURAT" and r["scor_risc"] == 0
    assert set(_status(r).values()) == {"OK"}
    assert r["solicitant"]["denumire"] == "LUMINA TEHNIC INSTAL SRL"


def test_dosar_neeligibil_problemele_prestabilite():
    r = _run("2_dosar_neeligibil")
    assert r["verdict"] == "SUSPECT_FRAUDA" and r["scor_risc"] == 100
    assert _status(r) == {"agent_documente": "OK", "agent_firma": "ALARMA", "agent_financiar": "ALARMA", "agent_contracte": "ALARMA"}
    probleme = {p["verificare"] for s in r["sub_agenti"] for p in s["probleme"]}
    assert probleme == {"istoric_firma", "bilant_vs_anaf", "flux_cont", "salarii", "contracte"}
    assert r["scor_detaliat"]["numar"]["CRITIC"] == 5 and r["scor_detaliat"]["total_brut"] == 175


def test_dosare_noi_alt_format():
    a = _run("test_nou/A_eligibil")
    assert a["verdict"] == "CURAT" and set(_status(a).values()) == {"OK"}
    assert [c["verificare"] for c in a["contraverificare"] if c["acceptat"]] == ["istoric_firma"]  # avertizarea e lamurita
    b = _run("test_nou/B_neeligibil")
    assert b["verdict"] == "SUSPECT_FRAUDA"
    assert _status(b) == {"agent_documente": "ALARMA", "agent_firma": "OK", "agent_financiar": "ALARMA", "agent_contracte": "ALARMA"}
    assert {p["verificare"] for s in b["sub_agenti"] for p in s["probleme"]} == {"injectie", "flux_cont", "salarii", "contracte"}
    assert not any(f["verificare"] == "bilant_vs_anaf" and f["severitate"] != "OK" for f in b["constatari"])  # bilantul = ANAF
    assert b["documente_izolate"] == ["contract"]


def test_document_ilizibil_cere_reincarcare():
    r = _run("3_document_ilizibil")
    assert [d["fisier"] for d in r["documente_ilizibile"]] == ["situatii_financiare_scanat.pdf"]
    assert _status(r)["agent_financiar"] == "ASTEAPTA_DOCUMENT"
    assert r["verdict"] != "CURAT" and r["astept_documente"]


def test_baza_incarcate_porneste_goala_si_reincarcarea():
    root = Path(tempfile.mkdtemp())
    try:
        assert incarcate.lista(root) == []
        r = incarcate.creeaza(_fisiere("3_document_ilizibil"), mode="offline", root=root)
        assert r["dosar"] == "N001" and r["documente_ilizibile"]
        # aceeasi copie ilizibila: se cere din nou
        r = incarcate.adauga_documente("N001", [("situatii_financiare_scanat.pdf", (DEMO / "3_document_ilizibil" / "situatii_financiare_scanat.pdf").read_bytes())],
                                       mode="offline", root=root)
        assert r["documente_ilizibile"]
        # copia lizibila inlocuieste scanarea: dosarul devine eligibil
        r = incarcate.adauga_documente("N001", [("situatii_financiare.pdf", (DEMO / "1_dosar_eligibil" / "situatii_financiare.pdf").read_bytes())],
                                       inlocuieste=["situatii_financiare_scanat.pdf"], mode="offline", root=root)
        assert r["verdict"] == "CURAT" and not r["documente_ilizibile"]
        d = incarcate.detalii("N001", root)
        stari = {(x["fisier"], x["stare"]) for x in d["documente"]}
        assert ("situatii_financiare_scanat.pdf", "inlocuit") in stari and ("situatii_financiare.pdf", "activ") in stari
        assert d["rezultat"]["verdict"] == "CURAT"
        incarcate.creeaza(_fisiere("2_dosar_neeligibil"), mode="offline", root=root)
        lst = {x["dosar"]: x for x in incarcate.lista(root)}
        assert lst["N001"]["verdict"] == "CURAT" and lst["N001"]["runde"] == 3
        assert lst["N002"]["verdict"] == "SUSPECT_FRAUDA" and lst["N002"]["denumire"] == "VELTRA COM DISTRIBUTIE SRL"
        assert set(lst["N002"]["agenti_fara_ok"]) == {"Agentul de firmă", "Agentul financiar", "Agentul de contracte"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fisiere_nepermise():
    root = Path(tempfile.mkdtemp())
    try:
        try:
            incarcate.creeaza([("virus.exe", b"x")], mode="offline", root=root)
            raise AssertionError("trebuia refuzat")
        except ValueError:
            pass
        try:
            incarcate.document("N001", "../../sherlock.db", root)
            raise AssertionError("trebuia refuzat")
        except FileNotFoundError:
            pass
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
