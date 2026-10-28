"""Doua dosare fictive pentru demo, de incarcat din aplicatie (tab-ul „Încarcă un dosar”).

  demo_dosare/1_dosar_eligibil/     LUMINA TEHNIC INSTAL SRL: totul se confirma -> verde
  demo_dosare/2_dosar_neeligibil/   VELTRA COM DISTRIBUTIE SRL: probleme prestabilite -> rosu
  demo_dosare/3_document_ilizibil/  dosarul eligibil, cu bilantul scanat ilizibil -> se cere reincarcarea

Problemele prestabilite din dosarul neeligibil si sub-agentul care le semnaleaza:
  Agentul de firma      firma veche, preluata acum 2 luni de un administrator nou, cu cifre crescute de 13 ori
  Agentul financiar     bilantul din dosar declara 2,85 mil. lei, ANAF are 640 mii; in cont intra doar ~5%;
                        14 angajati declarati la ANAF, salariu platit pentru o singura persoana
  Agentul de contracte  contractul de 2,4 mil. lei e cu o firma care nu exista in registru
  Agentul de documente  dosar complet, fara text ascuns (OK)

Firmele sunt adaugate in registrele sintetice (sherlock.db). Toate datele sunt INVENTATE.
Rulare: python tools_dev/generate_demo.py   (o face si generate_firme.py, dupa ce reface baza)
"""
import csv
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_firme as G  # noqa: E402

DEMO = G.ROOT.parent / "demo_dosare"
R = random.Random(4242)

ELIGIBIL = {
    "denumire": "LUMINA TEHNIC INSTAL SRL", "cui": "38104920", "tip": "SRL", "caen": "4322",
    "infiintare": date(2017, 4, 11), "adresa": "Str. Exemplului nr. 41, Brasov", "telefon": "0700 418 205",
    "administrator": "MARINESCU IOANA", "admin_de_la": date(2017, 4, 11), "statut": "ACTIVA", "datorii": 0.0,
    "anaf": {2025: (2_340_000, 2_386_800, 2_156_800, 230_000, 11), 2024: (2_105_000, None, None, None, 10)},
    "credit": {"suma": 350_000, "luni": 48, "scop": "achizitie utilaje si autoutilitara"},
}
NEELIGIBIL = {
    "denumire": "VELTRA COM DISTRIBUTIE SRL", "cui": "40217735", "tip": "SRL", "caen": "4690",
    "infiintare": date(2019, 5, 6), "adresa": "Calea Sintetica nr. 77, Ploiesti", "telefon": "0700 902 611",
    "administrator": "STANCIU VALENTIN", "admin_de_la": date(2026, 8, 14), "statut": "ACTIVA", "datorii": 0.0,
    # ANAF: cifre depuse oficial dupa preluare (x13 fata de 2024); bilantul din dosar e si mai umflat
    "anaf": {2025: (640_000, 652_000, 590_000, 62_000, 14), 2024: (48_000, None, None, None, 1)},
    "bilant_dosar": (2_850_000, 2_905_000, 2_520_000, 385_000, 14),
    "credit": {"suma": 1_200_000, "luni": 60, "scop": "capital de lucru si stocuri"},
}
CLIENT_REAL = {"denumire": "MERIDIAN RETAIL GRUP SA", "cui": "16508723", "tip": "SRL", "caen": "4711",
               "infiintare": date(2004, 9, 1), "adresa": "Bd. Demonstratiei nr. 12, Bucuresti", "telefon": "0700 135 790",
               "administrator": "CONSTANTIN MIHAELA", "admin_de_la": date(2015, 2, 1), "statut": "ACTIVA", "datorii": 0.0,
               "anaf": {2025: (48_600_000, 49_300_000, 46_100_000, 3_200_000, 210), 2024: (45_900_000, None, None, None, 204)}}
CLIENT_INEXISTENT = {"denumire": "ORION PROIECT DEZVOLTARE SRL", "cui": "45893312",
                     "adresa": "Str. Modelului nr. 3, Bucuresti", "administrator": "IONESCU MARIUS"}
DATA_CERERE = date(2026, 10, 20)


def _cui_valid(cui: str) -> str:
    assert G.cui_control_digit(cui[:-1]) == int(cui[-1]), cui
    return cui


def _registru(firme: list[dict]):
    db = sqlite3.connect(G.OUT / "sherlock.db")
    for f in firme:
        db.execute("DELETE FROM firme WHERE cui=?", (f["cui"],))
        db.execute("DELETE FROM administratori WHERE cui=?", (f["cui"],))
        db.execute("DELETE FROM bilanturi_anaf WHERE cui=?", (f["cui"],))
        db.execute("INSERT INTO firme VALUES (?,?,?,?,?,?,?,?,?)", (f["cui"], f["denumire"], f["tip"], f["infiintare"].isoformat(),
                   f["adresa"], f["telefon"], f["caen"], f["statut"], f["datorii"]))
        db.execute("INSERT INTO administratori VALUES (?,?,?)", (f["cui"], f["administrator"], f["admin_de_la"].isoformat()))
        for an, b in f["anaf"].items():
            db.execute("INSERT INTO bilanturi_anaf VALUES (?,?,?,?,?,?,?)", (f["cui"], an) + b)
    db.commit()
    db.close()


def _cerere(d: Path, f: dict):
    c = f["credit"]
    G.write_pdf(d / "cerere_credit.pdf", "CERERE DE FINANTARE - PERSOANE JURIDICE", [
        f"Solicitant: {f['denumire']}", "Forma juridica: SRL", f"CUI: {f['cui']}",
        f"Reprezentant legal: {f['administrator']}", f"Sediu: {f['adresa']}", f"Telefon: {f['telefon']}",
        f"Cod CAEN: {f['caen']} - {G.CAEN.get(f['caen'], ('activitate comerciala',))[0]}",
        f"Suma solicitata: {G.ro(c['suma'])} RON", f"Perioada: {c['luni']} luni",
        f"Rata lunara estimata: {G.ro(G.rata(c['suma'], c['luni']))} RON", f"Scopul creditului: {c['scop']}",
        f"IBAN: {G.make_iban_ro('BDEM', f'{R.randint(0, 10**16 - 1):016d}')}", f"Data cererii: {DATA_CERERE.strftime('%d.%m.%Y')}",
    ])


def _bilant(path: Path, f: dict, cifre: tuple):
    ca, ven, ch, profit, ang = cifre
    G.write_pdf(path, "SITUATII FINANCIARE ANUALE - EXTRAS", [
        f"Entitate: {f['denumire']}", f"CUI: {f['cui']}", "Exercitiul financiar: 2025", "",
        f"Cifra de afaceri neta: {G.ro(ca)} RON", f"Venituri totale: {G.ro(ven)} RON", f"Cheltuieli totale: {G.ro(ch)} RON",
        f"Profit net: {G.ro(profit)} RON", f"Numar mediu de salariati: {ang}",
    ])


def _contract(path: Path, prestator: dict, client: dict, valoare: float, luni: int, inceput: date, semnat: date):
    G.write_pdf(path, "CONTRACT DE PRESTARI SERVICII", [
        f"Nr. {R.randint(20, 300)} din {semnat.strftime('%d.%m.%Y')}", "Intre:",
        f"{prestator['denumire']}, cu sediul in {prestator['adresa']},",
        f"CUI {prestator['cui']}, reprezentata prin {prestator['administrator']}, in calitate de PRESTATOR,", "si",
        f"{client['denumire']}, cu sediul in {client['adresa']},",
        f"CUI RO{client['cui']}, reprezentata prin {client['administrator']}, in calitate de BENEFICIAR,",
        "s-a incheiat prezentul contract, cu respectarea urmatoarelor clauze:",
        "Art. 1 Obiectul contractului: servicii de instalatii si mentenanta pentru magazinele beneficiarului.",
        f"Art. 2 Durata contractului este de {luni} luni, incepand cu {inceput.strftime('%d.%m.%Y')}.",
        f"Art. 3 Valoarea totala a contractului este de {G.ro(valoare)} lei, fara TVA.",
        "Art. 4 Plata se face lunar, in transe egale, in termen de 30 de zile de la emiterea facturii.",
        "Art. 5 Prezentul contract a fost incheiat in doua exemplare, cate unul pentru fiecare parte.",
    ])


def _extras(path: Path, rows: list):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["data", "descriere", "suma"])
        for dt, desc, s in sorted(rows):
            w.writerow([dt.isoformat(), desc, f"{s:.2f}"])


def _luni():
    return [G.months_back(G.REF, i) for i in range(12, 0, -1)]  # oct 2025 - sep 2026


def _rows_eligibil(contract_lunar: float, contract_de_la: date) -> list:
    rows = []
    clienti = ["CLIENT ALFA SRL", "CLIENT GAMMA SRL", "CLIENT EPSILON SA"]
    for m in _luni():
        rows.append((m + timedelta(days=R.randint(2, 6)), f"INCASARE FACTURA {R.choice(clienti)}", round(R.uniform(52_000, 78_000), 2)))
        rows.append((m + timedelta(days=R.randint(12, 18)), f"INCASARE FACTURA {R.choice(clienti)}", round(R.uniform(60_000, 86_000), 2)))
        rows.append((m + timedelta(days=R.randint(20, 26)), f"INCASARE FACTURA {R.choice(clienti)}", round(R.uniform(30_000, 52_000), 2)))
        if m >= contract_de_la:
            rows.append((m + timedelta(days=27), f"INCASARE FACTURA {CLIENT_REAL['denumire']}", contract_lunar))
        rows.append((m + timedelta(days=9), "PLATA SALARII LUNA %02d - 11 persoane" % m.month, -round(11 * R.uniform(5_000, 5_400), 2)))
        rows.append((m + timedelta(days=24), "PLATA ANAF CONTRIBUTII", -round(11 * 5_200 * 0.7, 2)))
        rows.append((m + timedelta(days=R.randint(3, 25)), "PLATA FURNIZOR MATERIALE", -round(R.uniform(60_000, 90_000), 2)))
    return rows


def _rows_neeligibil() -> list:
    rows = []
    for m in _luni():
        rows.append((m + timedelta(days=R.randint(3, 12)), "INCASARE FACTURA CLIENT BETA SA", round(R.uniform(7_000, 11_000), 2)))
        rows.append((m + timedelta(days=R.randint(15, 25)), "INCASARE FACTURA CLIENT ZETA SRL", round(R.uniform(2_500, 5_000), 2)))
        rows.append((m + timedelta(days=9), "PLATA SALARII LUNA %02d - 1 persoane" % m.month, -round(R.uniform(4_050, 4_250), 2)))
        rows.append((m + timedelta(days=24), "PLATA ANAF CONTRIBUTII", -round(4_150 * 0.7, 2)))
        rows.append((m + timedelta(days=R.randint(3, 25)), "PLATA FURNIZOR", -round(R.uniform(4_000, 7_000), 2)))
    rows.append((date(2026, 8, 20), "DEPUNERE NUMERAR ASOCIAT", 45_000.00))  # nu e incasare de la clienti
    return rows


def _scanare_ilizibila(sursa: Path, dest: Path):
    """Bilantul „scanat” la o rezolutie la care nu se mai poate citi (fara strat de text)."""
    import pymupdf

    src = pymupdf.open(sursa)
    out = pymupdf.open()
    for p in src:
        pix = pymupdf.Pixmap(pymupdf.csGRAY, p.get_pixmap(dpi=14))  # ~2 pixeli pe rand de text: ilizibil
        pagina = out.new_page(width=p.rect.width, height=p.rect.height)
        pagina.insert_image(pagina.rect, pixmap=pix)
    out.set_metadata({"producer": "Scanner Sintetic", "title": "scanare"})
    out.save(dest, deflate=True)


def demo():
    for f in (ELIGIBIL, NEELIGIBIL, CLIENT_REAL):
        _cui_valid(f["cui"])
    _cui_valid(CLIENT_INEXISTENT["cui"])
    _registru([ELIGIBIL, NEELIGIBIL, CLIENT_REAL])
    con = sqlite3.connect(G.OUT / "sherlock.db")
    assert not con.execute("SELECT 1 FROM firme WHERE cui=?", (CLIENT_INEXISTENT["cui"],)).fetchone()
    con.close()

    d1, d2, d3 = DEMO / "1_dosar_eligibil", DEMO / "2_dosar_neeligibil", DEMO / "3_document_ilizibil"
    for d in (d1, d2, d3):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.iterdir():
            old.unlink()

    # 1. eligibil: cifrele din dosar = ANAF, banii intra in cont, salariile se platesc, contract cu un client real care plateste
    _cerere(d1, ELIGIBIL)
    _bilant(d1 / "situatii_financiare.pdf", ELIGIBIL, ELIGIBIL["anaf"][2025])
    contract_de_la = date(2026, 3, 1)
    _contract(d1 / "contract_client.pdf", ELIGIBIL, CLIENT_REAL, 360_000, 12, contract_de_la, date(2026, 2, 20))
    _extras(d1 / "extras_cont.csv", _rows_eligibil(30_000.00, contract_de_la))

    # 2. neeligibil: problemele prestabilite din docstring
    _cerere(d2, NEELIGIBIL)
    _bilant(d2 / "situatii_financiare.pdf", NEELIGIBIL, NEELIGIBIL["bilant_dosar"])
    _contract(d2 / "contract_client.pdf", NEELIGIBIL, CLIENT_INEXISTENT, 2_400_000, 24, date(2026, 9, 1), date(2026, 8, 28))
    _extras(d2 / "extras_cont.csv", _rows_neeligibil())

    # 3. acelasi dosar eligibil, dar bilantul e o scanare ilizibila
    for n in ("cerere_credit.pdf", "contract_client.pdf", "extras_cont.csv"):
        (d3 / n).write_bytes((d1 / n).read_bytes())
    _scanare_ilizibila(d1 / "situatii_financiare.pdf", d3 / "situatii_financiare_scanat.pdf")
    print(f"Dosare demo in {DEMO}")


if __name__ == "__main__":
    demo()
