from pathlib import Path
import re

p = Path('index.html')
html = p.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global html
    count = html.count(old)
    if count != 1:
        raise SystemExit(f'{label}: atteso 1 match, trovati {count}')
    html = html.replace(old, new, 1)


def sub_once(pattern, repl, label):
    global html
    html2, count = re.subn(pattern, repl, html, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: atteso 1 match, trovati {count}')
    html = html2

# 1) Conteggio posti robusto + piano cronologico compatibile con la capienza.
old_helpers = """    const activeRegistrationsFor = (dateId, source = state.registrations) => source
      .filter(r => r.dateId === dateId && !isWaitlistRegistration(r));
    const seatsOf = (r) => Math.max(1, Number(r?.totalPeople || 1) || 1);
    const activeSeatsFor = (dateId, source = state.registrations) => activeRegistrationsFor(dateId, source)
      .reduce((sum, r) => sum + seatsOf(r), 0);
"""
new_helpers = """    const isSeatActiveRegistration = (r) => {
      if (!r || isWaitlistRegistration(r)) return false;
      if (String(r.type || '').toLowerCase() === 'cancellazione') return false;
      if (normalizeWaitlistText(r.status) === 'annullato') return false;
      return true;
    };
    const activeRegistrationsFor = (dateId, source = state.registrations) => source
      .filter(r => r.dateId === dateId && isSeatActiveRegistration(r));
    const seatsOf = (r) => Math.max(1, Number(r?.totalPeople || 1) || 1);
    const activeSeatsFor = (dateId, source = state.registrations) => activeRegistrationsFor(dateId, source)
      .reduce((sum, r) => sum + seatsOf(r), 0);
    const waitlistFitPlan = (dateId, availableSeats, source = state.registrations) => {
      let remaining = Math.max(0, Number(availableSeats || 0));
      const selected = [];
      const waiting = [];
      for (const reg of waitlistQueueFor(dateId, source)) {
        const needed = seatsOf(reg);
        if (needed <= remaining) {
          selected.push(reg);
          remaining -= needed;
        } else {
          waiting.push(reg);
        }
      }
      return { selected, waiting, remaining };
    };
"""
replace_once(old_helpers, new_helpers, 'helpers capienza')

# 2) Testo ricevuta lista d'attesa coerente con gruppi di dimensione diversa.
replace_once(
    "La lista segue rigorosamente l’ordine cronologico. Se si libera capienza, il sistema ammette automaticamente il primo gruppo utile in coda. La presente ricevuta non consente l’ingresso finché non arriva la conferma definitiva.",
    "La lista segue l’ordine cronologico compatibile con i posti realmente liberi. Se un gruppo richiede più posti di quelli disponibili resta in attesa; il sistema può ammettere la prima richiesta successiva che entra nella capienza, senza superare mai il limite del turno. La presente ricevuta non consente l’ingresso finché non arriva la conferma definitiva.",
    'testo PDF lista attesa'
)

# 3) Scorrimento: MAI oltre capienza; se il primo gruppo non entra, valuta in ordine i successivi compatibili.
new_promote = r'''    async function promoteOpenDayWaitlist(dateId) {
      if (!dateId) return false;
      const locked = await acquireOpenDayWaitlistLock(dateId);
      if (!locked) return false;
      const promoted = [];
      try {
        let slot = state.dates.find(d => d.id === dateId);
        const slotSnap = await getDoc(doc(db, 'artifacts', appId, 'public', 'data', 'dates', dateId));
        if (slotSnap.exists()) slot = { id: slotSnap.id, ...slotSnap.data() };
        if (!slot) return false;

        const snap = await getDocs(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'));
        const fresh = []; snap.forEach(d => fresh.push({ id: d.id, ...d.data() }));
        const maxSeats = Math.max(1, Number(slot.maxSeats || 1));
        let occupied = activeSeatsFor(dateId, fresh);
        let available = Math.max(0, maxSeats - occupied);
        const queue = waitlistQueueFor(dateId, fresh);
        const originalPosition = new Map(queue.map((r, i) => [r.code, i + 1]));

        for (const queued of queue) {
          if (available <= 0) break;
          const ref = doc(db, 'artifacts', appId, 'public', 'data', 'registrations', queued.code);
          const liveSnap = await getDoc(ref);
          if (!liveSnap.exists()) continue;
          const live = { id: liveSnap.id, ...liveSnap.data() };
          if (!isWaitlistRegistration(live) || live.dateId !== dateId) continue;

          const needed = seatsOf(live);
          if (needed > maxSeats || needed > available) continue;

          // Invariante assoluta: l'ammissione è possibile solo se i posti occupati
          // dopo la promozione restano <= capienza autorizzata del turno.
          if (occupied + needed > maxSeats) continue;

          const patch = {
            type: ACTIVE_TYPE,
            status: 'Iscritto',
            iscrizioneConRiserva: false,
            waitlistPromotedAt: Date.now(),
            waitlistPromotionStatus: 'Ammesso da scorrimento',
            waitlistPromotionSource: 'automatico_capienza_compatibile',
            waitlistPositionAtPromotion: originalPosition.get(live.code) || null,
            waitlistSeatsAtPromotion: needed,
            waitlistAvailableBeforePromotion: available
          };
          await updateDoc(ref, patch);
          promoted.push({ ...live, ...patch });
          occupied += needed;
          available = Math.max(0, maxSeats - occupied);
        }
      } finally {
        await releaseOpenDayWaitlistLock(dateId);
      }

      for (const reg of promoted) await sendOpenDayPromotionEmail(reg);
      if (promoted.length) {
        const people = promoted.reduce((sum, r) => sum + seatsOf(r), 0);
        window.showToast?.(`${promoted.length} richiesta/e (${people} persone) ammesse automaticamente senza superare la capienza.`, 'info');
      }
      return promoted.length > 0;
    }
    window.promoteOpenDayWaitlist = promoteOpenDayWaitlist;'''
sub_once(r"    async function promoteOpenDayWaitlist\(dateId\) \{.*?\n    \}\n    window\.promoteOpenDayWaitlist = promoteOpenDayWaitlist;", new_promote, 'promoteOpenDayWaitlist')

# 4) Home: mostra per ogni data/turno occupati, liberi e persone in attesa.
new_home = r'''    function renderHomeDates() {
      const container = document.getElementById('groupedDatesGrid');
      const filterVal = document.getElementById('userPathFilter')?.value || 'all';
      if(!container) return;
      const filteredDates = filterVal === 'all' ? state.dates : state.dates.filter(d => d.studyPath === filterVal);
      const groups = {};
      filteredDates.forEach(d => { if(!groups[d.date]) groups[d.date] = []; groups[d.date].push(d); });
      const sortedDates = Object.keys(groups).sort((a, b) => new Date(a) - new Date(b));
      container.innerHTML = sortedDates.map(dateVal => {
        const sessions = groups[dateVal].sort((a, b) => a.timeSlot === b.timeSlot ? a.studyPath.localeCompare(b.studyPath) : a.timeSlot.localeCompare(b.timeSlot));
        const slotsHtml = sessions.map(s => {
          const maxSeats = Math.max(1, Number(s.maxSeats || 1));
          const activeSeats = activeSeatsFor(s.id);
          const queue = waitlistQueueFor(s.id);
          const waitPeople = queue.reduce((sum, r) => sum + seatsOf(r), 0);
          const available = Math.max(0, maxSeats - activeSeats);
          const fitPlan = waitlistFitPlan(s.id, available);
          const fitPeople = fitPlan.selected.reduce((sum, r) => sum + seatsOf(r), 0);
          const mustWait = queue.length > 0 || available <= 0;
          let statusLabel = '';
          if (!queue.length && available > 0) statusLabel = `🔥 ${available} POSTI LIBERI`;
          else if (!queue.length) statusLabel = '⛔ POSTI ESAURITI';
          else if (available <= 0) statusLabel = `⏳ COMPLETO • CODA ${queue.length} RICH. / ${waitPeople} PERSONE`;
          else if (fitPlan.selected.length) statusLabel = `⏳ ${available} LIBERI • ${fitPlan.selected.length} RICH. COMPATIBILI (${fitPeople} POSTI)`;
          else statusLabel = `⏳ ${available} LIBERI • GRUPPI IN ATTESA NON COMPATIBILI`;
          const statusClass = mustWait ? 'text-violet-700 bg-violet-50 border-violet-200' : 'text-emerald-600 bg-emerald-50 border-emerald-200';
          return `
            <div class="p-4 bg-white/80 rounded-xl border border-slate-200 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 text-xs font-semibold shadow-sm transition hover:border-indigo-300">
              <div class="w-full sm:w-2/3">
                <span class="font-black text-slate-900 block text-[12px] sm:text-[13px] leading-tight mb-1 whitespace-normal">${s.studyPath}</span>
                <span class="inline-block text-[10px] text-indigo-700 font-bold bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-lg mb-1">Ore ${s.timeSlot} • Sede: ${s.aula}</span>
                <span class="block text-[10px] text-slate-600 font-black mt-1">Capienza turno: ${activeSeats}/${maxSeats} occupati • ${available} liberi${queue.length ? ` • Lista d'attesa: ${queue.length} richieste / ${waitPeople} persone` : ''}</span>
              </div>
              <div class="flex flex-col sm:items-end gap-2 w-full sm:w-auto">
                <span class="text-[9px] font-black border px-2 py-1.5 rounded-lg whitespace-normal text-center ${statusClass}">${statusLabel}</span>
                <button onclick="${mustWait ? `window.startWaitlistProcess('${s.id}')` : `window.startBookingProcess('${s.id}')`}" class="w-full sm:w-auto px-4 py-2.5 ${mustWait?'bg-violet-600 hover:bg-violet-500 text-white':'bg-indigo-600 hover:bg-indigo-500 text-white'} rounded-lg uppercase font-black text-[10px] shadow-sm transition tracking-wider flex items-center justify-center gap-1 shrink-0">${mustWait ? `LISTA D'ATTESA${queue.length ? ` (${queue.length})` : ''}` : 'ISCRIVITI <i data-lucide="arrow-right" class="w-3 h-3"></i>'}</button>
              </div>
            </div>`;
        }).join('');
        return `<div class="glass-card p-5 rounded-3xl border space-y-4 shadow-sm hover:shadow-md transition"><h4 class="text-lg font-black text-indigo-950 font-outfit uppercase border-b border-slate-200 pb-2">${new Date(dateVal).toLocaleDateString('it-IT', {weekday:'long', day:'numeric', month:'long', year:'numeric'})}</h4><div class="space-y-3">${slotsHtml}</div></div>`;
      }).join('');
      try { lucide.createIcons(); } catch(e){}
    }
    window.renderHomeDates = renderHomeDates;'''
sub_once(r"    function renderHomeDates\(\) \{.*?\n    \}\n    window\.renderHomeDates = renderHomeDates;", new_home, 'renderHomeDates')

# 5) Nuova prenotazione: usa la capienza live sotto lo stesso lock e rifiuta gruppi più grandi dell'intero turno.
old_capacity_submit = """        const activeSeats = activeSeatsFor(dateId, fresh);
        const queue = waitlistQueueFor(dateId, fresh);
        const maxSeats = Math.max(1, Number(targetSession.maxSeats || 1));
        const shouldWait = openDayWaitlistMode || queue.length > 0 || (activeSeats + totalPeople > maxSeats);
"""
new_capacity_submit = """        const liveDateSnap = await getDoc(doc(db, 'artifacts', appId, 'public', 'data', 'dates', dateId));
        const liveSession = liveDateSnap.exists() ? { ...targetSession, ...liveDateSnap.data(), id: dateId } : targetSession;
        const maxSeats = Math.max(1, Number(liveSession.maxSeats || 1));
        if (!Number.isFinite(totalPeople) || totalPeople < 1) throw new Error('INVALID_GROUP_SIZE');
        if (totalPeople > maxSeats) throw new Error('GROUP_EXCEEDS_CAPACITY');
        const activeSeats = activeSeatsFor(dateId, fresh);
        const queue = waitlistQueueFor(dateId, fresh);
        const shouldWait = openDayWaitlistMode || queue.length > 0 || (activeSeats + totalPeople > maxSeats);
"""
replace_once(old_capacity_submit, new_capacity_submit, 'capienza live prenotazione')

old_catch = """if (err.message === 'DUPLICATE') showToast(\"Esiste già una richiesta per questo studente nello stesso turno.\", \"error\"); else if (err.message === 'LICEO_PREFERENCE_REQUIRED') showToast(\"Seleziona l'indirizzo liceale: Scienze Applicate oppure Curvatura Economica.\", \"error\"); else showToast(\"Errore durante il salvataggio. Riprova.\", \"error\");"""
new_catch = """if (err.message === 'DUPLICATE') showToast(\"Esiste già una richiesta per questo studente nello stesso turno.\", \"error\"); else if (err.message === 'LICEO_PREFERENCE_REQUIRED') showToast(\"Seleziona l'indirizzo liceale: Scienze Applicate oppure Curvatura Economica.\", \"error\"); else if (err.message === 'GROUP_EXCEEDS_CAPACITY') showToast(\"Il numero di persone richiesto supera la capienza massima autorizzata per questo turno. Riduci il numero di posti.\", \"error\"); else if (err.message === 'INVALID_GROUP_SIZE') showToast(\"Indica almeno una persona per la prenotazione.\", \"error\"); else showToast(\"Errore durante il salvataggio. Riprova.\", \"error\");"""
replace_once(old_catch, new_catch, 'messaggi capienza prenotazione')

# 6) Modifica iscrizione da area docenti: mai oltre capienza e riconcilia se si liberano posti.
new_edit_reg = r'''    async function saveEditReg(e) {
      e.preventDefault();
      const code = document.getElementById('editRegCode').value;
      const current = state.registrations.find(r => r.code === code);
      if (!current) return showToast("Iscrizione non trovata.", "error");
      const newSeats = parseInt(document.getElementById('editRegPosti').value);
      if (!Number.isFinite(newSeats) || newSeats < 1) return showToast("I posti devono essere almeno 1.", "error");
      const dateId = current.dateId;
      let locked = false;
      try {
        if (dateId) {
          locked = await acquireOpenDayWaitlistLock(dateId);
          if (!locked) throw new Error('LOCKED');
        }
        const freshSnap = await getDocs(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'));
        const fresh = []; freshSnap.forEach(d => fresh.push({ id: d.id, ...d.data() }));
        const liveCurrent = fresh.find(r => r.code === code) || current;
        if (dateId && !isWaitlistRegistration(liveCurrent)) {
          const dateSnap = await getDoc(doc(db, 'artifacts', appId, 'public', 'data', 'dates', dateId));
          const slot = dateSnap.exists() ? { id: dateSnap.id, ...dateSnap.data() } : state.dates.find(d => d.id === dateId);
          if (!slot) throw new Error('DATE_NOT_FOUND');
          const maxSeats = Math.max(1, Number(slot.maxSeats || 1));
          const otherSeats = activeSeatsFor(dateId, fresh.filter(r => r.code !== code));
          if (otherSeats + newSeats > maxSeats) throw new Error('CAPACITY_EXCEEDED');
        }
        await updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', code), {
          cognome: toTitleCase(document.getElementById('editRegCognome').value.trim()),
          nome: toTitleCase(document.getElementById('editRegNome').value.trim()),
          email: document.getElementById('editRegEmail').value.trim(),
          totalPeople: newSeats
        });
        showToast("Iscrizione modificata rispettando la capienza del turno!");
        window.closeModal('editRegModal');
      } catch(err) {
        if (err.message === 'CAPACITY_EXCEEDED') showToast("Modifica bloccata: con questi posti il turno supererebbe la capienza autorizzata.", "error");
        else if (err.message === 'LOCKED') showToast("Turno in aggiornamento. Riprova tra pochi secondi.", "warning");
        else showToast("Errore durante la modifica.", "error");
      } finally {
        if (locked) await releaseOpenDayWaitlistLock(dateId);
      }
      if (dateId) await promoteOpenDayWaitlist(dateId).catch(() => false);
    }
    window.saveEditReg = saveEditReg;'''
sub_once(r"    async function saveEditReg\(e\) \{.*?\n    \}\n    window\.saveEditReg = saveEditReg;", new_edit_reg, 'saveEditReg')

# 7) Modifica capienza turno: non può scendere sotto i posti già confermati; aumento = scorrimento immediato.
new_edit_date = r'''    async function saveEditDate(e) {
      e.preventDefault();
      const id = document.getElementById('editDateId').value;
      const newMaxSeats = parseInt(document.getElementById('editDateSeats').value);
      if (!Number.isFinite(newMaxSeats) || newMaxSeats < 1) return showToast("La capienza deve essere almeno 1.", "error");
      const locked = await acquireOpenDayWaitlistLock(id);
      if (!locked) return showToast("Turno in aggiornamento. Riprova tra pochi secondi.", "warning");
      try {
        const freshSnap = await getDocs(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'));
        const fresh = []; freshSnap.forEach(d => fresh.push({ id: d.id, ...d.data() }));
        const occupied = activeSeatsFor(id, fresh);
        if (newMaxSeats < occupied) throw new Error('CAPACITY_BELOW_OCCUPIED');
        await updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'dates', id), {
          date: document.getElementById('editDateValue').value,
          timeSlot: document.getElementById('editDateTime').value.trim(),
          aula: document.getElementById('editDateAula').value.trim(),
          maxSeats: newMaxSeats,
          studyPath: canonicalOpenDayStudyPath(document.getElementById('editDatePath').value)
        });
        showToast(`Turno aggiornato: ${occupied}/${newMaxSeats} posti già occupati.`);
        window.closeModal('editDateModal');
      } catch(err) {
        if (err.message === 'CAPACITY_BELOW_OCCUPIED') showToast("Capienza non valida: non puoi impostare meno posti di quelli già confermati.", "error");
        else showToast("Errore durante la modifica.", "error");
      } finally {
        await releaseOpenDayWaitlistLock(id);
      }
      await promoteOpenDayWaitlist(id).catch(() => false);
    }
    window.saveEditDate = saveEditDate;'''
sub_once(r"    async function saveEditDate\(e\) \{.*?\n    \}\n    window\.saveEditDate = saveEditDate;", new_edit_date, 'saveEditDate')

# 8) Tabella turni admin: mostra capienza reale e compatibilità della coda.
new_admin_dates = r'''    function renderAdminDatesList() {
      const tbody = document.getElementById('adminDatesTableBody');
      if(!tbody) return;
      const sortedDates = [...state.dates].sort((a, b) => new Date(a.date) - new Date(b.date) || a.timeSlot.localeCompare(b.timeSlot));
      tbody.innerHTML = sortedDates.map(d => {
        const maxSeats = Math.max(1, Number(d.maxSeats || 1));
        const booked = activeSeatsFor(d.id);
        const available = Math.max(0, maxSeats - booked);
        const waitQueue = waitlistQueueFor(d.id);
        const waitPeople = waitQueue.reduce((sum, r) => sum + seatsOf(r), 0);
        const fitPlan = waitlistFitPlan(d.id, available);
        const fitPeople = fitPlan.selected.reduce((sum, r) => sum + seatsOf(r), 0);
        return `
        <tr class="border-b hover:bg-slate-50 transition text-slate-700">
          <td class="p-3 font-bold">${new Date(d.date).toLocaleDateString('it-IT')}</td>
          <td class="p-3 font-mono font-bold">${d.timeSlot}</td>
          <td class="p-3 text-indigo-700 font-bold text-xs">${d.studyPath}</td>
          <td class="p-3 font-semibold">${d.aula}</td>
          <td class="p-3 text-center font-bold text-slate-900">
            <div>${booked} / ${maxSeats} occupati</div>
            <div class="mt-1 text-[9px] font-black ${available ? 'text-emerald-700' : 'text-rose-700'}">Liberi: ${available}</div>
            ${waitQueue.length ? `<div class="mt-1 text-[9px] font-black text-violet-700">Attesa: ${waitQueue.length} richieste / ${waitPeople} persone</div><div class="mt-1 text-[9px] font-black ${fitPlan.selected.length ? 'text-sky-700' : 'text-amber-700'}">${fitPlan.selected.length ? `Compatibili ora: ${fitPlan.selected.length} richieste / ${fitPeople} persone` : (available ? `Nessun gruppo in coda entra nei ${available} posti liberi` : 'Scorrimento fermo: turno completo')}</div>` : ``}
          </td>
          <td class="p-3 text-right">
            <div class="flex justify-end gap-2">
              <button onclick="window.openEditDateModal('${d.id}')" class="p-2.5 text-sky-600 bg-sky-50 hover:bg-sky-100 border border-transparent hover:border-sky-200 cursor-pointer"><i data-lucide="edit" class="w-4 h-4"></i></button>
              <button onclick="window.triggerDeleteTurno('${d.id}')" class="p-2.5 text-rose-500 bg-rose-50 hover:bg-rose-100 border border-transparent hover:border-rose-200 cursor-pointer"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
            </div>
          </td>
        </tr>
      `}).join('');
      lucide.createIcons();
    }
    window.renderAdminDatesList = renderAdminDatesList;'''
sub_once(r"    function renderAdminDatesList\(\) \{.*?\n    \}\n    window\.renderAdminDatesList = renderAdminDatesList;", new_admin_dates, 'renderAdminDatesList')

# 9) Testo pannello docenti: non promettere FIFO rigido quando la dimensione dei gruppi impedisce l'ammissione.
replace_once(
    "Ordine FIFO automatico: posizione calcolata per singolo turno. Nessun nominativo viene saltato.",
    "Ordine cronologico compatibile con la capienza: un gruppo viene ammesso solo se entra nei posti liberi. I gruppi troppo grandi restano in coda e non causano mai sovrannumero.",
    'testo pannello waitlist'
)

# Marker versione per audit rapido.
html = html.replace('// OPEN_DAY_WAITLIST_V1 - FIFO per turno con scorrimento automatico', '// OPEN_DAY_WAITLIST_V2 - capienza per persone, scorrimento cronologico compatibile e anti-overbooking', 1)

# Assert strutturali prima della scrittura.
required = [
    'OPEN_DAY_WAITLIST_V2',
    'waitlistFitPlan',
    "if (needed > maxSeats || needed > available) continue;",
    "if (occupied + needed > maxSeats) continue;",
    'GROUP_EXCEEDS_CAPACITY',
    'CAPACITY_EXCEEDED',
    'CAPACITY_BELOW_OCCUPIED',
    'Capienza turno:',
    'Nessun gruppo in coda entra nei',
    'automatico_capienza_compatibile'
]
for token in required:
    if token not in html:
        raise SystemExit(f'Assert fallita: {token}')

# Test logici puri dei casi richiesti.
def plan(available, groups):
    rem = available
    picked = []
    for idx, seats in enumerate(groups):
        if seats <= rem:
            picked.append((idx, seats))
            rem -= seats
    return picked, rem

cases = [
    (2, [3], [], 2),
    (2, [3,2], [(1,2)], 0),
    (2, [3,1,1], [(1,1),(2,1)], 0),
    (4, [5,4], [(1,4)], 0),
    (4, [2,3,2], [(0,2),(2,2)], 0),
    (5, [5], [(0,5)], 0),
    (5, [6,3,2], [(1,3),(2,2)], 0),
    (5, [4,3,2], [(0,4)], 1),
]
for available, groups, expected, expected_rem in cases:
    got, rem = plan(available, groups)
    assert got == expected, (available, groups, got, expected)
    assert rem == expected_rem, (available, groups, rem, expected_rem)
    assert sum(x[1] for x in got) <= available

p.write_text(html, encoding='utf-8')
print('OPEN_DAY_WAITLIST_CAPACITY_V2_OK')
