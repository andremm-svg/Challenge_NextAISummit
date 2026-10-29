"""Doua dosare fictive noi, in acelasi format ca dosarele din baza (cerere PDF, bilant PDF, extras CSV).

  demo_dosare/4_dosar_eligibil_nou/   CARPAT MOBILIER DESIGN SRL: totul se confirma -> verde
  demo_dosare/5_dosar_de_verificat/   DUNAREA TRANS LOGISTIC SRL: avertizari, nicio alarma critica -> portocaliu

Dosarul de verificat nu e o frauda evidenta, ci un caz pentru analist:
  Agentul financiar   bilantul din dosar declara 2,15 mil. lei, ANAF are 1,85 mil. (+16%, peste pragul de avertizare
                      de 8%, sub cel critic de 25%); in cont intra ~1,2 mil. lei pe an, intre 50% si 75% din cifra declarata
  restul              firma veche, acelasi administrator din 2018, salariile se platesc pentru toti cei 9 angajati

Firmele sunt adaugate in registrele sintetice (sherlock.db). Toate datele sunt INVENTATE.
Rulare: python tools_dev/generate_dosare_noi.py   (dupa generate_demo.py, daca baza a fost refacuta)
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_demo as D  # noqa: E402
import generate_firme as G  # noqa: E402

R = random.Random(2910)

ELIGIBIL = {
    "denumire": "CARPAT MOBILIER DESIGN SRL", "cui": "39105720", "tip": "SRL", "caen": "3109",
    "infiintare": date(2016, 3, 22), "adresa": "Str. Fictiunii nr. 18, Cluj-Napoca", "telefon": "0700 311 482",
    "administrator": "VLADESCU ANDREI", "admin_de_la": date(2016, 3, 22), "statut": "ACTIVA", "datorii": 0.0,
    "anaf": {2025: (3_120_000, 3_168_000, 2_826_000, 342_000, 16), 2024: (2_880_000, None, None, None, 15)},
    "credit": {"suma": 600_000, "luni": 48, "scop": "linie noua de productie"},
}
DE_VERIFICAT = {
    "denumire": "DUNAREA TRANS LOGISTIC SRL", "cui": "41273890", "tip": "SRL", "caen": "4941",
    "infiintare": date(2018, 6, 4), "adresa": "Str. Portului Sintetic nr. 5, Galati", "telefon": "0700 527 064",
    "administrator": "RADU CRISTIAN", "admin_de_la": date(2018, 6, 4), "statut": "ACTIVA", "datorii": 0.0,
    "anaf": {2025: (1_850_000, 1_878_000, 1_712_000, 138_000, 9), 2024: (1_640_000, None, None, None, 9)},
    "bilant_dosar": (2_150_000, 2_181_000, 1_975_000, 176_000, 9),  # +16% fata de ANAF
    "credit": {"suma": 450_000, "luni": 36, "scop": "achizitie autoutilitare"},
}


def _rows(clienti: list[str], incasari_lunare: tuple[float, float], angajati: int, furnizori: tuple[float, float]) -> list:
    rows = []
    for m in D._luni():
        total = R.uniform(*incasari_lunare)
        parti = [R.uniform(0.25, 0.45) for _ in range(3)]
        for zi, p in zip((R.randint(2, 7), R.randint(11, 17), R.randint(19, 26)), parti):
            rows.append((m + timedelta(days=zi), f"INCASARE FACTURA {R.choice(clienti)}", round(total * p / sum(parti), 2)))
        rows.append((m + timedelta(days=9), "PLATA SALARII LUNA %02d - %d persoane" % (m.month, angajati),
                     -round(angajati * R.uniform(4_900, 5_300), 2)))
        rows.append((m + timedelta(days=24), "PLATA ANAF CONTRIBUTII", -round(angajati * 5_100 * 0.7, 2)))
        rows.append((m + timedelta(days=R.randint(3, 25)), "PLATA FURNIZOR", -round(R.uniform(*furnizori), 2)))
    return rows


def dosare_noi():
    for f in (ELIGIBIL, DE_VERIFICAT):
        D._cui_valid(f["cui"])
    D._registru([ELIGIBIL, DE_VERIFICAT])

    d4, d5 = D.DEMO / "4_dosar_eligibil_nou", D.DEMO / "5_dosar_de_verificat"
    for d in (d4, d5):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.iterdir():
            old.unlink()

    # 4. eligibil: bilantul = ANAF, ~3,1 mil. lei pe an intra in cont, salarii pentru 16 angajati
    D._cerere(d4, ELIGIBIL)
    D._bilant(d4 / "situatii_financiare.pdf", ELIGIBIL, ELIGIBIL["anaf"][2025])
    D._extras(d4 / "extras_cont.csv", _rows(["CLIENT ALFA SRL", "CLIENT BETA SA", "CLIENT GAMMA SRL", "CLIENT DELTA SRL"],
                                            (245_000, 275_000), 16, (120_000, 160_000)))

    # 5. de verificat: bilant +16% fata de ANAF, ~1,2 mil. lei pe an in cont, salarii platite normal
    D._cerere(d5, DE_VERIFICAT)
    D._bilant(d5 / "situatii_financiare.pdf", DE_VERIFICAT, DE_VERIFICAT["bilant_dosar"])
    D._extras(d5 / "extras_cont.csv", _rows(["CLIENT EPSILON SA", "CLIENT ZETA SRL", "CLIENT BETA SA"],
                                            (92_000, 108_000), 9, (40_000, 55_000)))
    print(f"Dosare noi in {D.DEMO}")


if __name__ == "__main__":
    dosare_noi()
