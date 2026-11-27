"""Build immutable self-contained owner-local tool; contains NO actual secret."""
import base64
import hashlib
from pathlib import Path

ROOT=Path(__file__).parent
CSS='body{font:17px system-ui;max-width:720px;margin:24px auto;padding:18px;background:#f5f7fb;color:#18243a}section{background:white;padding:20px;margin:18px 0;border:1px solid #cdd6e5;border-radius:12px}input,button{font:inherit;max-width:100%;box-sizing:border-box;margin:8px 0;padding:12px}input[type=password],input[type=text]{width:100%}button{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}label{display:block;margin:10px 0}small{display:block}'
UI=r'''
'use strict';
const byId=id=>document.getElementById(id);
function status(message){byId('status').textContent=message;}
byId('generate').addEventListener('click',()=>{byId('newSecret').value=FGOwnerCustody.generateSecret();status('Secret generat numai pe acest dispozitiv. Salveaza-l separat, apoi introdu-l prin SSH. Nu il trimite in chat.');});
byId('copySecret').addEventListener('click',async()=>{try{if(!byId('newSecret').value)throw Error();await navigator.clipboard.writeText(byId('newSecret').value);status('Secret copiat. Pastreaza-l separat intr-un loc privat controlat de tine.');}catch(error){status('Copierea automata nu este disponibila. Foloseste selectarea/copierea din camp pe dispozitivul tau.');}});
byId('showSecret').addEventListener('change',()=>{byId('newSecret').type=byId('showSecret').checked?'text':'password';});
byId('recover').addEventListener('click',async()=>{
 byId('proof').textContent='';byId('copyProof').disabled=true;
 if(!byId('savedBundle').checked||!byId('savedSecret').checked){status('Confirma mai intai pastrarea independenta a pachetului si secretului separat.');return;}
 const file=byId('bundle').files[0];if(!file||file.size>3800){status('Alege pachetul criptat de custodie, maximum 3800 bytes.');return;}
 const secret=byId('recoverySecret').value;byId('recoverySecret').value='';status('Verificare locala in curs. Nu se trimite nimic in retea.');
 try{const receipt=await FGOwnerCustody.recover(new Uint8Array(await file.arrayBuffer()),secret);
 byId('proof').textContent=receipt.recovery_proof;byId('copyProof').disabled=false;
 status('RECUPERARE LOCALA VERIFICATA. Cheia master nu este afisata. Copiaza codul de verificare si introdu-l in comanda SSH verify-owner.');
 }catch(error){status(error.message);}
});
byId('copyProof').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(byId('proof').textContent);status('Codul de verificare a fost copiat. Nu este cheia master.');}catch(error){status('Selecteaza si copiaza manual codul de verificare afisat.');}});
if(window.top!==window.self||!window.isSecureContext||!crypto.subtle){byId('generate').disabled=true;byId('recover').disabled=true;status('WebCrypto nu este disponibil. Deschide fisierul descarcat LOCAL intr-un browser actualizat; nu folosi previzualizarea ChatGPT sau browserul cloud.');}
'''

def digest(value):return base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()

def build():
    core=(ROOT/'owner_custody_core.js').read_text()
    csp="default-src 'none'; connect-src 'none'; script-src 'sha256-"+digest(core)+"' 'sha256-"+digest(UI)+"'; style-src 'sha256-"+digest(CSS)+"'; base-uri 'none'; form-action 'none'; object-src 'none'; frame-src 'none'"
    document='''<!doctype html><html lang="ro"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'''+csp+'''"><title>FILIP GUARD — custodie locala</title><style>'''+CSS+'''</style><body>
<h1>FILIP GUARD — custodie independenta</h1>
<p>Descarca acest fisier si deschide-l <strong>local pe telefonul tau</strong>. Nu il rula in previzualizarea ChatGPT sau in browserul cloud. Nu are conexiuni de retea si nu afiseaza cheia master.</p>
<section><h2>1. Secretul tau de recuperare</h2><p>Genereaza secretul pe acest dispozitiv si pastreaza-l separat de pachetul criptat, intr-un loc privat controlat de tine. Nu il trimite in conversatii sau capturi.</p>
<button id="generate" type="button">Genereaza secret local</button><input id="newSecret" type="password" readonly autocomplete="off" spellcheck="false" aria-label="Secret local generat"><label><input id="showSecret" type="checkbox">Afiseaza secretul numai pe dispozitivul meu</label><button id="copySecret" type="button">Copiaza secretul</button>
<p>In sesiunea SSH proprie, comanda pregatita este:</p><pre>sudo /usr/local/sbin/filip-guard-master-custody prepare</pre><small>Introdu secretul de doua ori la prompturile ascunse. Nu pune secretul in comanda. Serviciile raman oprite.</small></section>
<section><h2>2. Verifica recuperarea locala</h2><p>Dupa pregatirea pe Oracle, descarca pachetul de custodie strict criptat. Pastreaza-l independent de Oracle si de bucketul backupurilor. Pastreaza si o copie separata protejata a pachetului; secretul ramane separat.</p>
<label>Pachet criptat<input id="bundle" type="file" accept=".json,application/json"></label><label>Secret de recuperare<input id="recoverySecret" type="password" autocomplete="off" spellcheck="false"></label>
<label><input id="savedBundle" type="checkbox">Am pastrat pachetul criptat independent de server si de bucketul backupurilor.</label><label><input id="savedSecret" type="checkbox">Am pastrat secretul separat, sub controlul meu.</label>
<button id="recover" type="button">Verifica local cheia si backupul de test</button><pre id="proof"></pre><button id="copyProof" type="button" disabled>Copiaza codul de verificare</button>
<p>Confirma apoi in sesiunea SSH proprie:</p><pre>sudo /usr/local/sbin/filip-guard-master-custody verify-owner</pre><small>Introdu numai codul de verificare la promptul ascuns. Pana la confirmare, custodia ramane in asteptare; niciun serviciu nu se activeaza.</small></section>
<p id="status" role="status">Niciun secret nu a fost generat sau incarcat.</p>
<script>'''+core+'''</script><script>'''+UI+'''</script></body></html>'''
    path=ROOT/'owner-custody.html';path.write_text(document);return path

if __name__=='__main__':print(build())
