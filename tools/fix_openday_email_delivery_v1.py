from pathlib import Path

p = Path('index.html')
html = p.read_text(encoding='utf-8')

replacements = []

def replace_once(old, new, label):
    global html
    if old not in html:
        raise SystemExit(f'Blocco non trovato: {label}')
    html = html.replace(old, new, 1)
    replacements.append(label)

replace_once(
'''      flushNow() {
        this.log("Esecuzione forzata manuale...");
        this.processQueues();
      },''',
'''      async flushNow() {
        this.log("Esecuzione forzata manuale...");
        return this.processQueues();
      },''',
'flushNow awaitable')

replace_once(
'''      async processQueues() {
        if (this.isProcessing) return;
        this.isProcessing = true;

        const today = new Date().toLocaleDateString('it-IT');''',
'''      async processQueues() {
        if (this.isProcessing) return;
        this.isProcessing = true;

        // Ricarica sempre la coda direttamente da Firestore prima di elaborarla.
        // Evita che una prenotazione appena salvata resti bloccata in IN_CODA
        // perché il listener realtime non ha ancora aggiornato state.registrations.
        try {
          const latestSnap = await getDocs(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'));
          const latestRegistrations = [];
          latestSnap.forEach(d => latestRegistrations.push({ id: d.id, ...d.data() }));
          state.registrations = latestRegistrations;
        } catch (e) {
          this.log("Aggiornamento coda da Firebase non riuscito: uso lo snapshot locale.", "warning");
        }

        const today = new Date().toLocaleDateString('it-IT');''',
'fresh Firestore queue')

replace_once(
'''          fetch(item.url, { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(payload) })
            .catch(e => { });
          
          await updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', item.reg.code), { [fieldMap[item.type]]: new Date().toLocaleString('it-IT') });''',
'''          // Attende almeno il completamento della richiesta HTTP del browser.
          // Con no-cors la risposta Google resta opaca, ma un errore di rete non viene più ignorato.
          await window.inviaEmailScript(item.url, payload);
          
          await updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', item.reg.code), { [fieldMap[item.type]]: new Date().toLocaleString('it-IT') });''',
'dispatch waits fetch')

replace_once(
'''    async function inviaEmailScript(url, payload) {
      try {
        await fetch(url, { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(payload) });
      } catch (err) { console.error("Errore fetch sincrono:", err); }
    }''',
'''    async function inviaEmailScript(url, payload) {
      // Compatibilità con gli Apps Script storici: alcuni leggono code/dateStr/studyPath,
      // altri codice_prenotazione/data/attivita.
      const normalizedPayload = { ...(payload || {}) };
      if (!normalizedPayload.codice_prenotazione && normalizedPayload.code) normalizedPayload.codice_prenotazione = normalizedPayload.code;
      if (!normalizedPayload.data && normalizedPayload.dateStr) normalizedPayload.data = normalizedPayload.dateStr;
      if (!normalizedPayload.attivita && normalizedPayload.studyPath) normalizedPayload.attivita = `Open Day - ${normalizedPayload.studyPath}`;
      return fetch(url, {
        method: 'POST',
        mode: 'no-cors',
        headers: { 'Content-Type': 'text/plain;charset=utf-8' },
        body: JSON.stringify(normalizedPayload)
      });
    }''',
'payload compatibility and propagated errors')

replace_once(
'''        if (shouldWait) { const position = queue.length + 1; await sendOpenDayWaitlistEmail(regData, position); showToast(`Richiesta registrata con riserva. Posizione indicativa: ${position}.`, 'info'); } else window.SmartEmailEngine.flushNow();''',
'''        if (shouldWait) { const position = queue.length + 1; await sendOpenDayWaitlistEmail(regData, position); showToast(`Richiesta registrata con riserva. Posizione indicativa: ${position}.`, 'info'); } else await window.SmartEmailEngine.flushNow();''',
'booking waits queue flush')

replace_once(
'''        else if (q3.length > 0 && availableQuota > this.safeLimit) {''',
'''        else if (q3.length > 0 && availableQuota > 0) {''',
'Q3 no artificial 90-message reserve')

# Rende deterministici anche i comandi manuali di accodamento, già dentro funzioni async.
replace_once(
'''      showToast("Email accodata. Verrà gestita dal Motore AI in background.", "info");
      window.SmartEmailEngine.flushNow();
    }
    window.triggerEmailQueue = triggerEmailQueue;''',
'''      showToast("Email accodata. Invio in elaborazione...", "info");
      await window.SmartEmailEngine.flushNow();
    }
    window.triggerEmailQueue = triggerEmailQueue;''',
'manual queue awaits flush')

# Controlli statici forti.
checks = [
    'async flushNow()',
    "const latestSnap = await getDocs(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'))",
    'await window.inviaEmailScript(item.url, payload);',
    'normalizedPayload.codice_prenotazione',
    'normalizedPayload.data',
    'normalizedPayload.attivita',
    'else await window.SmartEmailEngine.flushNow();',
    'else if (q3.length > 0 && availableQuota > 0)',
    'Email accodata. Invio in elaborazione...'
]
for c in checks:
    assert c in html, c

p.write_text(html, encoding='utf-8')
print('OPENDAY_EMAIL_PATCH_OK:', ', '.join(replacements))
