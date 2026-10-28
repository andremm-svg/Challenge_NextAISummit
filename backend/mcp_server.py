"""Chat cu Sherlock prin MCP: analistul intreaba in Claude (Desktop / Code), Sherlock investigheaza.

    python mcp_server.py            # transport stdio (Claude Desktop, Claude Code)

Configurare: .mcp.json din radacina proiectului (Claude Code) sau claude_desktop_config.json (vezi README).
Uneltele sunt aceleasi pe care le foloseste aplicatia web. Principiul ramane: Sherlock pregateste, omul decide.
Implicit investigatia ruleaza offline (determinist, cateva sutimi de secunda); mod="auto" foloseste si LLM-ul lui Sherlock.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from sherlock import feedback, servicii  # noqa: E402
from sherlock import portofoliu as portofoliu_mod  # noqa: E402

mcp = MCPServer(
    name="sherlock",
    title="Sherlock - antifrauda pentru creditele firmelor",
    instructions=(
        "Sherlock investigheaza dosarele de credit ale firmelor (SRL) si PFA dintr-o banca din Romania: verifica daca "
        "cifrele declarate la ANAF se regasesc in realitate (banii din cont, salariile platite, contractele, retelele de "
        "firme). Verdictul e calculat de reguli deterministe, cu dovezi. Cand raspunzi analistului: citeaza dovezile, "
        "nu inventa cifre, spune ce documente s-au cerut si aminteste ca decizia finala apartine analistului. "
        "Toate datele sunt sintetice."),
)


@mcp.tool()
def lista_dosare(cauta: str = "", set: str = "toate", limita: int = 30) -> list[dict]:
    """Listeaza dosarele de credit (dupa denumire, CUI sau numar de dosar). set: toate | test | calibrare."""
    return servicii.lista_dosare(set=set, cauta=cauta)[:limita]


@mcp.tool()
def analizeaza_dosar(dosar: str, mod: str = "offline", date: str = "curate") -> dict:
    """Investigatia multi-agent a unui dosar (ex. D014): verdict, scor de risc, constatari cu dovezi,
    contra-verificarea, documentele cerute clientului. mod: offline | auto. date: curate | murdare."""
    return servicii.rezumat(servicii.analizeaza(dosar, mode=mod, date=date))


@mcp.tool()
def detalii_verificare(dosar: str, verificare: str) -> list[dict]:
    """Toate constatarile si dovezile unei verificari (ex. flux_cont, salarii, retea, contracte, bilant_vs_anaf)."""
    r = servicii.analizeaza(dosar)
    return [f for f in r["constatari"] if f["verificare"] == verificare] or [{"info": f"Nicio constatare pentru {verificare}"}]


@mcp.tool()
def jurnal_audit(dosar: str) -> list[dict]:
    """Pasii investigatiei: ce sub-agent a rulat ce verificare, ce a completat controlul automat, ce a decis coordonatorul."""
    return servicii.analizeaza(dosar)["audit"]


@mcp.tool()
def raspuns_client(dosar: str) -> dict:
    """Simuleaza raspunsul clientului la documentele cerute si reia investigatia: verdictul inainte si dupa."""
    from sherlock.multi_agent import raspuns_client as rc
    from sherlock.firme.tools import DATA

    x = rc(str(servicii.folder_dosar(dosar)), str(DATA / "suplimentare" / dosar), mode="offline")
    return {"client_a_raspuns": x["client_a_raspuns"], "documente_noi": x["documente_noi"],
            "inainte": servicii.rezumat(x["inainte"], 4), "dupa": servicii.rezumat(x["dupa"], 4)}


@mcp.tool()
def retea_dosar(dosar: str) -> dict:
    """Firmele care au cerut credit in aceeasi perioada si au acelasi administrator, telefon sau adresa."""
    return servicii.retea(dosar)


@mcp.tool()
def cauta_firma(cui_sau_denumire: str) -> list[dict]:
    """Datele din registru (sintetic): administratori, bilanturi ANAF, cereri de credit."""
    return servicii.cauta_firma(cui_sau_denumire)


@mcp.tool()
def portofoliu(rescaneaza: bool = False) -> dict:
    """Situatia portofoliului: expunere pe verdict, grupuri de firme legate, prioritati pentru antifrauda.
    rescaneaza=True re-verifica toate dosarele (cateva zeci de secunde)."""
    r = portofoliu_mod.scaneaza(workers=8) if rescaneaza or not portofoliu_mod.ultima() else portofoliu_mod.ultima()
    return {k: (v[:10] if k in ("prioritati", "grupuri") else v) for k, v in r.items() if k != "dosare"}


@mcp.tool()
def inregistreaza_decizie(dosar: str, analist: str, decizie: str, eticheta: str = "", comentariu: str = "") -> dict:
    """Decizia analistului (aprobat_pentru_evaluare | respins | cere_documente | trimis_antifrauda) si, daca se stie,
    eticheta confirmata (FRAUDA | LEGITIM). Intra in jurnalul de audit si in bucla de feedback."""
    r = servicii.analizeaza(dosar)
    et = eticheta.upper() or None
    return feedback.inregistreaza(dosar, analist, decizie, r["verdict"], et, feedback.din_raport(r, et), r["masuratori"], comentariu)


@mcp.tool()
def raport_feedback() -> dict:
    """Precizia alarmelor pe verificare, din feedback-ul analistilor, si propunerile de recalibrare a pragurilor
    (propuneri: le aproba un om, prin aplicatie sau POST /sherlock/feedback/aplica)."""
    return {"raport": feedback.raport(), "propuneri": feedback.propune_praguri()}



if __name__ == "__main__":
    mcp.run("stdio")
