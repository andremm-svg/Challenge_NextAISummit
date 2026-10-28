"""Teste pentru Sherlock-firme.   python tests/test_firme.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sherlock import agent  # noqa: E402
from sherlock.firme.tools import CHECKS_VERIFICARE_CLASICA, DATA  # noqa: E402
from sherlock.llm import BedrockLLM  # noqa: E402

LABELS = json.loads((DATA / "etichete.json").read_text(encoding="utf-8"))


def _first(tipar):
    return next(k for k, v in sorted(LABELS.items()) if v["tipar"] == tipar)


def _run(dosar, **kw):
    return agent.investigate_folder(str(DATA / "dosare" / dosar), domeniu="firme", **kw)


def test_fiecare_tipar_de_frauda_e_prins():
    asteptat = {"angajati_fantoma": "salarii", "firma_cumparata": "istoric_firma", "retea": "retea", "pfa_venit_fals": "flux_cont"}
    for tipar, check in asteptat.items():
        r = _run(_first(tipar), mode="offline")
        assert r["verdict"] == "SUSPECT_FRAUDA", tipar
        assert any(f["verificare"] == check and f["severitate"] == "CRITIC" for f in r["constatari"]), tipar


def test_verificarea_clasica_rateaza_fraudele_cu_date_anaf_corecte():
    # firma cumparata: bilantul a fost depus OFICIAL la ANAF, deci verificarea clasica nu vede nimic
    r = _run(_first("firma_cumparata"), mode="offline")
    assert agent.verdict_from(r["constatari"], CHECKS_VERIFICARE_CLASICA) != "SUSPECT_FRAUDA"


def test_dosar_legitim_e_curat():
    r = _run(_first("legitim"), mode="offline")
    assert r["verdict"] in ("CURAT", "REVIZUIRE_UMANA")


def test_injectie_in_bilant_e_izolata():
    cu_injectie = [k for k in sorted(LABELS) if LABELS[k]["tipar"] == "bilant_umflat"
                   and any(f["verificare"] == "injectie" and f["severitate"] == "CRITIC" for f in _run(k, mode="offline")["constatari"])]
    assert len(cu_injectie) == 2  # generatorul ascunde instructiuni in 2 bilanturi
    assert "situatii_financiare" in _run(cu_injectie[0], mode="offline")["documente_izolate"]


class FakeConverse:
    """Simuleaza Claude pe Bedrock: ruleaza 3 unelte si incheie. Controlul automat trebuie sa completeze restul."""

    def __init__(self):
        self.n = 0
        self.plan = [("lista_documente", {}), ("extrage_campuri", {"doc_type": "cerere_credit"}), ("verifica_retea", {}),
                     ("incheie_investigatia", {"rezumat": "Firma face parte dintr-o retea de solicitanti legati."})]

    def converse(self, **kw):
        name, args = self.plan[min(self.n, len(self.plan) - 1)]
        self.n += 1
        return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": f"t{self.n}", "name": name, "input": args}}]}}}


def test_agent_llm_pe_firme_cu_control_automat():
    r = _run(_first("retea"), mode="llm", llm=BedrockLLM(model="test", client=FakeConverse()))
    assert r["mod"] == "llm" and r["verdict"] == "SUSPECT_FRAUDA"
    assert "verifica_flux_cont" in r["verificari_completate_automat"]
    assert r["explicatie"].startswith("Firma face parte")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
