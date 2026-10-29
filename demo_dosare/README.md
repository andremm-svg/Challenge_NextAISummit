# Dosarele demo

Trei dosare fictive de încărcat în aplicație (`http://127.0.0.1:8000/app/`, tab-ul „Încarcă un dosar”).
Fiecare folder se încarcă selectând **toate** fișierele din el. Firmele există în registrele sintetice
(`backend/data/firme/sherlock.db`); toate datele sunt inventate. Regenerare: `python backend/tools_dev/generate_demo.py`.

## 1. `1_dosar_eligibil/`: LUMINA TEHNIC INSTAL SRL → verde, „Dosar eligibil”

Credit de 350.000 lei pe 48 de luni. Totul se confirmă:

| Sub-agent | Ce confirmă |
|---|---|
| Agentul de documente | dosar SRL complet, fără text ascuns |
| Agentul de firmă | firmă activă din 2017, același administrator, fără legături cu alți solicitanți |
| Agentul financiar | bilanțul din dosar = bilanțul ANAF (2,34 mil. lei); încasările din cont acoperă cifra de afaceri; salarii plătite pentru 11 angajați |
| Agentul de contracte | contract de 360.000 lei cu MERIDIAN RETAIL GRUP SA, firmă reală cu cifră de afaceri de 48,6 mil. lei, care plătește lunar 30.000 lei în cont |

Risc: **0**. Toți cei 4 sub-agenți au dat OK.

## 2. `2_dosar_neeligibil/`: VELTRA COM DISTRIBUTIE SRL → roșu, „Dosar neeligibil”

Credit de 1,2 mil. lei pe 60 de luni. Probleme prestabilite:

| Sub-agent | Problema | Dovada din dosar |
|---|---|---|
| Agentul de firmă | firmă preluată pentru credit | firmă din 2019, administrator nou din 14.08.2026 (acum 2 luni), cifra de afaceri 2025 de 13 ori mai mare decât în 2024 |
| Agentul financiar | bilanț umflat | dosarul declară 2,85 mil. lei, ANAF are 640.000 lei (+345%) |
| Agentul financiar | banii nu intră în cont | încasări reale de ~167.000 lei pe an: 6% din cifra declarată |
| Agentul financiar | angajați fictivi | 14 angajați declarați la ANAF, salariu plătit pentru o singură persoană |
| Agentul de contracte | contract fictiv | contract de 2,4 mil. lei cu ORION PROIECT DEZVOLTARE SRL, CUI 45893312, care nu există în registrul comerțului |
| Agentul de documente | **OK** | dosar complet, fără text ascuns |

Risc: **100** (5 probleme critice × 35 = 175 de puncte, plafonat la 100). Sub status: „Nu au dat OK: Agentul de firmă,
Agentul financiar, Agentul de contracte”. Coordonatorul cere și extrasele de la alte bănci și extrasul contului de salarii.

**De ce e un caz bun pentru demo:** verificarea clasică la ANAF vede o firmă activă, cu bilanț depus și 14 angajați
declarați. Sherlock arată că banii nu există, salariile nu se plătesc și clientul din contract nu există.

## 3. `3_document_ilizibil/`: același dosar eligibil, cu bilanțul scanat ilizibil

1. Încarcă cele 4 fișiere din folder. Rezultat: portocaliu, „De verificat”. Agentul financiar „așteaptă un document
   lizibil”, iar în analiza completă apare secțiunea „Documente de reîncărcat” pentru `situatii_financiare_scanat.pdf`.
2. Încearcă să reîncarci tot `situatii_financiare_scanat.pdf`: cererea se repetă.
3. Reîncarcă `1_dosar_eligibil/situatii_financiare.pdf`: verificarea se reia, iar dosarul devine verde.
   Scanarea înlocuită rămâne în dosar, la „Înlocuite (păstrate pentru audit)”.

## 4. `4_dosar_eligibil_nou/`: CARPAT MOBILIER DESIGN SRL → verde, „Dosar eligibil”

Credit de 600.000 lei pe 48 de luni, în același format ca dosarele din bază (cerere, bilanț, extras; fără contract).
Bilanțul din dosar e identic cu ANAF (3,12 mil. lei), în cont intră ~3,1 mil. lei pe an, salariile se plătesc
pentru toți cei 16 angajați, același administrator din 2016. Risc: **0**, toți sub-agenții dau OK.

## 5. `5_dosar_de_verificat/`: DUNAREA TRANS LOGISTIC SRL → portocaliu, „De verificat”

Credit de 450.000 lei pe 36 de luni. Nu e o fraudă evidentă, ci un caz pentru analist:

| Sub-agent | Constatare | Dovada |
|---|---|---|
| Agentul financiar | bilanț diferit de ANAF (avertizare) | dosar 2,15 mil. lei vs. ANAF 1,85 mil. lei (+16%; avertizare de la 8%, critic de la 25%) |
| Agentul financiar | banii intră doar parțial în cont (avertizare) | ~1,23 mil. lei pe an, 57% din cifra declarată (avertizare sub 75%, critic sub 50%) |
| Agentul de documente, de firmă, de contracte | OK | firmă din 2018, același administrator, 9 angajați plătiți |

Risc: **24**. Contra-verificarea nu poate lămuri cele două avertizări (se susțin una pe alta), așa că dosarul
ajunge la analist. Profitul acoperă ratele doar de 0,8 ori (informativ).

Regenerare pentru 4 și 5: `python backend/tools_dev/generate_dosare_noi.py` (după `generate_demo.py`, dacă baza a fost refăcută).

## După demo

Dosarele încărcate apar în tab-ul „Dosare”, la „Dosare noi” (`N001`, `N002`…). Pentru o repetiție de la zero:
oprește serverul și șterge `backend/data/incarcate/`.

## Test cu dosare noi: `test_nou/`

Două dosare pe care Sherlock nu le-a mai analizat, cu alte firme, alte tipare și **alt format** decât dosarele 1–3:
tabele cu diacritice, alte etichete („Valoarea creditului solicitat”, „Rezultatul net al exercițiului”), nume de
fișiere diferite și extras de la altă bancă (CSV cu `;`, debit/credit separate, date `zz.ll.aaaa`).
Regenerare: `python backend/tools_dev/generate_test_nou.py`.

| Dosar | Firmă | Rezultat | De ce |
|---|---|---|---|
| `test_nou/A_eligibil` | ARCADIA CATERING EVENIMENTE SRL | verde | administrator schimbat acum 4 luni → avertizare la Agentul de firmă, lămurită de contra-verificare (cifre stabile, banii din cont confirmă) |
| `test_nou/B_neeligibil` | NORDIC STEEL MONTAJ SRL | roșu | bilanțul e identic cu ANAF (verificarea clasică ar aproba), dar: text ascuns în contract (Agentul de documente, documentul e izolat de LLM); 22 de angajați la ANAF, salarii pentru 3, doar 42% din bani în cont (Agentul financiar); beneficiarul contractului e înființat cu o lună înainte, are același telefon cu solicitantul și nu are cifră de afaceri (Agentul de contracte). Agentul de firmă dă OK |

Testele manuale pentru demo: [docs/QA_MANUAL.md](../docs/QA_MANUAL.md).
