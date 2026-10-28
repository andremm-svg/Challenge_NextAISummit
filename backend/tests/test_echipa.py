"""Teste pentru echipa de detectivi si bucla de cerere a documentelor.   python tests/test_echipa.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sherlock.echipa import investigate_echipa_folder, raspuns_client  # noqa: E402
from sherlock.firme.tools import DATA  # noqa: E402
from sherlock.llm import BedrockLLM  # noqa: E402

LABELS = json.loads((DATA / "etichete.json").read_text(encoding="utf-8"))


def _first(tipar):
    return next(k for k, v in sorted(LABELS.items()) if v["tipar"] == tipar)


def _dir(k):
    return str(DATA / "dosare" / k)


def test_avocatul_scoate_din_revizuire_firmele_noi_legitime():
    r = investigate_echipa_folder(_dir(_first("legitim_varsta_luni")), mode="offline")
    assert r["verdict_inainte_de_dezbatere"] == "REVIZUIRE_UMANA" and r["verdict"] == "CURAT"
    assert any(d["acceptat"] for d in r["dezbatere"])


def test_avocatul_nu_poate_anula_o_alarma_critica():
    for tipar in ("firma_cumparata", "angajati_fantoma", "retea", "pfa_venit_fals"):
        r = investigate_echipa_folder(_dir(_first(tipar)), mode="offline")
        assert r["verdict"] == "SUSPECT_FRAUDA", tipar
        assert not any(d["acceptat"] for d in r["dezbatere"] if d["severitate_initiala"] == "CRITIC"), tipar


def test_cererea_de_documente_rezolva_alarma_falsa():
    k = _first("legitim_fals_pozitiv")
    x = raspuns_client(_dir(k), str(DATA / "suplimentare" / k), mode="offline")
    assert x["inainte"]["verdict"] == "SUSPECT_FRAUDA" and x["inainte"]["documente_cerute"]
    assert x["client_a_raspuns"] and x["dupa"]["verdict"] == "CURAT"


def test_fraudatorul_nu_are_ce_trimite():
    k = _first("pfa_venit_fals")
    x = raspuns_client(_dir(k), str(DATA / "suplimentare" / k), mode="offline")
    assert x["client_a_raspuns"] is False and x["dupa"]["verdict"] == "SUSPECT_FRAUDA"
    assert any(f["verificare"] == "documente_cerute" for f in x["dupa"]["constatari"])


class FakeTeam:
    """Simuleaza Claude pe Bedrock pentru fiecare membru al echipei."""

    PLAN = {"Ofi": ["verifica_documente_obligatorii", "scaneaza_instructiuni_ascunse"],
            "Inv": ["verifica_identitate_firma", "verifica_retea"],  # omite statutul si istoricul -> garda
            "Con": ["verifica_bilant_vs_anaf", "verifica_flux_cont", "verifica_salarii"]}

    def __init__(self):
        self.calls = []

    def converse(self, **kw):
        self.calls.append(kw)
        system = kw.get("system", [{"text": ""}])[0]["text"] if kw.get("system") else ""
        text = kw["messages"][0]["content"][0].get("text", "")
        if "toolConfig" not in kw:
            body = '{"retea": "Firmele pot fi ale aceluiasi grup."}' if text.startswith("Esti avocatul diavolului") else "Concluzia echipei: retea suspecta."
            return {"output": {"message": {"role": "assistant", "content": [{"text": body}]}}}
        plan = next(v for k, v in self.PLAN.items() if f"Esti {k}" in system)
        done = sum(1 for m in kw["messages"] for b in m["content"] if "toolResult" in b)
        if done < len(plan):
            return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": f"t{len(self.calls)}", "name": plan[done], "input": {}}}]}}}
        return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": f"t{len(self.calls)}",
                "name": "incheie_investigatia", "input": {"rezumat": f"Raport {system[5:20]}"}}}]}}}


def test_echipa_cu_llm_si_garda():
    fake = FakeTeam()
    r = investigate_echipa_folder(_dir(_first("retea")), mode="llm", llm=BedrockLLM(model="test", client=fake))
    assert r["mod"] == "llm" and r["verdict"] == "SUSPECT_FRAUDA"
    assert "verifica_statut_fiscal" in r["verificari_fortate_de_garda"]
    assert all(s["rezumat"].startswith("Raport") for s in r["specialisti"])
    assert r["explicatie"].startswith("Concluzia echipei")
    assert any(d["avocatul_diavolului"] == "Firmele pot fi ale aceluiasi grup." for d in r["dezbatere"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
