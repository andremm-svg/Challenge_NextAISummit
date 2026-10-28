"""Sherlock: agentul care investigheaza un dosar de credit.

Arhitectura (aceeasi pentru ambele domenii):
  - LLM-ul (Claude prin Bedrock sau Featherless) ORCHESTREAZA: alege uneltele si ordinea, apoi explica.
  - Uneltele DECID: reguli deterministe, cu dovezi.
  - Garda ruleaza orice verificare obligatorie pe care agentul a sarit-o.
  - Verdictul e calculat de cod din constatari. LLM-ul nu poate aproba nimic.
  - Omul ia decizia finala.

Domenii:
  "persoane" : persoane fizice (buletin, adeverinta, extras, cerere)       -> sherlock/tools.py
  "firme"    : firme SRL si PFA (cerere, bilant/declaratie, extras CSV)   -> sherlock/firme/tools.py

Moduri: "llm", "offline" (planificator determinist), "auto" (llm daca e configurat).
"""
import importlib
import json
import re
import time
from pathlib import Path

from .llm import get_llm

MAX_STEPS = 16
SEV_ORDER = {"CRITIC": 0, "LIPSA": 1, "AVERTIZARE": 2, "INFO": 3, "OK": 4}
VERDICTE = {
    "SUSPECT_FRAUDA": "Suspiciune de fraudă – trimis la echipa antifraudă",
    "INCOMPLET": "Dosar incomplet – se solicită documente",
    "REVIZUIRE_UMANA": "Necesită revizuire umană",
    "CURAT": "Dosar curat – gata pentru decizia analistului",
}
DOMAINS = {"persoane": "sherlock.tools", "firme": "sherlock.firme.tools"}

JSON_MODE_SUFFIX = """
Raspunde la fiecare pas cu UN SINGUR obiect JSON si nimic altceva:
{"unealta": "<nume>", "argumente": {...}}
Unelte disponibile: %s
Pentru final: {"unealta": "incheie_investigatia", "argumente": {"rezumat": "..."}}"""


def _domain(name: str):
    if name not in DOMAINS:
        raise ValueError(f"Domeniu necunoscut: {name}")
    return importlib.import_module(DOMAINS[name])


def _tool_schemas(dom, doc_types: list[str], tool_names: list[str] | None = None) -> list[dict]:
    schemas = []
    for name, (_, desc) in dom.TOOLS.items():
        if tool_names is not None and name not in tool_names:
            continue
        params = {"type": "object", "properties": {}, "required": []}
        if name == "extrage_campuri":
            params = {"type": "object", "properties": {"doc_type": {"type": "string", "enum": doc_types}}, "required": ["doc_type"]}
        schemas.append({"type": "function", "function": {"name": name, "description": desc, "parameters": params}})
    schemas.append({"type": "function", "function": {
        "name": "incheie_investigatia", "description": "Incheie investigatia cu un rezumat pentru analist.",
        "parameters": {"type": "object", "properties": {"rezumat": {"type": "string"}}, "required": ["rezumat"]}}})
    return schemas


def _result_for_llm(case, result: dict, before: int) -> str:
    new = [{"severitate": f["severitate"], "mesaj": f["mesaj"], "dovezi": f["dovezi"][:4]} for f in case.findings[before:]]
    text = json.dumps({"rezultat": result, "constatari_noi": new}, ensure_ascii=False)[:3000]
    return re.sub(r"\b(\d{3})\d{7}(\d{3})\b", r"\1*******\2", text)  # CNP-urile nu ajung intregi la LLM


def _execute(dom, case, name: str, args: dict, tool_names=None, actor="agent") -> tuple[str, str | None]:
    if name == "incheie_investigatia":
        return "ok", (args or {}).get("rezumat", "")
    if tool_names is not None and name not in tool_names:
        return json.dumps({"eroare": f"Unealta {name} nu face parte din rolul tau. Foloseste: {tool_names}"}, ensure_ascii=False), None
    before = len(case.findings)
    result = dom.run_tool(case, name, args, actor=actor)
    return _result_for_llm(case, result, before), None


def _run_llm(dom, case, llm, tool_names=None, system=None, user_msg=None, actor="agent", max_steps=MAX_STEPS) -> str | None:
    """Bucla agentului. Cu tool_names/system se ruleaza un specialist care vede doar uneltele rolului sau."""
    doc_types = list(case.docs)
    tip = case.state.get("tip")
    user_msg = user_msg or (f"Investigheaza dosarul {case.case_id}" + (f" ({tip})" if tip else "") + f". Documente incarcate: {doc_types}.")
    system = system or dom.SYSTEM_PROMPT
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
    native = llm.native_tools
    schemas = _tool_schemas(dom, doc_types, tool_names)
    allowed = list(tool_names) if tool_names is not None else list(dom.TOOLS)

    def to_json_mode():
        messages[0]["content"] = system + JSON_MODE_SUFFIX % allowed

    def run(name, args):
        return _execute(dom, case, name, args, tool_names, actor)

    for step in range(max_steps):
        try:
            msg = llm.chat(messages, tools=schemas) if native else llm.chat(messages)
        except Exception as e:  # noqa: BLE001
            if native and step == 0:
                case.log("sistem", "fallback_json", f"Modelul nu suporta tool calling nativ ({type(e).__name__}); trec pe protocol JSON")
                native = False
                to_json_mode()
                continue
            case.log("sistem", "eroare_llm", f"{type(e).__name__}: {str(e)[:200]}")
            return None

        if native and getattr(msg, "tool_calls", None):
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                            for tc in msg.tool_calls]})
            final = None
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                reply, fin = run(tc.function.name, args)
                final = fin if fin is not None else final
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": reply})
            if final is not None:
                return final
            continue

        content = re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.S)
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            if native and step == 0:
                native = False
                to_json_mode()
                case.log("sistem", "fallback_json", "Modelul nu a apelat unelte; trec pe protocol JSON")
                continue
            case.log("agent", "raspuns_fara_actiune", content[:200])
            return content.strip() or None
        try:
            action = json.loads(m.group(0))
            name, args = action.get("unealta") or action.get("tool"), action.get("argumente") or action.get("args") or {}
        except json.JSONDecodeError:
            messages.append({"role": "user", "content": "JSON invalid. Raspunde doar cu obiectul JSON cerut."})
            continue
        messages.append({"role": "assistant", "content": m.group(0)})
        reply, final = run(name, args)
        if final is not None:
            return final
        messages.append({"role": "user", "content": f"REZULTAT {name}: {reply}"})

    case.log("sistem", "limita_pasi", f"{actor} a atins limita de {max_steps} pasi; garda preia verificarile ramase")
    return None


def _guardrail(dom, case) -> list[str]:
    forced = [n for n in dom.MANDATORY if n not in case.executed]
    for n in forced:
        dom.run_tool(case, n, actor="garda")
    if forced:
        case.log("garda", "verificari_fortate", f"Agentul a omis: {forced}. Au fost rulate automat.")
    return forced


def verdict_from(findings: list, checks: set | None = None) -> str:
    sev = {f["severitate"] for f in findings if checks is None or f["verificare"] in checks}
    if "CRITIC" in sev:
        return "SUSPECT_FRAUDA"
    if "LIPSA" in sev:
        return "INCOMPLET"
    if "AVERTIZARE" in sev:
        return "REVIZUIRE_UMANA"
    return "CURAT"


def risk_score(findings: list) -> int:
    pts = {"CRITIC": 35, "LIPSA": 15, "AVERTIZARE": 12}
    return min(100, sum(pts.get(f["severitate"], 0) for f in findings))


def _next_steps(findings: list, verdict: str) -> list[str]:
    steps = []
    for f in findings:
        if f["severitate"] == "LIPSA":
            steps.append(f"Solicitați clientului: {f['mesaj']}")
        elif f["severitate"] == "CRITIC":
            steps.append(f"Antifraudă – verificați: {f['mesaj']}")
        elif f["severitate"] == "AVERTIZARE":
            steps.append(f"Analistul confirmă: {f['mesaj']}")
    if verdict == "CURAT":
        steps.append("Analistul poate trece la evaluarea de risc și decizia de creditare.")
    return steps


def _template_summary(dom, findings: list, verdict: str) -> str:
    probleme = [f["mesaj"] for f in findings if f["severitate"] in ("CRITIC", "LIPSA", "AVERTIZARE")]
    if not probleme:
        return dom.OK_SUMMARY
    return f"{VERDICTE[verdict]}. Probleme găsite: " + " ".join(f"({i}) {p}." for i, p in enumerate(probleme, 1))


def investigate(case_id: str, paths: list[str], mode: str = "auto", domeniu: str = "persoane", llm=None) -> dict:
    t0 = time.time()
    dom = _domain(domeniu)
    if llm is None and mode in ("auto", "llm"):
        llm = get_llm()
    if mode == "offline":
        llm = None
    if mode == "llm" and llm is None:
        raise RuntimeError("Mod 'llm' cerut, dar LLM-ul nu e configurat in .env. "
                           "Vezi mesajul [Sherlock] de mai sus: arata exact ce camp lipseste.")
    used_mode = "llm" if llm else "offline"
    case = dom.load_case(case_id, paths, llm=llm)
    case.log("sistem", "start", f"domeniu={domeniu}, mod={used_mode}" +
             (f", furnizor={getattr(llm, 'provider', '?')}, model={llm.model}" if llm else ""))

    summary = _run_llm(dom, case, llm) if llm else dom.run_offline(case)
    forced = _guardrail(dom, case)
    verdict = verdict_from(case.findings)
    if not summary:
        summary = _template_summary(dom, case.findings, verdict)

    findings = sorted(case.findings, key=lambda f: SEV_ORDER.get(f["severitate"], 9))
    report = {
        "dosar": case_id,
        "domeniu": domeniu,
        "tip_entitate": case.state.get("tip"),
        "mod": used_mode,
        "verdict": verdict,
        "eticheta": VERDICTE[verdict],
        "scor_risc": risk_score(findings),
        "explicatie": summary,
        "decizie_finala": "Aparține analistului uman. Sherlock pregătește, omul decide.",
        "constatari": findings,
        "urmatorii_pasi": _next_steps(findings, verdict),
        "documente": {t: d["file"] for t, d in case.docs.items()},
        "documente_izolate": sorted(case.quarantined),
        "verificari_fortate_de_garda": forced,
        "audit": case.audit,
        "durata_sec": round(time.time() - t0, 2),
    }
    if "retea" in case.state:
        report["retea"] = case.state["retea"]
    return report


def investigate_folder(folder: str, mode: str = "auto", domeniu: str | None = None, llm=None) -> dict:
    p = Path(folder)
    files = sorted(str(f) for f in p.iterdir() if f.suffix.lower() in (".pdf", ".csv"))
    if domeniu is None:
        names = {Path(f).name for f in files}
        domeniu = "firme" if names & {"situatii_financiare.pdf", "declaratie_unica.pdf", "extras_cont.csv"} else "persoane"
    return investigate(p.name, files, mode=mode, domeniu=domeniu, llm=llm)
