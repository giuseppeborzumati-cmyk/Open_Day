from pathlib import Path

p = Path('index.html')
s = p.read_text(encoding='utf-8')

CONFIRM = 'AKfycbx934SuTzxYNzb82Tn9_kwPfTbAQFBQv5kGoqtIBP1GAlPdnICUAG2tFSYAnKhmf1P6Ow'
CANCEL = 'AKfycbx2BNhnVfV2Mu0YMjHy-wcagr5-_nHui8nZqMLZXfjPD1iEsKRKSX4k6URFD1t_kmq_Jw'
INGRESSO = 'AKfycbyW546zDa6kAI5cAaJkL-se9ngljm4c3UhlFuMxMPMmNVO-f5QsdUCqeotfJe0aFy7MBA'
USCITA = 'AKfycbz8MnsiM0QnbbkMqiSFCOVMpbFQamKaSy8lm7E-LdyeuOIEbmA_BqRINa4Pt7Nq7HFt'

for token in (CONFIRM, CANCEL, INGRESSO, USCITA):
    assert token in s, f'URL atteso non trovato: {token}'


def rep(old, new, label):
    global s
    if old not in s:
        raise SystemExit(f'Pattern non trovato: {label}')
    s = s.replace(old, new, 1)

marker = "    // --- MOTORE INTELLIGENTE EMAIL (SMART QUEUE ENGINE) ---\n    const SmartEmailEngine = {"
helpers = r'''    // --- MOTORE INTELLIGENTE EMAIL (SMART QUEUE ENGINE) ---
    // Ogni browser puo vedere la stessa coda: una lease Firestore per singola e-mail
    // evita doppi invii quando piu dispositivi sono aperti contemporaneamente.
    const EMAIL_ENGINE_OWNER = `MAIL-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    async function acquireOpenDayEmailDeliveryLease(code, type) {
      const safeId = `${String(code || '').replace(/[^A-Za-z0-9_-]/g, '_')}_${String(type || 'mail')}`;
      const ref = doc(db, 'artifacts', appId, 'public', 'data', 'email_delivery_locks', safeId);
      try {
        return await runTransaction(db, async tx => {
          const snap = await tx.get(ref);
          const now = Date.now();
          const old = snap.exists() ? snap.data() : {};
          if (Number(old.lockedUntil || 0) > now && old.owner !== EMAIL_ENGINE_OWNER) return false;
          tx.set(ref, { owner: EMAIL_ENGINE_OWNER, code, type, lockedAt: now, lockedUntil: now + 60000 }, { merge: true });
          return true;
        });
      } catch (e) {
        console.warn('OpenDay email lease non acquisita', e);
        return false;
      }
    }

    function parseOpenDayLocalDate(dateStr, timeStr = '00:00') {
      const [y, m, d] = String(dateStr || '').split('-').map(Number);
      const [hh, mm] = String(timeStr || '00:00').trim().split(':').map(Number);
      if (![y, m, d, hh, mm].every(Number.isFinite)) return null;
      return new Date(y, m - 1, d, hh, mm, 0, 0);
    }

    function openDayEventEndPlusFive(reg) {
      const slot = state.dates.find(d => d.id === reg.dateId);
      if (!slot?.date || !slot?.timeSlot) return null;
      let endTime = String(slot.timeSlot).includes('-') ? String(slot.timeSlot).split('-')[1].trim() : String(slot.timeSlot).trim();
      const end = parseOpenDayLocalDate(slot.date, endTime);
      if (!end) return null;
      end.setMinutes(end.getMinutes() + 5);
      return end.getTime();
    }

    async function reconcileScheduledOpenDayEmails() {
      const now = Date.now();
      const reminderDays = Math.max(0, Number(window.promemoriaDays ?? 7) || 7);
      const writes = [];

      for (const reg of state.registrations) {
        if (isWaitlistRegistration(reg)) continue;
        const slot = state.dates.find(d => d.id === reg.dateId);
        if (!slot) continue;

        if (!reg.promemoriaSentDate && slot.date) {
          const startTime = String(slot.timeSlot || '00:00').includes('-') ? String(slot.timeSlot).split('-')[0].trim() : String(slot.timeSlot || '00:00').trim();
          const start = parseOpenDayLocalDate(slot.date, startTime);
          if (start) {
            const diffDays = Math.ceil((start.getTime() - now) / 86400000);
            if (diffDays >= 0 && diffDays <= reminderDays) {
              reg.promemoriaSentDate = 'IN_CODA_Q2';
              writes.push(updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', reg.code), { promemoriaSentDate: 'IN_CODA_Q2' }));
            }
          }
        }

        if (reg.status === 'Ammesso' && !reg.pergamenaSentDate) {
          const dueAt = openDayEventEndPlusFive(reg);
          if (dueAt && now >= dueAt) {
            reg.status = 'Concluso';
            reg.pergamenaSentDate = 'IN_CODA_Q3';
            reg.pergamenaDueAt = dueAt;
            writes.push(updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', reg.code), {
              status: 'Concluso',
              pergamenaSentDate: 'IN_CODA_Q3',
              pergamenaDueAt: dueAt,
              concludedAt: now
            }));
          }
        }
      }

      if (writes.length) await Promise.allSettled(writes);
    }
    window.reconcileScheduledOpenDayEmails = reconcileScheduledOpenDayEmails;

    const SmartEmailEngine = {'''
rep(marker, helpers, 'helper motore email')

rep(
'''      start() {
        if(this.timerId) clearInterval(this.timerId);
        this.log("Motore E-mail Avviato. In attesa di elaborare le code...");
        this.timerId = setInterval(() => this.processQueues(), this.intervalMs);
        this.updateDashboard();
      },''',
'''      start() {
        if(this.timerId) clearInterval(this.timerId);
        this.log("Motore E-mail Avviato. Controllo continuo delle code attivo...");
        this.processQueues().catch(e => this.log(`Errore ciclo iniziale: ${e.message || e}`, "error"));
        this.timerId = setInterval(() => {
          this.processQueues().catch(e => this.log(`Errore ciclo automatico: ${e.message || e}`, "error"));
        }, this.intervalMs);
        this.updateDashboard();
      },''',
'avvio continuo motore')

rep(
'''        } catch (e) {
          this.log("Aggiornamento coda da Firebase non riuscito: uso lo snapshot locale.", "warning");
        }

        const today = new Date().toLocaleDateString('it-IT');''',
'''        } catch (e) {
          this.log("Aggiornamento coda da Firebase non riuscito: uso lo snapshot locale.", "warning");
        }

        // Accoda automaticamente i promemoria dovuti e chiude gli eventi 5 minuti
        // dopo la fine, anche se il timeout originario della pagina e stato perso.
        await reconcileScheduledOpenDayEmails();

        const today = new Date().toLocaleDateString('it-IT');''',
'riconciliazione code pianificate')

rep("else if (q2.length > 0 && availableQuota > this.reserveQ1) {", "else if (q2.length > 0 && availableQuota > 0) {", 'priorita promemoria')

rep(
'''        try {
          this.log(`Invio [${item.type.toUpperCase()}] per ${item.reg.code} -> ${item.reg.email}...`);
          
          await updateDoc''',
'''        try {
          const leaseOk = await acquireOpenDayEmailDeliveryLease(item.reg.code, item.type);
          if (!leaseOk) {
            this.log(`Invio [${item.type.toUpperCase()}] ${item.reg.code} gia preso in carico da un altro dispositivo.`, "warning");
            return;
          }
          this.log(`Invio [${item.type.toUpperCase()}] per ${item.reg.code} -> ${item.reg.email}...`);
          
          await updateDoc''',
'lease singolo invio')

rep(
'''    function logoutAdmin() { state.isAdminAuthed = false; window.SmartEmailEngine.stop(); window.navigateTo('home'); showToast("Uscita effettuata.", "info"); }''',
'''    function logoutAdmin() { state.isAdminAuthed = false; window.navigateTo('home'); showToast("Uscita effettuata. Il motore e-mail resta attivo in sicurezza.", "info"); }''',
'logout non ferma mail')

rep(
'''      onAuthStateChanged(auth, u => { state.user = u; if(u) setupRealtimeListeners(); });''',
'''      onAuthStateChanged(auth, u => {
        state.user = u;
        if(u) {
          setupRealtimeListeners();
          // Il motore non dipende piu dall'apertura dell'area Docenti.
          window.SmartEmailEngine.start();
        }
      });''',
'avvio globale dopo auth')

rep(
'''    async function savePromemoriaSettings() {
      await setDoc(doc(db, 'artifacts', appId, 'public', 'data', 'settings', 'promemoria'), { days: parseInt(document.getElementById('settingsPromemoriaDays').value || 7) });
      showToast("Impostazioni salvate!", "success");
    }''',
'''    async function savePromemoriaSettings() {
      const days = parseInt(document.getElementById('settingsPromemoriaDays').value || 7);
      await setDoc(doc(db, 'artifacts', appId, 'public', 'data', 'settings', 'promemoria'), { days });
      window.promemoriaDays = days;
      await window.reconcileScheduledOpenDayEmails();
      await window.SmartEmailEngine.flushNow();
      showToast("Impostazioni salvate e coda promemoria verificata!", "success");
    }''',
'salvataggio promemoria immediato')

old_check = '''    function checkAndSendPromemoria() {
      if(!window.promemoriaDays) return;
      const today = new Date();
      state.registrations.forEach(reg => {
         if (isWaitlistRegistration(reg)) return;
         const targetDate = state.dates.find(d => d.id === reg.dateId)?.date;
         if(!targetDate || reg.promemoriaSentDate) return; 
         
         const eventDate = new Date(targetDate);
         const diffTime = Math.abs(eventDate - today);
         const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
         
         if(diffDays <= window.promemoriaDays && eventDate >= today) {
            updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', reg.code), { promemoriaSentDate: 'IN_CODA_Q2' });
         }
      });
      window.SmartEmailEngine.flushNow();
    }'''
new_check = '''    async function checkAndSendPromemoria() {
      await window.reconcileScheduledOpenDayEmails();
      await window.SmartEmailEngine.flushNow();
    }'''
rep(old_check, new_check, 'check promemoria')

rep("              let delayMs = 7 * 60 * 1000; ", "              let delayMs = 5 * 60 * 1000; ", 'fallback pergamena 5 minuti')
rep("endDateTime.setHours(parseInt(timeParts[0], 10), parseInt(timeParts[1], 10) + 7, 0, 0);", "endDateTime.setHours(parseInt(timeParts[0], 10), parseInt(timeParts[1], 10) + 5, 0, 0);", 'fine evento +5')

rep(
'''              updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', qrData), { status: 'Ammesso', presenzaSentDate: 'IN_CODA_Q3' });''',
'''              updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', qrData), { status: 'Ammesso', presenzaSentDate: 'IN_CODA_Q3' })
                .then(() => window.SmartEmailEngine.flushNow())
                .catch(e => console.error("Accodamento attestato ingresso non riuscito", e));''',
'invio ingresso immediato')

# Integrita: gli URL richiesti dall'utente devono restare identici.
for token in (CONFIRM, CANCEL, INGRESSO, USCITA):
    assert token in s, f'URL alterato: {token}'
assert 'let delayMs = 5 * 60 * 1000' in s
assert '+ 5, 0, 0' in s
assert 'acquireOpenDayEmailDeliveryLease' in s
assert 'window.SmartEmailEngine.start();' in s
assert 'availableQuota > this.reserveQ1' not in s
assert 'window.SmartEmailEngine.stop(); window.navigateTo' not in s

p.write_text(s, encoding='utf-8')
print('OPENDAY_EMAIL_RUNTIME_V2_OK')
