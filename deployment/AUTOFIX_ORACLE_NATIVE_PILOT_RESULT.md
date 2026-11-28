> Raport istoric al primei subprobe. Blocajul de dependențe descris mai jos
> a fost ulterior rezolvat prin aprobarea instalării private și pilotul WordPress.
> Rezultatul actual: `AUTOFIX_ORACLE_PILOT_RESULT.md`.

# Rezultatul pilotului Oracle — 28 noiembrie 2026

**Rezultat parțial verificat:** proba nativă Python a trecut pe VM Oracle ARM64;
proba WordPress/PHP completă este blocată de dependențele inexistente. Nu sunt
același lucru și nu declarăm validarea WordPress pe host drept finalizată.

Dovadă directă:
https://github.com/Ciobanu87/filip-guard/actions/runs/46130410616
Job `pilot`, ID `140934067184`, încheiat cu succes. Raportul nativ a fost emis
la 28 noiembrie 2026, 11:25 EET (09:25 UTC).

## Alocare și capacitate verificate înaintea execuției

Prin SSH cu verificarea amprentei existente și prin metadata locală OCI:

- Frankfurt, `VM.Standard.A1.Flex`, 1 OCPU, 6 GB RAM; dispozitive block vizibile
  însumând 47 GiB. Nicio alocare, redimensionare sau resursă cloud nouă.
- 4.734 MiB RAM disponibili și 20.123.926.528 octeți liberi la admitere.
- Cele patru unități UI/worker/backup/timer inactive înainte și nemodificate după.
- Python existent disponibil; PHP/mysqli, server SQL și inițializator SQL nu au
  fost identificate în PATH, prefixele standard/libexec și listele RPM verificate.
  Docker și Podman nu au fost identificate. Nu s-a instalat niciun pachet.

Sursa Oracle consultată la data execuției:
https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
Limitele curente folosite: 1.500 OCPU-ore, 9.000 GB-ore RAM lunar și 200 GB total
boot/block în home region. Pentru configurația unică declarată de proprietar,
chiar 31 de zile înseamnă maximum 744 OCPU-ore și 4.464 GB-ore RAM; volumul rămâne
47 GB. Utilizarea CPU în pilot nu schimbă alocarea instanței existente.

Aceasta este verificarea încadrării alocării, folosind și dovezile deja confirmate
de proprietar: cont fără upgrade, singura VM/volum, consum și overage zero. Nu a
fost interogată facturarea live și nu afirmăm că SSH poate verifica întregul cont.
Pilotul nu a creat resurse sau trafic către furnizorii interziși.

## Ce a rulat efectiv pe Oracle

Candidat exact: `ee593326f89b5db8a1f0700c6a9f18424a36e0e6`; arhiva a fost verificată
cu SHA-256 din plan înaintea extragerii. Copia s-a aflat numai într-un director
privat temporar, nu în aplicația instalată. Runtime-ul Python existent a fost
folosit fără modificarea lui, sub utilizatorul existent `nobody`, diferit de
utilizatorul aplicației. Testul a confirmat că starea aplicației nu era inscriptibilă
de către copil. Spațiul de nume de rețea a fost separat și verificat din copil;
mediul nu a primit credențiale reale sau căi către starea/cheile aplicației.

Au trecut **19 teste**, zero erori, zero eșecuri și zero teste omise:

| Grup existent executat pe host | Teste | Acoperire |
| --- | ---: | --- |
| `test_autofix_failure_boundaries` | 7 | concurență, backup înainte de scriere, întreruperi simulate, expirare și confirmări invalide |
| `test_autofix_recovery_review` | 3 | observații de recuperare fără deblocarea reîncercării, sesiune nouă și izolare |
| `test_recovery_state_integration` | 2 | recuperare criptată cu cod de cont netrimis și jurnal AutoFix blocat; permisiuni/legături refuzate |
| `test_wordpress_production.ProductionFlowTests` | 7 | diagnostic/aprobare/backup/verificare/restore și rollback pe backend WordPress **simulat** |

Durata măsurată: **7,14 secunde**. Maximul observat al fișierelor private ale
pilotului: **1.932.374 octeți**. Copilul a avut limite explicite de CPU, fișier,
core dump și memorie virtuală; nu pretindem o măsurare a vârfului RSS agregat.
Întreruperile au fost simulate în fixture și urmate de redeschiderea motorului/
stării; nu a fost oprit, repornit sau întrerupt serviciul real al aplicației.

Backupul a folosit criptarea reală și verificarea readback/restaurare, dar stocarea
externă a fost fixture-ul în memorie. **Nu este o nouă probă B2 reală** și nu este
backup complet al unui WordPress de client. Nicio cheie master reală nu a fost
folosită, înlocuită sau exportată.

Raportul confirmă: fișiere temporare șterse, stări unități nemodificate, zero
instalări globale, zero listener public creat, zero Groq/SMTP/B2 și nicio activare
AutoFix în aplicația reală. Kernel namespace-ul și contul de test au fost temporare;
nu s-au modificat firewallul, unitățile sau configurația aplicației existente.

## Verificarea executorului și a codului din repository

https://github.com/Ciobanu87/filip-guard/actions/runs/46130410599
Toate cele cinci joburi au trecut: **944 + 24 + 8 = 976 teste**. Cele 19 teste ale
pilotului sunt reluate pe un alt mediu, nu 19 teste unice adăugate la acest total.
Sunt nouă teste noi pentru admiterea/izolarea executorului; funcționalitățile
produsului și candidatul aplicației nu au fost schimbate.

Commituri operaționale:

- `967a18795b991b9d77179db476d71ae14936a196`: admiterea read-only autorizată.
- `de1f92133faf4d41d84e24debb313caa2037d88d`: verificarea dependențelor și în afara PATH.
- `8d01a85226c093d273ab2c0dd309610ca8af404f`: execuția subsetului nativ izolat.

## Blocajul rămas în limitele aprobate

Pentru testul WordPress/PHP pe Oracle lipsesc PHP 8.3 cu mysqli și un runtime SQL
compatibil cu inițializare privată. Nu ocolim lipsa lor, nu instalăm global și nu
folosim un SQL partajat. Instalarea de dependențe noi nu este permisă de aprobarea
actuală. Continuarea acelei probe cere fie un runtime compatibil deja disponibil,
fie o aprobare distinctă pentru instalare gratuită, cu lista și metoda revizuite
înainte de execuție. Nu a fost solicitată vreo autentificare nouă sau cheie nouă.

`main` a rămas la `763b71a5edee2324cfcbc4739138b4d48fd53e1c`; serviciile de producție
rămân oprite. Nici această probă nativă, nici CI nu sunt folosite pentru a genera
un receipt de compatibilitate reală sau o politică de activare pentru un client.
