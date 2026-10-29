# Istoricul proiectului Sherlock

Reconstituit pe 28.10.2026 din istoricul git și din README. Conversațiile propriu-zise s-au purtat într-o sesiune
Claude Code în cloud (`claude.ai/code/session_0155yWC4q8gHJDox5FwS9HC7`), care nu e salvată pe acest calculator,
deci textul lor nu se poate citi de aici. Pe acest calculator nu există alte sesiuni anterioare.

A doua sursă este documentul **„Sherlock – ghidul echipei”** (Claude Docs, 28.10.2026), atașat conversației
de pe claude.ai/chat. Textul conversației din chat nu se poate citi de aici, doar documentul.

## Ghidul echipei (rezumatul documentului)

**Mesajul de 30 de secunde:** băncile verifică la ANAF, dar ANAF arată ce s-a declarat, nu dacă e adevărat.
Sherlock verifică dacă banii intră în cont, dacă salariile se plătesc și dacă firma face parte dintr-o rețea.

**Problema, cu surse:**
- creditele corporate Raiffeisen au crescut cu 17% într-un an, la 29 mld. lei (Business Forum);
- creditele neperformante ale firmelor au ajuns la 5,6% (martie 2026), peste 7% la microîntreprinderi și 11,3%
  la creditele cu garanție de stat (Capital);
- achiziția Garanti BBVA România aduce un portofoliu nou de firme (RBI, T2 2026).

**Cazuri reale:** DIICOT, iunie 2025 (~18 mil. lei, firme preluate, bilanțuri false, bancari complici);
Argeș, iunie 2026 (peste 2,8 mil. lei, angajați fictivi introduși direct la ANAF; băncile au verificat la ANAF
și au aprobat; acesta e **argumentul central**); dosarul trimis în judecată în 2026 (33 de firme, 18 bancari,
peste 81 mil. euro).

**Cele 10 verificări:** identitatea firmei, statutul fiscal, bilanțul față de ANAF, banii din cont, salariile,
istoricul firmei, rețeaua, instrucțiunile ascunse, documentele obligatorii, capacitatea de plată (informativ).

**Criteriile juriului și ce arătăm:**

| Criteriu | Pondere | Dovada |
|---|---|---|
| Agent design | 25% | jurnalul de audit: pașii agentului, apoi ce a completat garda |
| Funcționalitate și testare | 20% | `python run_eval.py` în fața juriului + testele |
| Originalitate | 15% | 90% față de 30% la verificarea clasică |
| Domeniu | 15% | cazurile reale, regulile (CUI, ANAF, AI Act) |
| Arhitectură | 15% | module separate, praguri în config, 2 furnizori LLM |
| Business | 10% | credite frauduloase oprite, chat-ul MCP |

**Întrebări grele pregătite:** datele sintetice (calibrare și test separate, validare pe dosare reale în producție);
de ce LLM dacă regulile decid (citește documente fără format, alege verificările, explică); alarmele false
(merg la analist, nu se respinge nimeni); cele 2 fraude ratate (bilanțuri umflate cu ~20%, trimise la revizuire
umană); păcălirea AI-ului (injecția e izolată, verdictul îl dă codul).

**Fiabilitate:** codul decide, dovezi pentru fiecare constatare, garda, anti-halucinație, anti-injecție,
jurnal de audit, decizia umană cu override, praguri configurabile, merge și fără LLM.

**Plan de extindere la hackathon, în ordinea priorității:** analiza contractelor cu LLM, documente „murdare”,
interfața web în Lovable, chat cu Sherlock prin MCP, bucla de feedback, scanarea de portofoliu.
Pe primul punct există un comentariu în document. După hackathon: întâi un **pilot în umbră**, pe dosare reale,
în paralel cu analiștii.

**Demo de 5 minute:** problema (30 s) → dosar curat (40 s) → firma preluată (60 s) → rețeaua (40 s) →
injecția (30 s) → contractul fictiv (40 s, după extindere) → chat-ul MCP (30 s, după extindere) →
cifrele (30 s) → decizia umană (20 s). Plan B: video înregistrat; modul offline merge oricum.

**Actualizat pe 28.10.2026:** ghidul folosește acum numele noi (controlul automat, sub-agenți, contra-verificare)
și rezultatele multi-agent (precizie 100%, zero alarme false, 2,5% din dosarele legitime trimise la analist),
cu tabelul „Ce aduce fiecare strat”, diagrama refăcută și un pas nou în demo (solicitarea de documente).

## Contextul

- **Competiția:** NEXXT AI Summit 2026, provocarea Raiffeisen „AI for Operational Efficiency”.
- **Ideea:** Sherlock, un agent antifraudă pentru dosarele de credit. ANAF arată ce s-a *declarat*,
  Sherlock verifică dacă cifrele se regăsesc *în realitate*.
- **Principiul:** AI-ul investighează, omul decide. LLM-ul orchestrează, codul decide.
- **Interfața:** construită în Lovable (backend-ul are CORS pentru ea).

## Cronologie

### 1. Motorul de bază pentru persoane fizice (commit `01600e6`)
- Citire PDF (text, metadate, text ascuns), extragere de date, validatori, unelte deterministe.
- Unelte: documente obligatorii, instrucțiuni ascunse (prompt injection), identitate (CNP, buletin),
  angajator (CUI + registru), venit vs. extras, metadate PDF, IBAN, grad de îndatorare.
- Verdicte: `CURAT`, `INCOMPLET`, `REVIZUIRE_UMANA`, `SUSPECT_FRAUDA`.
- 5 dosare sintetice de test (curat, incomplet, falsificat, injecție, typo): **5/5 corecte**.
- LLM prin Featherless; fără cheie rulează un planificator determinist (offline).

### 2. API și Claude prin Bedrock (commit `cf37a09`, 03:14)
- `main.py`: router `/sherlock` și CORS pentru interfața Lovable.
- `llm.py`: furnizor `BedrockLLM` (Converse API, tool use nativ), ales cu `LLM_PROVIDER` (`bedrock` / `featherless`).
- `pdf_reader`: import `pymupdf` în loc de `fitz`.
- `test_bedrock.py`: bucla agentului cu un client AWS simulat.
- Rapoartele generate de teste au fost scoase din git.

### 3. Mesaj de eroare (commit `06d3413`, 03:29)
- Mesajul de eroare numește corect furnizorul LLM ales.

### 4. Pivot pe firme și PFA (commit `a60c896`, 03:50)
- 198 de dosare sintetice: 40 de fraude în 5 tipare și 158 legitime, cu zgomot realist. Registrele sunt în SQLite.
- Tiparele de fraudă: bilanț umflat, firmă preluată pentru credit, angajați fantomă,
  rețea de firme-paravan, PFA cu venit fictiv.
- Unelte noi: identitate, statut fiscal, bilanț vs. ANAF, istoric, fluxul din cont, salarii, rețea, capacitate de plată.
- Agent generic pe domenii (persoane / firme), cu scor de risc.
- `run_eval.py`: recall, precizie, bani opriți, comparație cu verificarea clasică ANAF.
  Pe setul de test: **recall 90% față de 30%, precizie 95%**.
- Endpoint-uri `/sherlock/firme/*`: dosare, analiză, rețea, metrici.
- Modulul pentru persoane fizice a rămas separat, nu mai e în demo.

### 5. Echipa de detectivi și cererea de documente (commit `e8a699f`, 05:03)
- 3 specialiști cu unelte separate (securitate, investigator, contabil), cu LLM sau determinist.
- „Avocatul diavolului” și un „judecător” determinist: alarmele critice nu se anulează niciodată.
- Cererea de documente: extrase de la alte bănci; răspunsul clientului reia investigația.
- `run_eval --comparatie`: clasic vs. simplu vs. echipă vs. echipă + documente.
  Dosare legitime trimise la analist: 15% → 8% → 2,5%; alarme false: 1 → 0; recall 90%.

### 6. Redenumirea (commit `2e10027`, 05:18)
- `echipa.py` → `multi_agent.py`. Sub-agenții: Agentul de documente, Agentul de firmă, Agentul financiar.
- garda → controlul automat; avocatul diavolului → agentul de contra-verificare;
  judecătorul → decizia coordonatorului; cererea → solicitarea de documente.
- Endpoint-uri `/sherlock/firme/multi-agent/{dosar}` și `/raspuns-client`.

### 7. Planul de extindere, plus exemple negative și aplicația (commit `202455d`, 28.10.2026, ramura `extindere-sherlock`)
Cerut: „fă tot proiectul” (cu 4 puncte alese din plan: contracte, documente murdare, chat MCP, feedback + portofoliu),
apoi „mai multe exemple negative în baza de date, ca să nu avem multe alarme false” și „fă-mi și aplicație”.
- **Contracte** (`firme/contracte.py`, Agentul de contracte): extragere din text liber + LLM cu anti-halucinație
  (valori și citate verificate literal), verificare deterministă a beneficiarului (registru, capacitate, firmă nouă,
  legături cu solicitantul, plăți efective). Tipar nou de fraudă: `contract_fictiv` (12 dosare).
- **Documente murdare** (`firme/citire.py`): etichete alternative în config, diacritice, tabele, coduri de rând, formate de
  sumă și dată, extrase CSV de la orice bancă, clasificare după conținut/nume, scanări (Tesseract sau Claude pe Bedrock,
  altfel analist). `dosare_murdare/` pentru toate cele 506 dosare: aceleași verdicte, cu excepția scanărilor necitite.
- **Exemple negative**: +296 de dosare legitime (D199–D506), multe grele; D001–D198 au rămas identice (verificat).
  Solicitare nouă de documente: extrasul contului de salarii.
- **Feedback** (`feedback.py`, `run_feedback.py`): precizie pe verificare, propuneri de praguri care nu pierd fraude,
  validare pe test, aplicare doar cu analist și jurnal. Simularea: flux 0,5→0,384 recomandat, salarii respins.
- **Portofoliu** (`portofoliu.py`, `run_portofoliu.py`): re-verificare completă, grupuri pe tot portofoliul, priorități, schimbări.
- **MCP** (`mcp_server.py`, `.mcp.json`, mcp 2.x): 10 unelte pentru chat-ul analistului.
- **Aplicația** (`backend/app/index.html`, servită la `/app/`): dosare, upload, portofoliu, rezultate, feedback.
- 31 de teste (`pytest -q tests`).
- Bedrock: modelul implicit devine `us.anthropic.claude-sonnet-5-5`; modelele noi refuză `temperature` (reîncercare
  automată fără el) și gândesc înainte să răspundă (plafon minim de 4.000 de tokeni, altfel concluzia ieșea goală).

### 8. Interfața pentru demo, dosarele încărcate și agentul de lizibilitate (29.10.2026, ramura `extindere-sherlock`)
Cerut: interfață mai puțin albă, cu galben și logo Raiffeisen; fără „AI-ul investighează, omul decide” și fără
„Aparține analistului uman”; informații în puncte numerotate, cu cifrele îngroșate; carduri compacte cu Expand, pentru
dosar și pentru fiecare sub-agent; „Dosar eligibil / neeligibil” în meniul din antet; fără modul offline în interfață;
o bază de date goală pentru dosarele încărcate, două dosare demo și testarea fluxului din site; explicații pentru scor,
pagina de feedback și pagina de rezultate.
- **Interfața** (`backend/app/index.html`): galben Raiffeisen `#FEE600` și logo (Wikimedia Commons, domeniu public);
  cardul dosarului e compact (status verde / roșu / portocaliu, risc, sub-agenții care nu au dat OK), iar Expand deschide
  analiza completă în secțiuni numerotate; fiecare sub-agent are cardul lui, cu indicator în colț și Expand cu fiecare
  verificare („ce s-a verificat”, „ce nu este în regulă”, dovezi). Meniul „Documente” din antet filtrează lista pe status
  (Dosar eligibil / Dosar neeligibil / De verificat). Selectorul „curate / murdare” nu mai e în antet: rezultatele pe
  documentele „murdare” sunt în pagina Rezultate. În locul selectorului de mod, antetul arată dacă Claude răspunde.
- **Dosarele încărcate** (`sherlock/incarcate.py`): bază SQLite pornită goală (`data/incarcate/`, nu e în git), cu
  documentele și rezultatul fiecărei analize; documentele noi reiau investigația; documentele înlocuite rămân pentru audit.
- **Agentul de lizibilitate**: documentele scanate pe care nu le poate citi nimeni (Claude răspunde „ILIZIBIL” în loc să
  ghicească) se cer din nou clientului; sub-agentul care depinde de ele „așteaptă un document lizibil”.
- **Rezultatul pe sub-agent** e calculat după controlul automat și contra-verificare (status, probleme), iar verificările
  rulate de controlul automat rămân ale sub-agentului responsabil. Scorul de risc vine cu defalcarea lui.
- **Dosarele demo** (`demo_dosare/`, `tools_dev/generate_demo.py`): eligibil, neeligibil (5 probleme critice prestabilite,
  la 3 sub-agenți) și același dosar eligibil cu bilanțul scanat ilizibil.
- Când Claude nu răspunde (de exemplu token AWS expirat), raportul o spune (`erori_llm`); verdictul rămâne al regulilor.
- 36 de teste; test cap-coadă în browser (Playwright, local): încărcarea celor 3 dosare, statusurile, butoanele Expand,
  reîncărcarea, lista, filtrul, decizia analistului și afișarea pe telefon. Cifrele din evaluare sunt neschimbate.

### 9. Tool intern, dosare noi pentru demo și testele manuale (29.10.2026, `main`)
- Interfața devine un tool intern: fără texte explicative; butonul „Expand” devine „Detalii”; în Portofoliu, „Grupuri de
  firme legate” și „Priorități pentru echipa antifraudă” încep la același nivel. Concluziile lui Claude se afișează cu
  îngroșat și pe rânduri.
- Cheia Bedrock: `AWS_BEARER_TOKEN_BEDROCK` (cheile temporare expiraseră). Testat cap-coadă cu Claude real, inclusiv
  „ILIZIBIL” pe bilanțul scanat.
- Două dosare noi pentru demo, în alt format (`demo_dosare/test_nou/`, `tools_dev/generate_test_nou.py`): ARCADIA
  (eligibil, avertizare lămurită de contra-verificare) și NORDIC STEEL (neeligibil: text ascuns în contract, angajați
  fantomă, bani lipsă, beneficiar paravan; bilanțul e identic cu ANAF).
- Teste manuale pentru ziua demo-ului: `docs/QA_MANUAL.md` (22 de cazuri). 37 de teste automate.
- Documentul de arhitectură (agenți, flux de date, situații neprevăzute, criteriile juriului, demo, teste):
  „Sherlock: arhitectura soluției”.

## Rezultatele după extindere (setul de test, 253 de dosare: 26 de fraude, 227 legitime)

| Configurație | Recall | Precizie | Alarme false | Legitime la analist | Credite frauduloase oprite |
|---|---|---|---|---|---|
| Verificare clasică ANAF | 23% | 100% | 0 | – | 1,55 mil. lei |
| Agent simplu | 92% | 75% | 8 | 25% | 22,16 mil. lei |
| Multi-agent | 92% | 75% | 8 | 9% | 22,16 mil. lei |
| Multi-agent + solicitare documente | 92% | 100% | 0 | 4% | 22,16 mil. lei |

## Rezultatele finale înainte de extindere (setul de test, 99 de dosare)

| Configurație | Recall | Precizie | Alarme false | Legitime la analist | Credite frauduloase oprite |
|---|---|---|---|---|---|
| Verificare clasică ANAF | 30% | 100% | 0 | – | 1,55 mil. lei |
| Agent simplu | 90% | 95% | 1 | 15% | 5,06 mil. lei |
| Multi-agent | 90% | 95% | 1 | 8% | 5,06 mil. lei |
| Multi-agent + solicitare documente | 90% | 100% | 0 | 2,5% | 5,06 mil. lei |

Fraudele care nu au fost marcate drept suspecte au ajuns la revizuire umană, deci 100% au ajuns la un analist.

## Decizii și limite notate

- Anti-halucinație: o valoare extrasă de LLM trebuie să apară literal în document.
- Anti-prompt-injection: documentele cu text ascuns nu mai ajung la LLM.
- Limita simulării: un fraudator real poate trimite un extras fals; în producție extrasele ar veni prin Open Banking.
- GDPR / AI Act: modelul ar rula în infrastructura băncii, CNP-urile sunt mascate, decizia e umană și se păstrează jurnalul de audit.

## Starea curentă

- Ramura `main` conține tot (punctele 7 și 8), prin pull request-ul #1 (`bf32780`, 29.10.2026). Colegii lucrează pe
  ramuri proprii, pornite din `main`, și deschid pull request-uri.
- Ghidul echipei din Claude Docs are încă cifrele de dinainte de extindere; textul nou e în documentul „Sherlock –
  ghidul echipei (actualizat 29.10.2026)”.
