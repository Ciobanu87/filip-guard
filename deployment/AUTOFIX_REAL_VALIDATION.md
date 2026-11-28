> Actualizare 28 noiembrie 2026: aprobarea pilotului și a dependențelor private
> a fost acordată; pilotul WordPress real pe Oracle a trecut 9/9. Propunerile de
> aprobare și blocajele inițiale din acest document sunt istorice. Vezi
> `AUTOFIX_ORACLE_PILOT_RESULT.md` pentru situația actuală. Producția rămâne oprită.

# Următoarea validare AutoFix — pregătire, fără execuție

Plan pregătit la 28 noiembrie 2026. Nu constituie aprobare și nu execută comenzi,
nu activează workflow-uri Oracle și nu produce dovezi de validare inventate.
Roadmapul și funcționalitățile aplicației rămân neschimbate.

## Candidatul fixat și dovezile reutilizate

Candidat: `ee593326f89b5db8a1f0700c6a9f18424a36e0e6`, exclusiv ramura
`filip-guard-development`. CI existent:
https://github.com/Ciobanu87/filip-guard/actions/runs/46120509281

Au trecut 935 teste principale, 24 WordPress/MySQL temporare și 8 infrastructură
izolată; toate cele cinci joburi sunt verzi. Nu le rerulăm pentru această pregătire.
Cele nouă cazuri AI istorice, validările anterioare B2 și custodia masterului nu
se repetă. Profilul de producție testat este strict WordPress 7.1.5, HTML clasic,
single-site, companionul FILIP GUARD fără pluginuri/MU/drop-in suplimentare și
container public de conținut verificat. Alte configurații nu sunt implicit acceptate.

Arhiva reproductibilă conține numai cele 367 de fișiere urmărite în acest commit,
fără fișiere locale neînregistrate, mediu virtual sau secrete montate:

```sh
git archive --format=tar ee593326f89b5db8a1f0700c6a9f18424a36e0e6 > candidate.tar
sha256sum candidate.tar
```

SHA-256: `75dbf433f0859ca93d6d970bd08af27a5280fc06526aa4f202d9f54222320902`.
Dimensiune: 2.017.280 octeți; tree Git:
`f82d08a3403ffb891677e82ebd871d83a0a873f1`.
Pregătirea a verificat că arhiva nu conține legături/fișiere speciale și că cel mai
mare fișier are 51.442 octeți. Checksumul este o verificare de integritate, nu o
semnătură independentă. La orice diferență oprim transferul și analizăm cauza;
nu schimbăm automat checksumul pentru a accepta alt conținut.

Manifestul inert: `AUTOFIX_REAL_VALIDATION_PLAN.json`. La pregătirea inițială aprobările sale erau false. După aprobarea explicită a
proprietarului, manifestul înregistrează pilotul privat autorizat și rezultatul
parțial; aprobările pentru producție/instalări globale și originile de client
rămân neacordate. Numele fișierului nu corespunde
niciunui request Oracle urmărit de workflow-urile existente. Nu este politică de
producție și nu este fișă de validare cu verificări trecute.

## Ce putem face fără un site WordPress existent

Prima opțiune este un pilot privat, temporar, pe VM Oracle deja existentă, după
aprobarea proprietarului. Nu este un site public nou și nu presupune cumpărarea
unui domeniu, a găzduirii, a unui volum sau a unui serviciu cloud. Datele sunt
exclusiv sintetice; nu se folosește starea clienților, registrul AI real sau cheia
master reală. Cheile/parolele efemere ale fixture-ului nu sunt cheile aplicației.

Scopul său este verificarea candidatului pe arhitectura ARM64 și sistemul real de
găzduire. Nu dovedește compatibilitatea unei teme sau a pluginurilor unui viitor
client și nu înlocuiește recuperarea reală B2 a stării complete a aplicației.

Am reutilizat, fără conectare nouă la Oracle, jurnalul read-only din 26 noiembrie:
https://github.com/Ciobanu87/filip-guard/actions/runs/45824514553
Acesta raporta atunci ARM64, 1 CPU, 5.642 MiB RAM, fără Docker/Podman și 19 GiB
liberi pe filesystemul inspectat. Observația precede configurările ulterioare;
**nu este inventar curent**. Nu presupunem că PHP/MySQL/MariaDB sunt instalate sau
că mai există același spațiu liber. Volumul cloud de 47 GB și mărimea filesystemului
sunt lucruri diferite; acest plan nu redimensionează niciunul.

Dovada host operațional deja existentă, tot fără o nouă execuție:
https://github.com/Ciobanu87/filip-guard/actions/runs/45842027227
Aceasta a confirmat atunci izolarea, recuperarea SQLite, oprirea proceselor de
test și menținerea blocării activării. Nu repetăm acel audit integral.

## Execuția propusă după aprobare — în ordine și cu oprire la blocaj

1. Prin transportul SSH deja fixat, verificare numai în citire a identității,
   serviciilor inactive, dependențelor disponibile, memoriei și spațiului actual.
   Nu sunt necesare chei noi sau o nouă autentificare Groq/Backblaze.
2. Dacă lipsesc PHP 8.3/mysqli, SQL izolat sau alte dependențe gratuite, raportăm
   exact ce lipsește și propunem lista și metoda de instalare. **Această aprobare
   nu acoperă instalări globale**, modificări de repository OS sau servicii SQL.
   Nu presupunem disponibilitatea unor pachete ARM64 în repository-urile gratuite.
3. Dacă dependențele există, pregătim numai un director privat separat și sursa
   fixată. Păstrăm aplicația existentă, mediul său și unitățile nemodificate.
   Verificăm arhiva înainte de extragere. Nu folosim o instalare WordPress existentă.
4. Stabilim înainte de execuție limitele din manifest: maximum 2 GiB scratch,
   minimum 5 GiB rămași liberi, maximum 2 GiB RAM cumulat pentru procesele testului
   și 15 minute. Dacă executorul ales nu poate impune limitele, oprim pregătirea.
   Acestea sunt limite propuse, nu consumuri măsurate pe Oracle în această sesiune.
5. Instanță SQL nouă și temporară, fără configurația/data directory ale unui SQL
   existent; port neprivilegiat, liber și exclusiv loopback. Niciun fallback la
   portul standard sau la un server partajat. PHP/HTTPS doar loopback, cu CA și
   certificate efemere ale fixture-ului. Fără porturi publice sau firewall schimbat.
6. Folosim două scenarii existente, nu întreaga suită: refuzul schimbărilor arbitrare
   și al resurselor neadmise; apoi diagnostic → propunere → aprobare → backup
   verificat → CAS → verificare publică → restaurare aprobată și verificată.
   Modul WordPress `production` este simulat numai în această instalare temporară,
   ca în CI. Aplicația reală și companionul unui site real rămân dezactivate.
7. Procesele rulează fără root, cu stocare temporară și fără credențiale reale în
   mediu. Niciun Groq, SMTP sau B2 real. Backupul acestui pilot folosește fixture-ul
   existent; raportul trebuie să spună explicit că nu este dovadă cloud B2.
8. Oprire/curățare exclusiv a proceselor și fișierelor create de pilot, cu verificarea
   listenerelor închise și a serviciilor FILIP GUARD rămase inactive. Păstrăm numai
   dovezi private necesare și un rezumat fără credențiale; rezultatele incerte nu
   sunt marcate ca succes și nu declanșează reîncercare automată.

Runnerul existent `tests/real_wordpress/run.py` cere sursă WordPress curată, WP-CLI,
PHP și o bază de date izolată. **Nu se lansează pe Oracle cu valorile sale implicite**:
adaptorul de execuție pentru host trebuie să lege explicit datele/porturile/limitele
private de dependențele efectiv găsite. Nu îl prezentăm ca executor Oracle gata
validat înainte de această verificare; nu îl îndreptăm spre un WordPress existent.

## Pentru compatibilitatea unui site real — etapă distinctă

Dacă există deja un WordPress propriu sau permisiunea unui proprietar:

- Tu indici URL-ul și confirmi dreptul de testare pe o copie separată, fără date
  reale de clienți. Dacă nu există copie, nu cumperi nimic; stabilim mai întâi unde
  poate fi creată gratuit și ce permisiune explicită avem pentru modificări.
- Eu verific versiunea, tema, pluginurile, metadatele, selectorul public și metoda
  de acces. Incompatibilitatea nu se rezolvă prin schimbarea flagurilor sau
  ascunderea pluginurilor; nicio actualizare a site-ului nu este implicit aprobată.
- Dacă accesul privat nu poate fi reutilizat, tu faci numai autentificarea sau
  acordarea accesului de proprietar indispensabilă. Credențialele se introduc
  printr-un canal privat, niciodată în chat, commit, issue sau log public.
- Protocolul de modificare se fixează pe resurse de test și se aprobă înainte de
  prima scriere. Abia după dovezi reale revizuite pregătim fișa și politica privată
  pentru release/resurse/fereastră. Nu reciclăm fișele sintetice din CI/pilot.

Pentru un mediu extern neales nu există încă un executor general validat; metoda
se adaptează numai după identificarea copiei și a accesului, fără ocolirea regulii
`.test` a vechiului traseu. Această pregătire nu inventează acces sau autorizare.

## Exact ce trebuie să faci personal

Pilotul privat și instalarea dependențelor au fost aprobate și executate. **Nu mai
este necesară intervenția proprietarului pentru acest pilot.** Au trecut 9/9
scenarii WordPress reale pe Oracle, cu curățare verificată și producția oprită.
Raport: `AUTOFIX_ORACLE_PILOT_RESULT.md`.

Pentru etapele separate care nu sunt autorizate prin pilot:

- Aprobarea propunerii minime de alertare și controlul/verificarea adresei de
  administrator pentru contul extern gratuit, înaintea implementării.
- Alegerea unei copii WordPress reale autorizate, URL-ul și confirmarea dreptului
  de testare, înaintea validării unui profil client; accesul numai prin canal privat.
- Aprobarea distinctă înaintea instalării versiunii în aplicația Oracle existente,
  recuperării stării reale sau activării serviciilor. Validarea SMTP rămâne separată.

Înlocuirea cheii master, resetarea bugetului AI, activarea altui furnizor sau
upgrade-ul la un plan plătit nu sunt necesare și nu au fost efectuate.

## Rezultatul după aprobările proprietarului

Proba nativă Python anterioară de 19 teste este păstrată, fără reluare. Proba nouă
WordPress/PHP pe ARM64 a trecut 9/9: PHP 8.3.37 cu mysqli și SQL privat MariaDB
10.11, date sintetice, rețea izolată, zero Groq/SMTP/B2 și toate fișierele temporare
eliminate. Nu s-a modificat aplicația existentă sau `main` și nu s-a activat
producția. Nu folosim receipt-urile sintetice pentru autorizarea unui site client.
