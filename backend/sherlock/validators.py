"""Validatori deterministi (fara AI). Fiecare functie e pura si testabila."""
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

# ---------- CNP ----------
_CNP_KEY = "279146358279"


def cnp_control_digit(first12: str) -> int:
    s = sum(int(a) * int(b) for a, b in zip(first12, _CNP_KEY)) % 11
    return 1 if s == 10 else s


def validate_cnp(cnp: str) -> dict:
    """Verifica lungimea, cifra de control si data nasterii. Returneaza si data nasterii."""
    cnp = (cnp or "").strip()
    if not re.fullmatch(r"\d{13}", cnp):
        return {"valid": False, "motiv": "CNP-ul nu are exact 13 cifre"}
    if cnp_control_digit(cnp[:12]) != int(cnp[12]):
        return {"valid": False, "motiv": "Cifra de control a CNP-ului este gresita"}
    secol = {"1": 1900, "2": 1900, "3": 1800, "4": 1800, "5": 2000, "6": 2000}.get(cnp[0])
    if secol is None:
        return {"valid": False, "motiv": "Prima cifra (sex/secol) nu este suportata"}
    try:
        nastere = date(secol + int(cnp[1:3]), int(cnp[3:5]), int(cnp[5:7]))
    except ValueError:
        return {"valid": False, "motiv": "Data nasterii din CNP nu exista"}
    return {"valid": True, "data_nasterii": nastere.isoformat()}


def age_on(birth_iso: str, ref: date) -> int:
    b = date.fromisoformat(birth_iso)
    return ref.year - b.year - ((ref.month, ref.day) < (b.month, b.day))


# ---------- IBAN ----------
def iban_checksum_ok(iban: str) -> bool:
    iban = iban.replace(" ", "").upper()
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def validate_iban_ro(iban: str) -> dict:
    iban = (iban or "").replace(" ", "").upper()
    if not re.fullmatch(r"RO\d{2}[A-Z]{4}[A-Z0-9]{16}", iban):
        return {"valid": False, "motiv": "Format IBAN RO invalid (trebuie RO + 2 cifre + 4 litere banca + 16 caractere)"}
    if not iban_checksum_ok(iban):
        return {"valid": False, "motiv": "Cifrele de control IBAN sunt gresite"}
    return {"valid": True, "banca": iban[4:8]}


def make_iban_ro(bank: str, account16: str) -> str:
    """Folosit doar pentru generarea datelor sintetice."""
    base = bank + account16 + "RO00"
    digits = "".join(str(int(c, 36)) for c in base)
    check = 98 - int(digits) % 97
    return f"RO{check:02d}{bank}{account16}"


# ---------- CUI (cod fiscal firma) ----------
_CUI_KEY = "753217532"


def cui_control_digit(body: str) -> int:
    body = body.zfill(9)
    s = sum(int(a) * int(b) for a, b in zip(body, _CUI_KEY)) * 10 % 11
    return 0 if s == 10 else s


def validate_cui(cui: str) -> dict:
    cui = re.sub(r"^RO", "", (cui or "").strip().upper())
    if not re.fullmatch(r"\d{2,10}", cui):
        return {"valid": False, "motiv": "CUI-ul trebuie sa contina 2-10 cifre"}
    if cui_control_digit(cui[:-1]) != int(cui[-1]):
        return {"valid": False, "motiv": "Cifra de control a CUI-ului este gresita"}
    return {"valid": True, "cui": cui}


# ---------- Nume ----------
def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name or "")
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^A-Za-z ]", " ", name).upper()
    return " ".join(sorted(name.split()))  # ordinea prenume/nume nu conteaza


def name_similarity(a: str, b: str) -> float:
    return round(SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio(), 3)


# ---------- Sume ----------
def parse_amount_ro(text: str) -> float | None:
    """'6.850,00' -> 6850.0 ; '6850' -> 6850.0"""
    if text is None:
        return None
    t = str(text).strip().replace("RON", "").replace("lei", "").replace(" ", "").lstrip("+")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None
