# Teste manuale (QA) pentru demo

Se rulează în ziua demo-ului, înainte de filmare sau de prezentare. Durată: ~25 de minute. Fișierele sunt în `demo_dosare/`.

**Pregătire:** cheile AWS valide în `backend/.env`; un singur server pornit (`python -m uvicorn main:app --reload` din
`backend`); folderul `backend/data/incarcate/` șters, ca baza să pornească goală; browser deschis la
`http://127.0.0.1:8000/app/`.

Status: ✅ trece · ❌ nu trece (notează ce ai văzut) · ⏭ sărit.

| ID | Test | Pași | Rezultat așteptat | Status |
|---|---|---|---|---|
| QA-01 | Conexiunea cu Claude | Deschide aplicația | Antetul arată „Claude pe Bedrock · conectat” (punct verde) | |
| QA-02 | Baza pornește goală | Tab Dosare → „Dosare noi” | „Dosare noi (0)”, lista spune „Niciun dosar.” | |
| QA-03 | Dosar eligibil | Încarcă un dosar → toate fișierele din `1_dosar_eligibil` → Investighează | În 30–90 s: card verde „Dosar eligibil”, LUMINA TEHNIC INSTAL SRL, risc 0, „4/4 sub-agenți OK”, 4 puncte verzi | |
| QA-04 | Dosar neeligibil | Încarcă `2_dosar_neeligibil` | Card roșu „Dosar neeligibil”, risc 100, „Nu au dat OK: Agentul de firmă, Agentul financiar, Agentul de contracte”; Agentul de documente verde | |
| QA-05 | Detalii pe sub-agent | La QA-04, Detalii pe Agentul financiar, apoi Restrânge | Se deschid 3 probleme critice: bilanț 2.850.000 vs ANAF 640.000 lei, acoperire 6%, 14 angajați / salariu pentru 1; Restrânge le ascunde | |
| QA-06 | Detalii pe dosar | La QA-04, Detalii pe dosar | Secțiuni numerotate: Pași următori, Scor de risc („5 × 35 … plafonat la 100”), Concluzie (scrisă de Claude, cu cifre îngroșate), Probleme (5), Contra-verificare, Documente cerute clientului, Contractele, Documente, Jurnal de audit | |
| QA-07 | Document ilizibil | Încarcă `3_document_ilizibil` | Card portocaliu „De verificat”; Agentul financiar „Document ilizibil”; la Detalii: „Documente de reîncărcat: situatii_financiare_scanat.pdf” | |
| QA-08 | Reîncărcare cu aceeași copie | La QA-07: alege din nou `situatii_financiare_scanat.pdf` → Reîncarcă | Cererea de reîncărcare apare din nou, dosarul rămâne portocaliu | |
| QA-09 | Reîncărcare cu copia bună | Alege `1_dosar_eligibil/situatii_financiare.pdf` → Reîncarcă | Card verde „Dosar eligibil”; la Documente: „Înlocuite: situatii_financiare_scanat.pdf” | |
| QA-10 | Dosar nou A (alt format) | Încarcă toate fișierele din `test_nou/A_eligibil` | Card verde, ARCADIA CATERING EVENIMENTE SRL; la Detalii → Contra-verificare: „Istoricul firmei – explicație acceptată” (administrator schimbat acum 4 luni, cifre stabile) | |
| QA-11 | Dosar nou B (alt format) | Încarcă toate fișierele din `test_nou/B_neeligibil` | Card roșu, NORDIC STEEL MONTAJ SRL; nu au dat OK: Agentul de documente (text ascuns în contract), Agentul financiar (22 angajați / salarii pentru 3; 42% din bani), Agentul de contracte (beneficiar nou, fără cifră de afaceri); Agentul de firmă verde; la Documente: „Izolate (text ascuns)” | |
| QA-12 | Lista și filtrul | Tab Dosare → Dosare noi; meniul „Documente” din antet: Dosar eligibil / Dosar neeligibil / Toate | Lista are toate dosarele încărcate (N001…), cu bandă verde/roșie; filtrul arată doar statusul ales | |
| QA-13 | Redeschidere din listă | Click pe dosarul NORDIC în listă | Se deschide instant (rezultatul e salvat), același status și aceleași probleme | |
| QA-14 | Documente cerute clientului | Pe un dosar încărcat cu „Documente cerute clientului”: alege un fișier → Adaugă documente | Analiza se reia; fișierul apare la Documente | |
| QA-15 | Decizia analistului | Pe NORDIC: nume analist, decizie „trimis antifraudă”, Salvează | Mesaj „Decizie salvată”; tab Feedback → „Decizii (1)” cu dosarul | |
| QA-16 | Override | Pe ARCADIA: decizie „respins”, Salvează | Mesaj „override”; în Feedback, eticheta „override” lângă decizie | |
| QA-17 | Portofoliu | Tab Portofoliu → Scanează acum | În zeci de secunde: cifrele de sus; „Grupuri de firme legate” și „Priorități” una lângă alta, la același nivel | |
| QA-18 | Rezultate | Tab Rezultate | Rândul evidențiat: 92% fraude prinse, 100% precizie, 0 alarme false, 4% legitime la analist | |
| QA-19 | Dosar de test sintetic | Dosare → „Dosare de test” → orice dosar roșu → la Documente cerute: Simulează răspunsul clientului | Înainte / după, cu statusurile | |
| QA-20 | Fișier nepermis | Încarcă un fișier `.exe` sau `.docx` | Mesaj de eroare; nu apare niciun dosar nou în listă | |
| QA-21 | Claude indisponibil | (opțional, la repetiție) pune un token greșit în `.env`, repornește serverul, încarcă `1_dosar_eligibil` | Antet „Claude indisponibil”; dosarul are același status (verde), cu mesajul „Claude indisponibil” în card | |
| QA-22 | Telefon | Micșorează fereastra la lățime de telefon (sau F12 → mod telefon) | Fără derulare orizontală; cardurile sub-agenților unul sub altul | |

**După test:** oprește serverul și șterge `backend/data/incarcate/` pentru o bază goală la demo. Deciziile de test din
Feedback sunt în `backend/data/feedback.db`; șterge fișierul dacă vrei pagina goală.

Testele automate acoperă aceleași scenarii: `cd backend && python -m pytest -q tests` (37 de teste).
