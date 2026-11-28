# Pilot WordPress real pe Oracle — rezultat verificat

**9/9 teste trecute**, zero eșecuri, zero erori, zero omiteri. Execuție încheiată
la 28 noiembrie 2026, **13:51 EET / 11:51 UTC**. Nu este activare de producție.

- Pilot: https://github.com/Ciobanu87/filip-guard/actions/runs/46141522686
- Job Oracle: `140968298788`, concluzie `success`.
- Executor: `a6c769ed73b1060a8180c2800d217bbcdcdf1adf`.
- Candidat aplicație păstrat: `ee593326f89b5db8a1f0700c6a9f18424a36e0e6`.
- Raport structurat: `AUTOFIX_ORACLE_WORDPRESS_RESULT.json`.

## Mediu și încadrare gratuită

Înaintea execuției au fost reverificate identitatea SSH cu amprenta salvată,
alocarea A1 ARM64 în Frankfurt — 1 OCPU, 6 GB RAM, 47 GiB block vizibil — și
capacitatea: 4.734 MiB RAM disponibili, 20.121.239.552 octeți liberi. Nu s-au creat
sau redimensionat resurse cloud. Dovezile proprietarului privind contul Free Tier,
fără upgrade, unica instanță/volum și consumul zero au fost reutilizate. SSH nu
este o verificare a facturării întregului cont; facturarea live nu a fost polled.

Configurația unică se încadrează în limitele oficiale consultate: maximum
744 OCPU-ore și 4.464 GB-ore RAM pentru 31 de zile, sub 1.500/9.000, și 47 GB sub
200 GB boot/block în home region. Surse oficiale și metoda de instalare:
`WORDPRESS_PRIVATE_DEPENDENCIES.md`. Numai repository-urile publice Oracle gratuite;
nicio subscripție ULN, resursă suplimentară, bază enterprise sau serviciu plătit.

Au fost instalate **temporar și privat** PHP **8.3.37**, mysqli și MariaDB din
streamul **10.11**, inclusiv bibliotecile necesare. Pachetele ARM64 au fost
verificate GPG; scriptlet-urile RPM au fost dezactivate. Nu s-a instalat global,
nu s-au pornit unități SQL/PHP ale gazdei. Runtime-ul privat, WordPress-ul,
baza SQL, credențialele sintetice și logurile private au fost eliminate după probă.
Reconstruirea runtime-ului pentru corectarea unei probe eșuate este necesară tocmai
pentru că execuțiile precedente și-au eliminat toate fișierele temporare.

WordPress **7.1.5** și WP-CLI **2.12.0** au fost descărcate din sursele oficiale și
verificate cu hashurile deja fixate. Copia candidatului a păstrat SHA-256 al
arhivei: `75dbf433f0859ca93d6d970bd08af27a5280fc06526aa4f202d9f54222320902`.

## Scenarii executate pe host

| Test existent | Rezultat |
| --- | --- |
| Profilul de producție refuză conținut arbitrar și resurse neadmise | trecut |
| Scanare → propunere → aprobare → backup verificat → aplicare → verificare publică independentă → restaurare aprobată | trecut |
| Răspuns pierdut/trunchiat după scriere: rezultat incert, fără repetare automată | trecut |
| Întrerupere la verificare: rollback verificat | trecut |
| Rollback refuzat când există o modificare WordPress ulterioară | trecut |
| Permisiune revocată înaintea scrierii: intervenție refuzată | trecut |
| Restaurare condiționată și idempotentă | trecut |
| Concurență în condiția SQL: protejarea versiunii | trecut |
| Răspuns pierdut la restaurare: stare explicit neverificată, fără succes fals | trecut |

Sursa testelor: `tests/real_wordpress/run.py`; lista exactă selectată se află în
`oracle_autofix_wordpress_pilot.py`. Întreruperile sunt injectate în transportul
fixture-ului după răspunsuri WordPress reale. Nu am oprit sau întrerupt aplicația
reală și nu afirmăm că această probă testează oprirea fizică a VM.

Durata instalare/pregătire/testare măsurată de controller: **200,04 secunde**.
Ocupare privată la final, înaintea curățării: **1.050.423.727 octeți**, nu o măsurare
a maximului. Testele au rulat ca `nobody`, separat de utilizatorul aplicației,
într-un namespace de rețea cu numai loopback, fără rute externe, și cu namespace
PID separat pentru eliminarea proceselor rămase. Au existat praguri monitorizate
pentru disc, RSS agregat al descendenților și timp, plus limite per proces.

## Corecții și observații de mediu

Executorul a fost corectat pentru enumerarea interfețelor din namespace, generarea
sigură a programului copil și separarea diagnosticelor PHP de răspunsurile HTTP.
Validatorul REST nu a fost modificat: răspunsurile cu MIME greșit au fost refuzate.

Configurația finală folosește fișierele de extensii semnate ale distribuției,
`display_errors=Off` și `log_errors=On`. Manualul PHP precizează că ținta `stderr`
pentru afișare este eficientă numai în CLI/phpdbg/CGI; serverul încorporat folosește
alt SAPI. Erorile nu trebuie afișate în răspunsuri REST:
https://www.php.net/manual/en/errorfunc.configuration.php

Raportul final păstrează un marker **`php-warning` nefatal** din logurile fixture-ului;
nu pretindem că logurile sunt lipsite de avertismente. Mesajul brut nu a fost
publicat și logurile temporare au fost șterse, deci cauza exactă a acestui marker
nu poate fi afirmată din dovada păstrată. Toate aserțiunile au trecut, fără erori
MIME/JSON în raportul final. Acest marker nu este folosit drept dovadă de producție
sau SMTP și nu justifică reluarea automată a celor nouă teste deja trecute.

## Limite importante ale rezultatului

Backupul a folosit criptarea reală, readback și restaurarea resursei, cu un object
store sintetic în memorie. Nu este un apel B2 real și nu este un backup complet al
unui site client. Profilul de producție a existat exclusiv în WordPress-ul privat
de test, cu politică/receipt sintetice, fără chei sau date reale. Nu s-a emis un
receipt de compatibilitate pentru un site client și nu s-a autorizat producția.

Raportul confirmă: fișiere temporare eliminate, inventar RPM global nemodificat,
cele patru unități FILIP GUARD în aceeași stare oprită, zero porturi publice create,
zero Groq/SMTP/B2, nicio utilizare/rotație a cheii master și nicio actualizare a
aplicației existente. `main` a rămas la `763b71a5edee2324cfcbc4739138b4d48fd53e1c`.

## CI și probe anterioare păstrate

https://github.com/Ciobanu87/filip-guard/actions/runs/46141522675
Toate cele cinci joburi verzi: **952 + 24 + 8 = 984 teste**, inclusiv opt teste
noi de protecție a executorului. Probele container/persistență și operațiuni de host
izolate au trecut și ele. Cele nouă teste Oracle sunt o execuție pe alt mediu,
nu nouă teste unice care se adaugă la 984.

Subproba anterioară de **19 teste Python native** rămâne valabilă și nu a fost
reluată: https://github.com/Ciobanu87/filip-guard/actions/runs/46130410616
Detaliile istorice sunt păstrate în `AUTOFIX_ORACLE_NATIVE_PILOT_RESULT.md`.
Evaluările AI reale, registrul de consum și custodia cheilor nu au fost reluate.

## Ce rămâne separat

- Alertarea administratorilor este incompletă; propunerea minimă gratuită este
  în `ADMIN_ALERTING_REVIEW.md`, **neimplementată**, conform instrucțiunii de a o
  prezenta înainte de implementare.
- Validarea unui profil WordPress real autorizat și activarea aplicației Oracle
  necesită în continuare aprobări distincte. Pilotul nu înlocuiește acele validări.
- SMTP real și recuperarea externă B2 cu starea viitoarei instalări nu au fost
  executate în această etapă; interdicțiile de apeluri reale au rămas active.

Pilotul izolat cerut este încheiat. Produsul nu este declarat finalizat pentru
producție pe baza acestei probe.
