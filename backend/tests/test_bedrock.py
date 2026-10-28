"""Testeaza adaptorul Bedrock fara AWS: un client simulat raspunde ca API-ul Converse.

    python tests/test_bedrock.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sherlock import agent  # noqa: E402
from sherlock.llm import BedrockLLM  # noqa: E402

PLAN = [
    ("lista_documente", {}),
    ("scaneaza_instructiuni_ascunse", {}),
    ("verifica_venit", {}),
    ("verifica_angajator", {}),
    ("incheie_investigatia", {"rezumat": "Venitul declarat nu se regaseste in cont, iar angajatorul nu exista."}),
]


class FakeConverseClient:
    def __init__(self):
        self.calls = []

    def converse(self, **kw):
        self.calls.append(kw)
        msgs = kw["messages"]
        # regulile Bedrock: incepe cu user, rolurile alterneaza
        assert msgs[0]["role"] == "user"
        assert all(a["role"] != b["role"] for a, b in zip(msgs, msgs[1:])), "roluri consecutive identice"
        # fiecare toolResult trebuie sa raspunda unui toolUse anterior
        used = {b["toolUse"]["toolUseId"] for m in msgs for b in m["content"] if "toolUse" in b}
        for m in msgs:
            for b in m["content"]:
                if "toolResult" in b:
                    assert b["toolResult"]["toolUseId"] in used
        step = len(self.calls) - 1
        name, args = PLAN[min(step, len(PLAN) - 1)]
        return {"output": {"message": {"role": "assistant", "content": [
            {"text": f"Pasul {step + 1}"},
            {"toolUse": {"toolUseId": f"t{step}", "name": name, "input": args}},
        ]}}}


def test_bedrock_end_to_end():
    fake = FakeConverseClient()
    llm = BedrockLLM(model="model-test", client=fake)
    original = agent.get_llm
    agent.get_llm = lambda: llm
    try:
        r = agent.investigate_folder(str(ROOT / "data" / "dosare" / "dosar_03_falsificat"), mode="llm")
    finally:
        agent.get_llm = original
    assert r["verdict"] == "SUSPECT_FRAUDA"
    assert r["mod"] == "llm"
    assert "angajatorul nu exista" in r["explicatie"]
    assert "toolConfig" in fake.calls[0] and fake.calls[0]["system"]
    assert len(fake.calls) == len(PLAN)


if __name__ == "__main__":
    test_bedrock_end_to_end()
    print("PASS test_bedrock_end_to_end")
