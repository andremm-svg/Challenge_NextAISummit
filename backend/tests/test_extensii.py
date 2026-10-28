"""Teste pentru extensii: documente murdare, contracte, exemple negative grele, feedback, portofoliu, MCP.
    python tests/test_extensii.py"""
import asyncio
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sherlock import feedback  # noqa: E402
from sherlock.firme import citire  # noqa: E402
from sherlock.firme import tools as T  # noqa: E402
from sherlock.multi_agent import investigate_multi_agent_folder, raspuns_client  # noqa: E402
from sherlock.portofoliu import _grupuri  # noqa: E402

DATA = T.DATA
LABELS = json.loads((DATA / "etichete.json").read_text(encoding="utf-8"))


def _all(tipar, **kw):
    return [k for k, v in sorted(LABELS.items()) if v["tipar"] == tipar and all(v.get(a) == b for a, b in kw.items())]


def _run(k, date="dosare"):
    return investigate_multi_agent_folder(str(DATA / date / k), mode="offline")


def _sev(r, check):
    return [f["severitate"] for f in r["constatari"] if f["verificare"] == check]


# ------------------------------------------------------------------ documente murdare
def test_formate_de_suma():
    for text, val in [("1.234.567,89", 1234567.89), ("1 234 567", 1234567), ("1,234,567.00", 1234567), ("(12.345)", -12345),
                      ("-1 234,56", -1234.56), ("6.850,00", 6850), ("1234.5", 1234.5), ("2.300", 2300)]:
        assert citire.parse_amount(text) == val, text


def test_etichete_alternative_si_tabele():
    text = ("Situațiile financiare anuale la 31.12.2025\nCod unic de înregistrare\n12345678\n"
            "Cifra de afaceri netă (rd. 01)\n1 234 567\nRezultatul net al exercițiului (rd. 18)\n(45.000)\nEfectiv mediu de personal (rd. 21)\n7")
    f = citire.extract("situatii_financiare", text, T.CITIRE)
    assert f["cifra_afaceri"] == 1234567 and f["profit_net"] == -45000 and f["angajati"] == 7 and f["an"] == "2025" and f["cui"] == "12345678"


def test_extrase_de_la_alte_banci():
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "a.csv").write_text("Banca Demo SA - Extras de cont\nIBAN;RO00\n\nData tranzactiei;Detalii tranzactie;Debit;Credit\n"
                                   "05.03.2026;Încasare factură CLIENT ALFA SRL;;12.500,00\n10.03.2026;Plată salarii luna 03;8.000,00;\n",
                                   encoding="utf-8-sig")
        (tmp / "b.csv").write_text("Data operatiunii\tExplicatie\tSuma (RON)\n05/03/2026\tOP primit de la CLIENT BETA SA\t12 500,00\n", encoding="utf-8")
        a, b = citire.read_statement(str(tmp / "a.csv"), T.CITIRE["extras"]), citire.read_statement(str(tmp / "b.csv"), T.CITIRE["extras"])
        assert [r["suma"] for r in a["rows"]] == [12500.0, -8000.0] and a["rows"][0]["data"] == "2026-03-05"
        assert T._is_incasare(a["rows"][0]) and T._is_salariu(a["rows"][1]) and T._is_incasare(b["rows"][0])
    finally:
        shutil.rmtree(tmp)


def test_dosarele_murdare_dau_acelasi_verdict():
    """Pe un esantion fara scanari, varianta murdara si cea curata au acelasi verdict si aceleasi alarme."""
    ids = [k for k in sorted(LABELS)[::9]]
    for k in ids:
        murdar = _run(k, "dosare_murdare")
        if any(f["verificare"] == "calitate_documente" for f in murdar["constatari"]):
            continue
        curat = _run(k)
        assert murdar["verdict"] == curat["verdict"], k
        assert {(f["verificare"], f["severitate"]) for f in murdar["constatari"]} == {(f["verificare"], f["severitate"]) for f in curat["constatari"]}, k


def test_document_scanat_necitit_ajunge_la_analist():
    scanate = [k for k in sorted(LABELS) if "calitate_documente" in {f["verificare"] for f in _run(k, "dosare_murdare")["constatari"]
                                                                     if f["severitate"] == "AVERTIZARE"}][:3]
    assert scanate
    for k in scanate:
        assert _run(k, "dosare_murdare")["verdict"] != "CURAT", k


# ------------------------------------------------------------------ contracte
def test_contractele_fictive_sunt_prinse():
    for var in ("inexistent", "paravan", "fara_plati", "capacitate"):
        for k in _all("contract_fictiv", varianta=var)[:2]:
            r = _run(k)
            assert r["verdict"] == "SUSPECT_FRAUDA" and "CRITIC" in _sev(r, "contracte"), (var, k)


def test_verificarea_clasica_nu_vede_contractul_fictiv():
    from sherlock.agent import verdict_from

    for k in _all("contract_fictiv")[:4]:
        assert verdict_from(_run(k)["constatari"], T.CHECKS_VERIFICARE_CLASICA) != "SUSPECT_FRAUDA", k


def test_contractele_legitime_nu_dau_alarme_false():
    for tipar in ("legitim_contract_real", "legitim_contract_recent", "legitim_contract_achizitie", "legitim_contract_final"):
        for k in _all(tipar)[:3]:
            assert "CRITIC" not in _sev(_run(k), "contracte"), (tipar, k)
    for k in _all("legitim_contract_grup")[:3]:  # client din acelasi grup: alarma, dar contra-verificarea o explica (platile sunt reale)
        r = _run(k)
        d = next(x for x in r["contraverificare"] if x["verificare"] == "contracte")
        assert d["acceptat"] and r["verdict"] != "SUSPECT_FRAUDA", k


class FakeLLM:
    native_tools = False

    def __init__(self, raw):
        self.raw = raw

    def complete(self, prompt, max_tokens=600):
        return self.raw


def test_llm_pe_contract_anti_halucinatie():
    from sherlock.firme.contracte import extrage_contract

    k = _all("contract_fictiv", varianta="paravan")[0]
    folder = DATA / "dosare" / k
    raw = json.dumps({"beneficiar_cui": "99999999", "valoare_totala": 123456789,
                      "clauze_neobisnuite": [{"citat": "plata se face in bitcoin la cererea prestatorului", "motiv": "inventat"}]})
    case = T.load_case(k, sorted(str(f) for f in folder.iterdir()), llm=FakeLLM(raw))
    f = extrage_contract(case, "contract")
    assert all(p["cui"] != "99999999" for p in f["parti"]) and f["clauze_neobisnuite"] == []
    assert f["valoare_totala"] != 123456789
    assert any("RESPIN" in a["detaliu"] for a in case.audit if a["actiune"] == "extragere_llm")


# ------------------------------------------------------------------ exemple negative grele
def test_salariile_platite_din_alt_cont_se_lamuresc_cu_documente():
    for k in _all("legitim_salarii_alta_banca")[:3]:
        x = raspuns_client(str(DATA / "dosare" / k), str(DATA / "suplimentare" / k), mode="offline")
        assert any(c["document"] == "extras_cont_salarii" for c in x["inainte"]["documente_cerute"]), k
        assert x["client_a_raspuns"] and x["dupa"]["verdict"] != "SUSPECT_FRAUDA", k


def test_zero_alarme_false_pe_toate_dosarele_legitime_de_test():
    from run_eval import run_case

    fp = [k for k, v in sorted(LABELS.items()) if v["set"] == "test" and v["eticheta"] == "LEGITIM"
          and run_case(k, "complet", None)["verdict"] == "SUSPECT_FRAUDA"]
    assert fp == [], fp


# ------------------------------------------------------------------ feedback
def test_bucla_de_feedback():
    tmp = Path(tempfile.mkdtemp())
    original = copy.deepcopy(T.CONFIG)
    try:
        db = tmp / "fb.db"
        for i in range(4):
            feedback.inregistreaza(f"F{i}", "test", "trimis_antifrauda", "SUSPECT_FRAUDA", "FRAUDA",
                                   [{"verificare": "flux_cont", "severitate": "CRITIC", "corecta": True}], {"acoperire_flux": 0.1 + i * 0.05}, db=db)
            feedback.inregistreaza(f"L{i}", "test", "aprobat_pentru_evaluare", "SUSPECT_FRAUDA", "LEGITIM",
                                   [{"verificare": "flux_cont", "severitate": "CRITIC", "corecta": False}], {"acoperire_flux": 0.42 + i * 0.1}, db=db)
        r = feedback.raport(db)
        assert r["pe_verificare"]["flux_cont"] == {"alarme": 8, "confirmate": 4, "infirmate": 4, "precizie": 0.5}
        assert r["override"] == 4  # analistul a aprobat dosare marcate suspecte
        p = next(x for x in feedback.propune_praguri(db) if x["prag"] == "flux_cont.critic_sub")
        assert 0.25 < p["propus"] < 0.42
        cfg = tmp / "config.yaml"
        shutil.copy(T.BASE / "config.yaml", cfg)
        try:
            feedback.aplica({"flux_cont.critic_sub": 0.3}, "", config_path=cfg)
            raise AssertionError("aplicarea fara analist trebuia refuzata")
        except ValueError:
            pass
        jurnal = feedback.JURNAL
        feedback.JURNAL = tmp / "jurnal.jsonl"
        try:
            feedback.aplica({"flux_cont.critic_sub": 0.3}, "Analist Test", config_path=cfg)
        finally:
            feedback.JURNAL = jurnal
        text = cfg.read_text(encoding="utf-8")
        assert "  critic_sub: 0.3" in text and "# Regulile Sherlock" in text  # comentariile raman
        import yaml

        nou = yaml.safe_load(text)
        assert nou["flux_cont"]["critic_sub"] == 0.3 and nou["salarii"]["critic_sub"] == original["salarii"]["critic_sub"]  # doar flux_cont
    finally:
        T.CONFIG.clear()
        T.CONFIG.update(original)
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ portofoliu si MCP
def test_portofoliul_gaseste_retelele():
    grupuri = _grupuri()
    retele = {k for k, v in LABELS.items() if v["tipar"] == "retea"}
    gasite = {d for g in grupuri if len(g["dosare"]) >= 3 for d in g["dosare"]}
    assert retele <= gasite


def test_mcp_server():
    import mcp_server

    async def run():
        names = {t.name for t in await mcp_server.mcp.list_tools()}
        assert {"analizeaza_dosar", "lista_dosare", "cauta_firma", "portofoliu", "inregistreaza_decizie"} <= names
        r = await mcp_server.mcp.call_tool("analizeaza_dosar", {"dosar": _all("contract_fictiv")[0]})
        assert not r.is_error and "SUSPECT_FRAUDA" in r.content[0].text

    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
