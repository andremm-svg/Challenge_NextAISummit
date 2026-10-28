"""Extensia setului sintetic: contracte, mai multe exemple negative (dosare legitime) si documente "murdare".

Rulat din generate_firme.py, dupa setul initial, cu aceeasi stare a generatorului (G), ca D001-D198 sa ramana identice.

  extensii(G)  D199+: fraude cu contract fictiv + ~300 de dosare legitime, multe "grele" (seamana cu frauda):
               afaceri cu numerar, salarii platite din alt cont, firme noi, administrator schimbat, crestere reala mare,
               grupuri legitime, contracte cu clienti din acelasi grup, contracte abia semnate, contracte de achizitie.
  murdare(G)   data/firme/dosare_murdare/<id>: aceleasi dosare in alte formate (etichete cu diacritice, tabele, coduri
               de rand, alte formate de suma si data, extrase de la trei banci diferite, nume de fisier diferite, scanari).
"""
import csv
import json
import random
import shutil
import sqlite3
from datetime import timedelta

LUNI = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie", "octombrie",
        "noiembrie", "decembrie"]
NUMERALE = {12: "douasprezece", 18: "optsprezece", 24: "douazeci si patru", 36: "treizeci si sase"}


def _d(x):
    return x.strftime("%d.%m.%Y")


# ====================================================================== contracte
def _firma_contraparte(G, extra, ca, varsta_luni, ref, bilant=True, **override):
    """Un client al solicitantului: exista in registru, dar nu cere credit."""
    f = {"cui": G.cui(), "denumire": G.denumire_srl().replace(" SRL", G.R.choice([" SA", " SRL"])),
         "data_infiintare": G.months_back(ref, varsta_luni), "adresa": G.adresa(), "telefon": G.telefon(),
         "caen": G.R.choice(list(G.CAEN)), "statut": "ACTIVA", "administrator": G.persoana(), "ca": ca if bilant else None}
    f.update(override)
    extra.append(f)
    return f


def contract_doc(G, app, cp, valoare, durata, inceput, data_c, plata, achizitie=False):
    """Textul unui contract, intr-unul din trei sabloane (contractele reale nu au format fix)."""
    nr = G.R.randint(10, 480)
    obiect = G.CAEN[app["caen"]][0].lower()
    a = {"denumire": app["denumire"], "cui": app["cui"], "adresa": app["adresa"], "administrator": app["administrator"]}
    b = cp
    # in contractele de achizitie solicitantul e clientul, nu prestatorul
    prest, client = (b, a) if achizitie else (a, b)
    t = G.R.randrange(3)
    sfarsit = inceput + timedelta(days=round(durata * 30.44) - 1)
    if t == 0:
        plata_txt = {"lunar": "Art. 4 Plata se face lunar, in transe egale, in termen de 30 de zile de la emiterea facturii.",
                     "final": "Art. 4 Plata se face integral la finalizarea serviciilor, pe baza procesului-verbal de receptie."}[plata]
        return {"titlu": "CONTRACT DE PRESTARI SERVICII", "linii": [
            f"Nr. {nr} din {_d(data_c)}", "Intre:",
            f"{prest['denumire']}, cu sediul in {prest['adresa']},",
            f"CUI {prest['cui']}, reprezentata prin {prest['administrator']}, in calitate de PRESTATOR,", "si",
            f"{client['denumire']}, cu sediul in {client['adresa']},",
            f"CUI RO{client['cui']}, reprezentata prin {client['administrator']}, in calitate de BENEFICIAR,",
            "s-a incheiat prezentul contract, cu respectarea urmatoarelor clauze:",
            f"Art. 1 Obiectul contractului: {obiect[:60]}.",
            f"Art. 2 Durata contractului este de {durata} luni, incepand cu {_d(inceput)}.",
            f"Art. 3 Valoarea totala a contractului este de {G.ro(valoare)} lei, fara TVA.", plata_txt,
            "Art. 5 Prezentul contract a fost incheiat in doua exemplare, cate unul pentru fiecare parte."]}
    if t == 1:
        plata_txt = {"lunar": "Modalitate de plata: lunar, prin ordin de plata, la 30 de zile de la livrare.",
                     "final": "Modalitate de plata: integral la finalizarea livrarilor."}[plata]
        return {"titlu": f"CONTRACT DE FURNIZARE NR. {nr}/{data_c.year}", "linii": [
            f"Data: {data_c.day} {LUNI[data_c.month - 1]} {data_c.year}", "Partile contractante:",
            f"1. FURNIZOR: {prest['denumire']}, Cod fiscal: {prest['cui']}",
            f"   sediul: {prest['adresa']}, reprezentant: {prest['administrator']}",
            f"2. CUMPARATOR: {client['denumire']}, Cod fiscal: RO{client['cui']}",
            f"   sediul: {client['adresa']}, reprezentant: {client['administrator']}",
            f"Obiectul contractului: furnizare, {obiect[:55]}",
            f"Valoarea contractului: {G.ro(valoare).split(',')[0]} lei (fara TVA)",
            f"Perioada de derulare: {_d(inceput)} - {_d(sfarsit)}", plata_txt,
            "Litigiile se solutioneaza pe cale amiabila sau de instantele competente."]}
    plata_txt = "platibila lunar pe baza de situatii de lucrari." if plata == "lunar" else "platibila integral la finalizarea lucrarilor."
    suma = f"{valoare:,.0f}".replace(",", " ")
    return {"titlu": "CONTRACT CADRU DE EXECUTIE LUCRARI", "linii": [
        f"Subscrisa {client['denumire']}, inregistrata sub CUI {client['cui']},",
        "denumita in continuare Beneficiarul,",
        f"si societatea {prest['denumire']} (CUI {prest['cui']}), denumita in continuare Executantul,",
        f"au convenit urmatoarele la data de {_d(data_c)}:",
        f"Executantul va realiza lucrarile descrise in anexa pe o perioada de {durata} ({NUMERALE.get(durata, 'luni')})",
        "luni de la semnare.",
        f"Pretul lucrarilor se ridica la suma de {suma} lei, {plata_txt}",
        "Partile pot modifica prezentul contract numai prin act aditional."]}


def _rename_payments(rows, inceput, ref, cp_name):
    """Clientul din contract plateste efectiv: cea mai mare incasare din fiecare luna de derulare vine de la el."""
    rows = [list(r) for r in rows]
    by_month = {}
    for r in rows:
        if r[2] > 0 and r[1].startswith("INCASARE") and inceput <= r[0] <= ref:
            k = (r[0].year, r[0].month)
            if k not in by_month or r[2] > by_month[k][2]:
                by_month[k] = r
    for r in by_month.values():
        r[1] = f"INCASARE FACTURA {cp_name}"
    return [tuple(r) for r in rows], [r[2] for r in by_month.values()]


def _contract_case(G, extra, var):
    R, REF = G.R, G.REF
    e = G.new_entity("SRL", angajati=R.randint(3, 18))
    a = e["anaf"][2025]
    rows = G.statement(e, a["cifra_afaceri"] * R.uniform(0.9, 1.05), G.salary_for(e))
    durata = R.choice([12, 18, 24, 36])
    loan = G.new_loan(e)
    plata, achizitie = "lunar", False
    fraud = var in ("inexistent", "paravan", "fara_plati", "capacitate")
    if var in ("inexistent", "capacitate", "recent", "achizitie"):
        inceput = REF + timedelta(days=R.randint(-30, 25))
    elif var == "final":
        inceput = REF - timedelta(days=R.randint(90, 240))
        plata = "final"
    else:
        inceput = REF - timedelta(days=R.randint(130, 280))
    data_c = inceput - timedelta(days=R.randint(3, 20))

    if var == "inexistent":  # CUI corect ca forma, dar firma nu exista
        cp = {"cui": G.cui(), "denumire": G.denumire_srl().replace(" SRL", " SA"), "adresa": G.adresa(), "administrator": G.persoana()}
    elif var == "paravan":  # firma infiintata cu 2-4 luni inainte, fara activitate, cu telefonul solicitantului
        cp = _firma_contraparte(G, extra, None, 0, data_c - timedelta(days=R.randint(60, 120)), bilant=False, telefon=e["telefon"])
        cp["data_infiintare"] = data_c - timedelta(days=R.randint(60, 120))
    elif var == "capacitate":  # firma mica, nu poate plati cat scrie in contract
        cp = _firma_contraparte(G, extra, round(R.uniform(120_000, 400_000), -3), R.randint(36, 120), REF)
    else:
        cp = _firma_contraparte(G, extra, round(R.uniform(8e6, 60e6), -4), R.randint(60, 200), REF)
        if var == "grup":
            cp["administrator"] = e["administrator"]

    if fraud:
        anual = a["cifra_afaceri"] * R.uniform(1.2, 2.5)
        if var == "capacitate":
            anual = max(anual, cp["ca"] * R.uniform(3, 8))
        valoare = round(anual * durata / 12, -3)
        loan["suma"] = round(valoare * R.uniform(0.25, 0.5), -3)
        loan["rata"] = G.rata(loan["suma"], loan["luni"])
        loan["scop"] = f"finantarea executiei contractului cu {cp['denumire']}"
    elif var in ("real", "grup"):
        rows, platite = _rename_payments(rows, inceput, REF, cp["denumire"])
        valoare = round(sum(platite) / max(1, len(platite)) * durata, -3)
    elif var == "achizitie":
        valoare = round(loan["suma"] * R.uniform(1.0, 1.3), -3)
        loan["scop"] = f"achizitie echipamente conform contractului cu {cp['denumire']}"
        achizitie = True
    else:
        valoare = round(a["cifra_afaceri"] * R.uniform(0.2, 0.5) * durata / 12, -3)
    doc = contract_doc(G, e, cp, valoare, durata, inceput, data_c, plata, achizitie=achizitie)
    return (e, loan, dict(a), rows), doc


# ====================================================================== exemple negative "grele"
def _salarii_alta_banca(G):
    """Firma legitima care plateste salariile din contul de la alta banca: in extrasul principal salariile lipsesc."""
    R = G.R
    e = G.new_entity("SRL", angajati=R.randint(5, 30))
    a = e["anaf"][2025]
    rows = G.statement(e, a["cifra_afaceri"] * R.uniform(0.9, 1.05), G.salary_for(e, ratio=R.uniform(0.0, 0.15)))
    return e, G.new_loan(e), dict(a), rows


def _supliment_salarii(G, case_id, e):
    R2 = G.R2
    lunar = e["anaf"][2025]["angajati"] * R2.uniform(3600, 5200)
    out = []
    for i in range(12, 0, -1):
        m0 = G.months_back(G.REF, i)
        out.append((m0 + timedelta(days=9), f"PLATA SALARII LUNA {m0.month:02d}", -round(lunar * R2.uniform(0.97, 1.03), 2)))
        out.append((m0 + timedelta(days=R2.randint(2, 26)), "COMISION ADMINISTRARE CONT", -round(R2.uniform(15, 40), 2)))
    d = G.SUPLIMENTARE / case_id
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "extras_cont_salarii.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["data", "descriere", "suma"])
        for dt, desc, sm in sorted(out):
            w.writerow([dt.isoformat(), desc, f"{sm:.2f}"])


def _crestere_reala(G):
    """Firma care chiar a crescut mult (contract nou, extindere): banii din cont confirma cifrele."""
    e = G.new_entity("SRL")
    a = e["anaf"][2025]
    e["anaf"][2024]["cifra_afaceri"] = round(a["cifra_afaceri"] / G.R.uniform(5.2, 6.5), -3)
    rows = G.statement(e, a["cifra_afaceri"] * G.R.uniform(0.9, 1.05), G.salary_for(e))
    return e, G.new_loan(e), dict(a), rows


def extensii(G):
    R = G.R
    # vocabular in plus pentru denumiri (dupa setul initial, deci D001-D198 nu se schimba)
    G.PREFIX.extend(["BOREAL", "CARMEN", "DUNAREA", "EVEREST", "FENIX", "GALAXIA", "HELIOS", "ISTRU", "JUPITER", "KAPPA",
                     "LIBRA", "MAGNUS", "NEPTUN", "OLIMP", "PEGAS", "QUANTUM", "RIVIERA", "SIGMA", "TITAN", "URSA",
                     "VEGA", "WEST", "XENIA", "YORK", "ZEFIR", "AURORA", "BETA", "CAPITAL", "DORNA", "ELITE"])
    G.SUFIX.extend(["BUILD", "PHARMA", "RETAIL", "EXPORT", "GRUP", "DISTRIBUTIE", "INSTAL", "METAL", "LEMN", "PLAST"])
    G.NUME.extend(["Anghel", "Bratu", "Ciobanu", "Diaconu", "Enache", "Fratila", "Grigore", "Hristea", "Iordache", "Jitaru",
                   "Lupu", "Mihai", "Nedelcu", "Olteanu", "Paun", "Roman", "Serban", "Tanase", "Ursu", "Voicu"])
    labels = json.loads((G.OUT / "etichete.json").read_text(encoding="utf-8"))
    strat = {"FRAUDA": 0, "LEGITIM": 0}
    for v in labels.values():
        strat[v["eticheta"]] += 1
    extra, cases = [], []  # (eticheta, tipar, tup, contract)

    for var in ["inexistent", "paravan", "fara_plati", "capacitate"] * 3:
        tup, doc = _contract_case(G, extra, var)
        cases.append(("FRAUDA", "contract_fictiv", tup, doc, {"varianta": var}))
    plan = ([("legitim", lambda: G.legit("SRL"))] * 90 + [("legitim_pfa", lambda: G.legit("PFA"))] * 40 +
            [("legitim_rotunjire", lambda: G.legit("SRL", rotunjire=True))] * 15 +
            [("legitim_varsta_luni", lambda: G.legit("SRL", varsta_luni=R.randint(6, 11)))] * 12 +
            [("legitim_admin_schimbat", lambda: G.legit("SRL", admin_schimbat=True))] * 12 +
            [("legitim_datorii", lambda: G.legit("SRL", datorii=True))] * 8 +
            [("legitim_cash", lambda: G.legit("SRL", cash=True))] * 15 +
            [("legitim_pfa_cash", lambda: G.legit("PFA", cash=True))] * 8 +
            [("legitim_fals_pozitiv", lambda: G.legit("SRL", fals_pozitiv=True))] * 6 +
            [("legitim_salarii_alta_banca", lambda: _salarii_alta_banca(G))] * 10 +
            [("legitim_crestere_reala", lambda: _crestere_reala(G))] * 8)
    for tipar, fn in plan:
        cases.append(("LEGITIM", tipar, fn(), None, {}))
    for _ in range(6):  # grupuri legitime: doua firme ale aceluiasi antreprenor
        owner = G.persoana()
        for _ in range(2):
            e, loan, doc, rows = G.legit("SRL")
            e["administrator"] = owner
            cases.append(("LEGITIM", "legitim_grup", (e, loan, doc, rows), None, {}))
    for var, n in (("real", 30), ("grup", 8), ("recent", 10), ("achizitie", 6), ("final", 6)):
        for _ in range(n):
            tup, doc = _contract_case(G, extra, var)
            cases.append(("LEGITIM", f"legitim_contract_{var}", tup, doc, {}))
    R.shuffle(cases)

    db = sqlite3.connect(G.OUT / "sherlock.db")
    start = len(labels) + 1
    for i, (label, pattern, (e, loan, doc, rows), contract, info) in enumerate(cases, start):
        case_id = f"D{i:03d}"
        db.execute("INSERT INTO firme VALUES (?,?,?,?,?,?,?,?,?)", (e["cui"], e["denumire"], e["tip"], e["data_infiintare"].isoformat(),
                   e["adresa"], e["telefon"], e["caen"], e["statut"], e["datorii_anaf"]))
        db.execute("INSERT INTO administratori VALUES (?,?,?)", (e["cui"], e["administrator"], e["admin_de_la"].isoformat()))
        for an, b in e["anaf"].items():
            db.execute("INSERT INTO bilanturi_anaf VALUES (?,?,?,?,?,?,?)", (e["cui"], an, b.get("cifra_afaceri"), b.get("venituri"),
                       b.get("cheltuieli"), b.get("profit_net"), b.get("angajati")))
        db.execute("INSERT INTO cereri_credit VALUES (?,?,?,?)", (case_id, e["cui"], loan["data_cerere"].isoformat(), loan["suma"]))
        G.write_case(case_id, e, loan, doc, rows, contract=contract)
        if pattern in ("legitim_cash", "legitim_pfa_cash", "legitim_fals_pozitiv"):
            G.write_supplement(case_id, e, rows)
        if pattern == "legitim_salarii_alta_banca":
            _supliment_salarii(G, case_id, e)
        strat[label] += 1
        labels[case_id] = {"eticheta": label, "tipar": pattern, "tip": e["tip"], "suma": loan["suma"],
                           "set": "calibrare" if strat[label] % 2 else "test", "denumire": e["denumire"],
                           "extensie": True, **info}
    for f in extra:  # clientii din contracte: in registru, fara cerere de credit
        db.execute("INSERT INTO firme VALUES (?,?,?,?,?,?,?,?,?)", (f["cui"], f["denumire"], "SRL", f["data_infiintare"].isoformat(),
                   f["adresa"], f["telefon"], f["caen"], f["statut"], 0.0))
        db.execute("INSERT INTO administratori VALUES (?,?,?)", (f["cui"], f["administrator"], f["data_infiintare"].isoformat()))
        if f["ca"]:
            db.execute("INSERT INTO bilanturi_anaf VALUES (?,?,?,?,?,?,?)", (f["cui"], 2025, f["ca"], f["ca"] * 1.01, f["ca"] * 0.93,
                       f["ca"] * 0.07, max(5, int(f["ca"] / 200_000))))
    db.commit()
    db.close()
    (G.OUT / "etichete.json").write_text(json.dumps(labels, indent=1, ensure_ascii=False), encoding="utf-8")
    fr = sum(v["eticheta"] == "FRAUDA" for v in labels.values())
    print(f"Extensie: {len(cases)} dosare noi -> total {len(labels)} ({fr} fraude, {len(labels) - fr} legitime)")


# ====================================================================== documente "murdare"
def _fmt_suma(RM, x, stil):
    if stil == 0:
        return f"{x:,.0f}".replace(",", ".")
    if stil == 1:
        return f"{x:,.0f}".replace(",", " ")
    if stil == 2:
        return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{x:,.2f}"


_FONT = []


def _font():
    """Un font cu diacritice romanesti (ă, ș, ț), daca exista pe sistem; altfel Helvetica fara diacritice."""
    if not _FONT:
        import unicodedata
        from pathlib import Path

        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        for f in (r"C:\Windows\Fontsrial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf"):
            if Path(f).is_file():
                pdfmetrics.registerFont(TTFont("Diacritice", f))
                _FONT.append(("Diacritice", lambda t: t))
                break
        else:
            _FONT.append(("Helvetica", lambda t: "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))))
    return _FONT[0]


def _pdf_tabel(G, path, titlu, antet, perechi, subsol, hidden=None):
    """Formular cu doua coloane (eticheta | valoare), cu antet si subsol, ca la un PDF exportat dintr-un program."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    font, tx = _font()
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    w, h = A4
    c.setFont(font, 8)
    c.drawString(55, h - 40, tx(antet))
    c.setFont(font, 12)
    c.drawString(55, h - 70, tx(titlu))
    c.setFont(font, 10)
    y = h - 105
    for et, val in perechi:
        c.drawString(55, y, tx(et))
        c.drawString(330, y, tx(str(val)))
        y -= 19
    c.setFont(font, 8)
    c.drawString(55, 50, tx(subsol))
    if hidden:
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 1.5)
        c.drawString(55, 40, hidden)
    c.save()


def _scaneaza(path):
    """Transforma PDF-ul intr-unul scanat: doar imagine, fara strat de text."""
    import pymupdf

    src = pymupdf.open(str(path))
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=110, colorspace=pymupdf.csGRAY)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=pix.tobytes("jpeg", jpg_quality=75))
    src.close()
    out.save(str(path), deflate=True)


def _desc_murdar(RM, desc):
    if desc.startswith("INCASARE FACTURA "):
        cl = desc[len("INCASARE FACTURA "):]
        return RM.choice([f"Încasare factură {cl}", f"Transfer primit {cl} contravaloare factura", f"OP primit de la {cl}"])
    if desc.startswith("PLATA SALARII"):
        luna = desc.split("LUNA ")[1][:2] if "LUNA " in desc else "01"
        return RM.choice([f"Plată salarii luna {luna}", f"Drepturi salariale {luna}/2026", f"Stat de plată luna {luna}"])
    return {"PLATA ANAF CONTRIBUTII": "Plată ANAF contribuții sociale", "PLATA FURNIZOR": "Plată furnizor servicii",
            "COMISION ADMINISTRARE CONT": "Comision administrare cont"}.get(desc, desc)


def _csv_murdar(RM, path, rows, iban):
    """Trei formate de export, ca de la trei banci diferite."""
    b = RM.randrange(3)
    path.parent.mkdir(parents=True, exist_ok=True)
    if b == 0:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            fh.write(f"Banca Demo SA - Extras de cont\nIBAN;{iban}\nPerioada;{_d(rows[0][0])} - {_d(rows[-1][0])}\n\n")
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Data tranzactiei", "Detalii tranzactie", "Debit", "Credit"])
            for dt, desc, s in rows:
                v = f"{abs(s):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                w.writerow([_d(dt), _desc_murdar(RM, desc), v if s < 0 else "", v if s > 0 else ""])
    elif b == 1:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Date", "Description", "Amount"])
            for dt, desc, s in rows:
                w.writerow([dt.isoformat(), desc, f"{s:.2f}"])
    else:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter="\t")
            w.writerow(["Data operatiunii", "Explicatie", "Suma (RON)"])
            for dt, desc, s in rows:
                w.writerow([dt.strftime("%d/%m/%Y"), _desc_murdar(RM, desc), f"{s:,.2f}".replace(",", " ").replace(".", ",")])


def _read_rows(path):
    from datetime import date

    with open(path, encoding="utf-8") as fh:
        return [(date.fromisoformat(r["data"]), r["descriere"], float(r["suma"])) for r in csv.DictReader(fh)]


def murdare(G):
    RM = random.Random(G.SEED + 7)  # RNG separat: varianta murdara nu schimba setul curat
    out_root, sup_root = G.OUT / "dosare_murdare", G.OUT / "suplimentare_murdare"
    for root in (out_root, sup_root):
        if root.exists():
            shutil.rmtree(root)
    scanate = 0
    for case_id, e, loan, doc, rows, hidden, contract in G.WRITTEN:
        d = out_root / case_id
        pfa = e["tip"] == "PFA"
        stil = RM.randrange(4)
        dc = loan["data_cerere"]
        data_txt = RM.choice([dc.strftime("%d/%m/%Y"), f"{dc.day} {LUNI[dc.month - 1]} {dc.year}", dc.isoformat()])
        luni = loan["luni"]
        perioada = f"{luni // 12} ani" if luni % 12 == 0 and RM.random() < 0.5 else f"{luni} luni"
        antet = f"Banca Demo S.A. - Formular F-CRD-{RM.randint(1, 9):02d} - generat {RM.choice(['online', 'in agentie'])}"
        _pdf_tabel(G, d / RM.choice(["Cerere_finantare_semnata.pdf", "cerere credit 2026.pdf", "Solicitare_finantare.pdf"]),
                   "Cerere de finanțare – " + ("persoană fizică autorizată" if pfa else "persoană juridică"), antet, [
                       ("Denumirea solicitantului", e["denumire"]),
                       ("Forma juridică", "Persoană fizică autorizată (PFA)" if pfa else "Societate cu răspundere limitată (SRL)"),
                       ("Cod unic de înregistrare", f"RO{e['cui']}" if RM.random() < 0.5 else e["cui"]),
                       ("Reprezentantul legal", e["administrator"].title()),
                       ("Sediul social", e["adresa"]),
                       ("Telefon", e["telefon"].replace(" ", RM.choice([".", "", " "]))),
                       ("Cod CAEN", f"{e['caen']} – {G.CAEN[e['caen']][0][:30]}"),
                       ("Valoarea creditului solicitat", f"{_fmt_suma(RM, loan['suma'], stil)} lei"),
                       ("Perioada de rambursare", perioada),
                       ("Rata lunară estimată", f"{_fmt_suma(RM, loan['rata'], 2)} lei"),
                       ("Destinația creditului", loan["scop"][:60]),
                       ("Data depunerii", data_txt)],
                   "Pagina 1 din 1 - document semnat electronic")
        fin = d / (RM.choice(["D212_2025.pdf", "declaratie unica 2025.pdf"]) if pfa else
                   RM.choice(["Bilant_2025.pdf", "situatii financiare 2025.pdf", "Situatii_financiare_ANAF.pdf"]))
        if pfa:
            _pdf_tabel(G, fin, "DECLARAȚIA UNICĂ – Formular 212 (extras)", "Agentia Nationala de Administrare Fiscala - copie", [
                ("Titular", e["denumire"]), ("Cod fiscal (CIF)", e["cui"]), ("Anul de realizare a venitului", "2025"),
                ("Venitul brut", _fmt_suma(RM, doc["cifra_afaceri"], stil)),
                ("Cheltuielile deductibile", _fmt_suma(RM, doc["cheltuieli"], stil)),
                ("Venitul net anual", _fmt_suma(RM, doc["profit_net"], stil))], "Pagina 1 din 1", hidden=G.INJECTIE if hidden else None)
        else:
            _pdf_tabel(G, fin, "Situațiile financiare anuale la 31.12.2025", f"{e['denumire']} - Cod unic de înregistrare: {e['cui']}", [
                ("Denumire entitate", e["denumire"]), ("Cod unic de înregistrare", e["cui"]),
                ("Cifra de afaceri netă (rd. 01)", _fmt_suma(RM, doc["cifra_afaceri"], stil)),
                ("Venituri totale (rd. 12)", _fmt_suma(RM, doc["venituri"], stil)),
                ("Cheltuieli totale (rd. 13)", _fmt_suma(RM, doc["cheltuieli"], stil)),
                ("Rezultatul net al exercițiului (rd. 18)", _fmt_suma(RM, doc["profit_net"], stil)),
                ("Efectiv mediu de personal (rd. 21)", doc["angajati"])],
                "Intocmit: departament financiar - Pagina 1 din 1", hidden=G.INJECTIE if hidden else None)
        if not hidden and RM.random() < 0.06:
            _scaneaza(fin)
            scanate += 1
        iban = G.make_iban_ro("BDEM", f"{RM.randint(0, 10**16 - 1):016d}")
        _csv_murdar(RM, d / RM.choice(["extras_RO_BDEM.csv", "Extras cont 12 luni.csv", "tranzactii_export.csv"]), rows, iban)
        if contract:
            G.write_pdf(d / RM.choice(["Contract_client.pdf", "contract semnat.pdf"]), contract["titlu"], contract["linii"])
        sup = G.SUPLIMENTARE / case_id
        if sup.is_dir():
            for f in sup.iterdir():
                _csv_murdar(RM, sup_root / case_id / f"export_{f.stem}.csv", _read_rows(f), iban)
    print(f"Documente murdare: {len(G.WRITTEN)} dosare in {out_root} ({scanate} documente financiare scanate)")
