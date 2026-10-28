"""Teste unitare pentru validatori si pentru bucla agentului (cu un LLM simulat).

    python -m pytest tests -q      sau      python tests/test_unelte.py
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sherlock import agent  # noqa: E402
from sherlock.validators import name_similarity, parse_amount_ro, validate_cnp, validate_cui, validate_iban_ro  # noqa: E402

DOSARE = ROOT / "data" / "dosare"


def test_iban():
    assert validate_iban_ro("RO49AAAA1B31007593840000")["valid"]          # exemplul oficial
    assert not validate_iban_ro("RO48AAAA1B31007593840000")["valid"]      # cifra de control gresita
    assert not validate_iban_ro("RO49AAAA1B3100759384")["valid"]          # prea scurt


def test_cnp():
    from sherlock.validators import cnp_control_digit
    first12 = "190051440012"
    valid = first12 + str(cnp_control_digit(first12))
    r = validate_cnp(valid)
    assert r["valid"] and r["data_nasterii"] == "1990-05-14"
    wrong = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    assert not validate_cnp(wrong)["valid"]                               # cifra de control gresita
    assert not validate_cnp("123")["valid"]


def test_cui():
    assert validate_cui("RO18547290")["valid"]                            # CUI public cunoscut (control corect)
    assert not validate_cui("18547291")["valid"]


def test_nume_si_sume():
    assert name_similarity("POPESCU ANDREI", "Andrei Popescu") == 1.0
    assert 0.85 <= name_similarity("IONESCU ANDREI", "IONESU ANDREI") < 0.97
    assert parse_amount_ro("6.850,00") == 6850.0
    assert parse_amount_ro("+1.050,50 RON") == 1050.5


class FakeLLM:
    """Simuleaza un model care face tool calling nativ, ca sa testam bucla fara internet."""
    native_tools = True
    model = "fake"

    def __init__(self, plan):
        self.plan, self.i = plan, 0

    def complete(self, prompt, max_tokens=600):
        return "{}"

    def chat(self, messages, tools=None, max_tokens=700):
        name, args = self.plan[min(self.i, len(self.plan) - 1)]
        self.i += 1
        tc = SimpleNamespace(id=f"c{self.i}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))
        return SimpleNamespace(content="", tool_calls=[tc])


def test_controlul_automat_completeaza_ce_omite_agentul(monkeypatch=None):
    # Agentul "lenes" ruleaza doar 2 unelte si se opreste. Controlul automat trebuie sa ruleze restul.
    plan = [("lista_documente", {}), ("verifica_identitate", {}),
            ("incheie_investigatia", {"rezumat": "Am verificat doar identitatea."})]
    fake = FakeLLM(plan)
    original = agent.get_llm
    agent.get_llm = lambda: fake
    try:
        r = agent.investigate_folder(str(DOSARE / "dosar_03_falsificat"), mode="llm")
    finally:
        agent.get_llm = original
    assert r["verdict"] == "SUSPECT_FRAUDA"
    assert "verifica_venit" in r["verificari_completate_automat"]
    assert r["explicatie"] == "Am verificat doar identitatea."


def test_injectia_nu_poate_aproba():
    r = agent.investigate_folder(str(DOSARE / "dosar_04_injectie"), mode="offline")
    assert r["verdict"] == "SUSPECT_FRAUDA"
    assert "adeverinta_venit" in r["documente_izolate"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
