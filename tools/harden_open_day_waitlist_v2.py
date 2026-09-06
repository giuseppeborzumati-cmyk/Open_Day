from pathlib import Path
import re

p = Path('index.html')
h = p.read_text(encoding='utf-8')

if "OPEN_DAY_WAITLIST_V1" not in h:
    raise SystemExit('Meccanismo lista attesa non trovato')

# 1) Denominazione corretta e uniforme del percorso liceale.
h = h.replace('Curvatura Economia', 'Curvatura Economica')

# 2) Normalizza anche i dati gia presenti in Firebase senza modificarli in modo distruttivo.
marker = "    let openDayWaitlistReconcileTimer = null;\n"
helper = """    function canonicalOpenDayStudyPath(value) {\n      return String(value || '').replace(/Curvatura Economia/g, 'Curvatura Economica');\n    }\n"""
if 'function canonicalOpenDayStudyPath' not in h:
    if marker not in h:
        raise SystemExit('Punto inserimento normalizzatore non trovato')
    h = h.replace(marker, marker + helper, 1)

old_dates = "s.forEach(d => state.dates.push({id: d.id, ...d.data()}));"
new_dates = "s.forEach(d => { const raw = {id: d.id, ...d.data()}; state.dates.push({...raw, studyPath: canonicalOpenDayStudyPath(raw.studyPath)}); });"
if old_dates in h:
    h = h.replace(old_dates, new_dates, 1)

old_regs = "s.forEach(d => state.registrations.push({id: d.id, ...d.data()}));"
new_regs = "s.forEach(d => { const raw = {id: d.id, ...d.data()}; state.registrations.push({...raw, studyPath: canonicalOpenDayStudyPath(raw.studyPath)}); });"
if old_regs in h:
    h = h.replace(old_regs, new_regs, 1)

h = h.replace(
    "studyPath: document.getElementById('newTurnoPath').value",
    "studyPath: canonicalOpenDayStudyPath(document.getElementById('newTurnoPath').value)"
)
h = h.replace(
    "studyPath: document.getElementById('editDatePath').value",
    "studyPath: canonicalOpenDayStudyPath(document.getElementById('editDatePath').value)"
)

# 3) La capienza docenti conta solo le prenotazioni confermate, non la lista d'attesa.
old_booked = "const booked = state.registrations.filter(r => r.dateId === d.id).reduce((sum, r) => sum + parseInt(r.totalPeople||1), 0);"
new_booked = "const booked = activeSeatsFor(d.id);\n        const waitQueue = waitlistQueueFor(d.id);\n        const waitPeople = waitQueue.reduce((sum, r) => sum + seatsOf(r), 0);"
if old_booked not in h:
    raise SystemExit('Conteggio capienza docenti non trovato')
h = h.replace(old_booked, new_booked, 1)

old_cell = '<td class="p-3 text-center font-bold text-slate-900">${booked} / ${d.maxSeats}</td>'
new_cell = '<td class="p-3 text-center font-bold text-slate-900"><div>${booked} / ${d.maxSeats}</div>${waitQueue.length ? `<div class="mt-1 text-[9px] font-black text-violet-700">Attesa: ${waitQueue.length} richieste / ${waitPeople} persone</div>` : ``}</td>'
if old_cell not in h:
    raise SystemExit('Cella capienza docenti non trovata')
h = h.replace(old_cell, new_cell, 1)

# 4) Le statistiche generali non devono considerare la coda come posti gia occupati.
old_stats_head = "      let totalInclusione = 0;\n\n      state.registrations.forEach(r => {"
new_stats_head = "      let totalInclusione = 0;\n      const activeStatsRegistrations = state.registrations.filter(r => !isWaitlistRegistration(r));\n\n      activeStatsRegistrations.forEach(r => {"
if old_stats_head not in h:
    raise SystemExit('Blocco statistiche non trovato')
h = h.replace(old_stats_head, new_stats_head, 1)
h = h.replace("iscrittiEl.innerText = state.registrations.length;", "iscrittiEl.innerText = activeStatsRegistrations.length;", 1)
h = h.replace("const totalRegistrations = state.registrations.length;", "const totalRegistrations = activeStatsRegistrations.length;", 1)

# 5) Chi e in lista d'attesa non riceve il promemoria riservato agli ammessi.
old_reminder = "      state.registrations.forEach(reg => {\n         const targetDate = state.dates.find(d => d.id === reg.dateId)?.date;"
new_reminder = "      state.registrations.forEach(reg => {\n         if (isWaitlistRegistration(reg)) return;\n         const targetDate = state.dates.find(d => d.id === reg.dateId)?.date;"
if old_reminder not in h:
    raise SystemExit('Blocco promemoria non trovato')
h = h.replace(old_reminder, new_reminder, 1)

# 6) Evita doppio ricalcolo dopo una cancellazione: triggerManualDelete lo esegue gia.
h = h.replace(
    "await window.triggerManualDelete(reg.code, true); await promoteOpenDayWaitlist(reg.dateId);",
    "await window.triggerManualDelete(reg.code, true);"
)

# Verifiche di consistenza sul comportamento richiesto.
assert "const WAITLIST_TYPE = 'lista_attesa'" in h
assert "const WAITLIST_LOCK_COLLECTION = 'openday_waitlist_locks'" in h
assert "const totalPeople = parseInt(document.getElementById('formNumAlunni').value || 1) + parseInt(document.getElementById('formNumAccompagnatori').value || 0);" in h
assert "queue.length > 0 || (activeSeats + totalPeople > maxSeats)" in h
assert "if (needed > available) break;" in h
assert "waitlistPromotionStatus: 'Ammesso da scorrimento'" in h
assert "tabWaitlist" in h and "Lista d'attesa Open Day" in h
assert "const booked = activeSeatsFor(d.id);" in h
assert "if (isWaitlistRegistration(reg)) return;" in h
assert 'Curvatura Economia)' not in h
assert 'Curvatura Economica' in h

p.write_text(h, encoding='utf-8')
print('OPEN_DAY_WAITLIST_V2_OK')
