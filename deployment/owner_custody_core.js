'use strict';
// Local WebCrypto only. No fetch, storage, key display or raw-key export.
(function(root) {
const enc = new TextEncoder(), dec = new TextDecoder();
const MAGIC = enc.encode('FILIP-GUARD-APPLICATION-STATE-v1\0');
const hex = bytes => Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2,'0')).join('');
const sha = async bytes => hex(await crypto.subtle.digest('SHA-256', bytes));
function bytes64(value, max=8192) {
  if(typeof value!=='string'||value.length>max*2||value.length%4!==0||!/^[A-Za-z0-9+/]*={0,2}$/.test(value)) throw Error('Format criptat invalid');
  const raw=atob(value); if(raw.length>max)throw Error('Fisier prea mare');
  return Uint8Array.from(raw,c=>c.charCodeAt(0));
}
function exact(obj, keys) { if(!obj||Array.isArray(obj)||typeof obj!=='object'||Object.keys(obj).sort().join('|')!==keys.slice().sort().join('|'))throw Error('Structura invalida'); }
function concat(...parts) { const size=parts.reduce((n,p)=>n+p.length,0), out=new Uint8Array(size);let at=0;for(const p of parts){out.set(p,at);at+=p.length;}return out; }
function generateSecret() {
  const raw=crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...raw)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
async function recover(bundleBytes, secret) {
  let master;
  try {
    if(!(bundleBytes instanceof Uint8Array)||bundleBytes.length>3800||!/^[-_A-Za-z0-9]{43}$/.test(secret))throw Error('Intrare invalida');
    const bundle=JSON.parse(dec.decode(bundleBytes));
    exact(bundle,['format','envelope','application_state_check']);
    if(bundle.format!=='filip-guard-owner-custody-v1')throw Error('Versiune necunoscuta');
    const e=bundle.envelope;
    exact(e,['format','key_id','deployment_id','kdf','iterations','salt','nonce','ciphertext']);
    if(e.format!=='filip-guard-master-envelope-v1'||e.kdf!=='PBKDF2-SHA256'||e.iterations!==600000||!/^[0-9a-f]{32}$/.test(e.deployment_id)||!/^[A-Za-z0-9_-]{1,64}$/.test(e.key_id))throw Error('Parametri criptografici invalizi');
    const salt=bytes64(e.salt),nonce=bytes64(e.nonce),cipher=bytes64(e.ciphertext);
    if(salt.length!==16||nonce.length!==12||cipher.length!==48)throw Error('Lungime invalida');
    const password=await crypto.subtle.importKey('raw',enc.encode(secret),'PBKDF2',false,['deriveKey']);
    const wrapping=await crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt,iterations:600000},password,{name:'AES-GCM',length:256},false,['decrypt']);
    const aad=enc.encode('FILIP-GUARD/owner-master-custody/v1/'+e.key_id+'/'+e.deployment_id+'/PBKDF2-SHA256/600000');
    master=new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM',iv:nonce,additionalData:aad,tagLength:128},wrapping,cipher));
    if(master.length!==32)throw Error('Cheie invalida');
    const check=bundle.application_state_check;exact(check,['manifest','ciphertext']);const m=check.manifest;
    exact(m,['scope','deployment_id','key_id','object_id','ciphertext_sha256']);
    const objectPattern=new RegExp('^deployments/'+e.deployment_id+'/application-state-[0-9a-f]{32}\\.aesgcm$');
    if(m.scope!=='application_sqlite_state'||m.deployment_id!==e.deployment_id||m.key_id!==e.key_id||!objectPattern.test(m.object_id)||!/^[0-9a-f]{64}$/.test(m.ciphertext_sha256))throw Error('Manifest invalid');
    const sealed=bytes64(check.ciphertext);
    if(sealed.length<=MAGIC.length+28||await sha(sealed)!==m.ciphertext_sha256||!MAGIC.every((v,i)=>sealed[i]===v))throw Error('Backup corupt');
    const hkdf=await crypto.subtle.importKey('raw',master,'HKDF',false,['deriveKey']);
    const archiveKey=await crypto.subtle.deriveKey({name:'HKDF',hash:'SHA-256',salt:new Uint8Array(32),info:enc.encode('FILIP-GUARD/v1/application-state/'+e.deployment_id)},hkdf,{name:'AES-GCM',length:256},false,['decrypt']);
    const archiveAAD=concat(MAGIC,enc.encode(e.deployment_id+'/'+e.key_id));
    const plaintext=await crypto.subtle.decrypt({name:'AES-GCM',iv:sealed.slice(MAGIC.length,MAGIC.length+12),additionalData:archiveAAD,tagLength:128},archiveKey,sealed.slice(MAGIC.length+12));
    const archive=JSON.parse(dec.decode(plaintext));exact(archive,['version','directories','files']);
    if(archive.version!==1||!Array.isArray(archive.directories)||archive.directories.length!==0||!Array.isArray(archive.files)||archive.files.length!==1)throw Error('Backup de verificare invalid');
    const file=archive.files[0];exact(file,['path','data','sha256']);const data=bytes64(file.data);
    if(file.path!=='custody.sqlite'||data.length!==1024||await sha(data)!==file.sha256||dec.decode(data.slice(0,16))!=='SQLite format 3\0')throw Error('Recuperarea SQLite nu a fost verificata');
    const challenges=Array.from(dec.decode(data).matchAll(/FG-CUSTODY-CHALLENGE:([A-Za-z0-9_-]{43})/g));
    if(challenges.length!==1)throw Error('Dovada recuperarii lipseste');
    const bundleSHA=await sha(bundleBytes),digest=Uint8Array.from(bundleSHA.match(/../g),s=>parseInt(s,16));
    const proofKey=await crypto.subtle.importKey('raw',master,{name:'HMAC',hash:'SHA-256'},false,['sign']);
    const proof=hex(await crypto.subtle.sign('HMAC',proofKey,concat(enc.encode('FG-OWNER-CUSTODY-PROOF/v1\0'),digest,enc.encode(challenges[0][1]))));
    return {format:'filip-guard-owner-custody-proof-v1',bundle_sha256:bundleSHA,recovery_proof:proof,
            offline_application_backup_recovery_verified:true};
  } catch(error) { throw Error('Recuperare neverificata: secret gresit, fisier modificat sau format incompatibil. Nu introduce cheia master manual.'); }
  finally { if(master)master.fill(0);secret=null; }
}
root.FGOwnerCustody=Object.freeze({generateSecret,recover});
})(globalThis);
