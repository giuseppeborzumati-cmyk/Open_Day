from pathlib import Path

p = Path('index.html')
s = p.read_text(encoding='utf-8')

def rep(old, new, label):
    global s
    if old not in s:
        raise SystemExit(f'ANCHOR_NOT_FOUND: {label}')
    s = s.replace(old, new, 1)

# 1) Campo di scelta del percorso liceale nel form Open Day
rep(
'''            <input type="hidden" id="formEventId">
            <div class="grid grid-cols-2 gap-5">''',
'''            <input type="hidden" id="formEventId">
            <div id="openDayLiceoPreferenceBlock" class="hidden p-4 rounded-2xl border border-indigo-200 bg-indigo-50/70 space-y-2">
              <label for="formLiceoPreference" class="text-[11px] font-black text-indigo-800 uppercase tracking-wider">Indirizzo liceale preferito *</label>
              <select id="formLiceoPreference" class="w-full p-3 rounded-xl border border-indigo-200 bg-white outline-none focus:ring-2 focus:ring-indigo-500 font-bold text-slate-800">
                <option value="">Seleziona il percorso</option>
                <option value="scienze_applicate">Liceo Scientifico - Opzione Scienze Applicate</option>
                <option value="curvatura_economica">Liceo Scientifico - Opzione Scienze Applicate - Curvatura Economica</option>
              </select>
              <p class="text-[10px] text-indigo-700 font-semibold leading-relaxed">Il turno Open Day resta unico: questa scelta serve a indicare con precisione l'indirizzo liceale di interesse e viene mantenuta anche nell'eventuale lista d'attesa.</p>
            </div>
            <div class="grid grid-cols-2 gap-5">''',
'form liceo preference')

# 2) Costanti e helper nel modulo principale
rep(
'''    function canonicalOpenDayStudyPath(value) {
      return String(value || '').replace(/Curvatura Economia/g, 'Curvatura Economica');
    }
''',
'''    function canonicalOpenDayStudyPath(value) {
      return String(value || '').replace(/Curvatura Economia/g, 'Curvatura Economica');
    }
    const OPEN_DAY_LICEO_COMBINED = 'LS - Liceo Scientifico (Scienze Applicate & Curvatura Economica)';
    const OPEN_DAY_LICEO_PREF_STANDARD = 'scienze_applicate';
    const OPEN_DAY_LICEO_PREF_CURVATURA = 'curvatura_economica';
    function isOpenDayLiceoPath(value) {
      return /Liceo Scientifico/i.test(canonicalOpenDayStudyPath(value));
    }
    function openDayLiceoPreferenceKey(value) {
      if (value && typeof value === 'object') return String(value.liceoPreference || '').trim();
      return String(value || '').trim();
    }
    function openDayLiceoPreferenceLabel(value) {
      const key = openDayLiceoPreferenceKey(value);
      if (key === OPEN_DAY_LICEO_PREF_STANDARD) return 'Liceo Scientifico - Opzione Scienze Applicate';
      if (key === OPEN_DAY_LICEO_PREF_CURVATURA) return 'Liceo Scientifico - Opzione Scienze Applicate - Curvatura Economica';
      return '';
    }
    function updateOpenDayLiceoPreferenceField(studyPath) {
      const block = document.getElementById('openDayLiceoPreferenceBlock');
      const select = document.getElementById('formLiceoPreference');
      if (!block || !select) return;
      const liceo = isOpenDayLiceoPath(studyPath);
      block.classList.toggle('hidden', !liceo);
      select.required = liceo;
      if (!liceo) select.value = '';
    }
''',
'liceo helpers')

# 3) PDF pass: per il liceo mostra l'indirizzo effettivamente scelto
rep(
'''      addField('Indirizzo Scelto:', docObj.splitTextToSize(data.studyPath, 110), startY + lineH*2);''',
'''      const selectedStudyPath = openDayLiceoPreferenceLabel(data) || data.studyPath;
      addField('Indirizzo Scelto:', docObj.splitTextToSize(selectedStudyPath, 110), startY + lineH*2);''',
'pass pdf liceo')

# 4) PDF lista d'attesa: riporta esplicitamente la preferenza liceale
rep(
'''        ['Percorso', reg.studyPath],
        ['Turno', reg.dateStr],''',
'''        ['Percorso', reg.studyPath],
        ...(openDayLiceoPreferenceLabel(reg) ? [['Preferenza liceo', openDayLiceoPreferenceLabel(reg)]] : []),
        ['Turno', reg.dateStr],''',
'waitlist pdf preference')

# 5) Mostra/nasconde la scelta quando parte la prenotazione
rep(
'''      document.getElementById('lblBookingPath').innerText = target.studyPath;
      document.getElementById('lblBookingDate').innerText = `${new Date(target.date).toLocaleDateString('it-IT')} • Ore ${target.timeSlot}`;''',
'''      document.getElementById('lblBookingPath').innerText = target.studyPath;
      updateOpenDayLiceoPreferenceField(target.studyPath);
      document.getElementById('lblBookingDate').innerText = `${new Date(target.date).toLocaleDateString('it-IT')} • Ore ${target.timeSlot}`;''',
'start booking liceo')

# 6) Legge e valida la preferenza nel salvataggio
rep(
'''        const email = document.getElementById('formEmail').value.trim();
        const totalPeople = parseInt(document.getElementById('formNumAlunni').value || 1) + parseInt(document.getElementById('formNumAccompagnatori').value || 0);''',
'''        const email = document.getElementById('formEmail').value.trim();
        const liceoPreference = isOpenDayLiceoPath(targetSession.studyPath) ? String(document.getElementById('formLiceoPreference')?.value || '').trim() : '';
        if (isOpenDayLiceoPath(targetSession.studyPath) && !openDayLiceoPreferenceLabel(liceoPreference)) throw new Error('LICEO_PREFERENCE_REQUIRED');
        const totalPeople = parseInt(document.getElementById('formNumAlunni').value || 1) + parseInt(document.getElementById('formNumAccompagnatori').value || 0);''',
'booking preference read')

rep(
'''        const regData = { code, cognome, nome, provenienza: toTitleCase(document.getElementById('formProvenienza').value.trim()), email, totalPeople, dateId: targetSession.id, studyPath: targetSession.studyPath, dateStr: `${new Date(targetSession.date).toLocaleDateString('it-IT')} • ${targetSession.timeSlot}`, status: shouldWait ? 'Con riserva' : 'Iscritto', type: shouldWait ? WAITLIST_TYPE : ACTIVE_TYPE, inclusione: document.getElementById('formInclusione').checked, timestamp };''',
'''        const regData = { code, cognome, nome, provenienza: toTitleCase(document.getElementById('formProvenienza').value.trim()), email, totalPeople, dateId: targetSession.id, studyPath: targetSession.studyPath, liceoPreference, dateStr: `${new Date(targetSession.date).toLocaleDateString('it-IT')} • ${targetSession.timeSlot}`, status: shouldWait ? 'Con riserva' : 'Iscritto', type: shouldWait ? WAITLIST_TYPE : ACTIVE_TYPE, inclusione: document.getElementById('formInclusione').checked, timestamp };''',
'booking preference store')

# 7) Conferma: fa vedere chiaramente anche la preferenza liceale
rep(
'''        document.getElementById('ticketCode').innerText = code; document.getElementById('ticketStudent').innerText = `${regData.cognome} ${regData.nome}`; document.getElementById('ticketPath').innerText = regData.studyPath; document.getElementById('ticketDate').innerText = regData.dateStr;''',
'''        document.getElementById('ticketCode').innerText = code; document.getElementById('ticketStudent').innerText = `${regData.cognome} ${regData.nome}`; document.getElementById('ticketPath').innerText = openDayLiceoPreferenceLabel(regData) ? `${regData.studyPath}\nPreferenza: ${openDayLiceoPreferenceLabel(regData)}` : regData.studyPath; document.getElementById('ticketDate').innerText = regData.dateStr;''',
'confirmation preference')

rep(
'''      } catch(err) { console.error('OpenDay booking/waitlist', err); if (err.message === 'DUPLICATE') showToast("Esiste già una richiesta per questo studente nello stesso turno.", "error"); else showToast("Errore durante il salvataggio. Riprova.", "error"); }''',
'''      } catch(err) { console.error('OpenDay booking/waitlist', err); if (err.message === 'DUPLICATE') showToast("Esiste già una richiesta per questo studente nello stesso turno.", "error"); else if (err.message === 'LICEO_PREFERENCE_REQUIRED') showToast("Seleziona l'indirizzo liceale: Scienze Applicate oppure Curvatura Economica.", "error"); else showToast("Errore durante il salvataggio. Riprova.", "error"); }''',
'booking preference error')

# 8) Lista d'attesa docenti: colonna preferenza liceo
rep(
'''<th class="p-3">Persone</th><th class="p-3">Turno</th><th class="p-3">Indirizzo</th></tr></thead><tbody id="openDayWaitlistTableBody"></tbody></table>''',
'''<th class="p-3">Persone</th><th class="p-3">Turno</th><th class="p-3">Indirizzo</th><th class="p-3">Preferenza liceo</th></tr></thead><tbody id="openDayWaitlistTableBody"></tbody></table>''',
'waitlist table header')

rep(
'''<td class="p-3 font-black">${seatsOf(r)}</td><td class="p-3">${escWaitlist(r.dateStr)}</td><td class="p-3 max-w-[260px]">${escWaitlist(r.studyPath)}</td></tr>`;''',
'''<td class="p-3 font-black">${seatsOf(r)}</td><td class="p-3">${escWaitlist(r.dateStr)}</td><td class="p-3 max-w-[260px]">${escWaitlist(r.studyPath)}</td><td class="p-3 max-w-[280px] font-bold text-indigo-800">${escWaitlist(openDayLiceoPreferenceLabel(r) || '—')}</td></tr>`;''',
'waitlist table preference cell')

rep(
'''      }).join('') || '<tr><td colspan="7" class="p-8 text-center text-slate-400 font-bold">Nessuna iscrizione in lista d\\'attesa.</td></tr>';''',
'''      }).join('') || '<tr><td colspan="8" class="p-8 text-center text-slate-400 font-bold">Nessuna iscrizione in lista d\\'attesa.</td></tr>';''',
'waitlist empty colspan')

# 9) Elenco prenotazioni docenti: preferenza visibile sotto l'indirizzo
rep(
'''            <div class="font-bold text-slate-800 text-[10px] truncate max-w-[150px] whitespace-normal" title="${r.studyPath}">${r.studyPath}</div>
            <div class="text-[11px] text-indigo-600 font-black mt-1">${r.dateStr}</div>''',
'''            <div class="font-bold text-slate-800 text-[10px] truncate max-w-[150px] whitespace-normal" title="${r.studyPath}">${r.studyPath}</div>
            ${openDayLiceoPreferenceLabel(r) ? `<div class="text-[10px] text-emerald-700 font-black mt-1 whitespace-normal max-w-[180px]">${openDayLiceoPreferenceLabel(r)}</div>` : ''}
            <div class="text-[11px] text-indigo-600 font-black mt-1">${r.dateStr}</div>''',
'admin registrations preference')

# Mark version for verification and cache/debug visibility.
rep(
'''    // OPEN_DAY_WAITLIST_V1 - stesso meccanismo FIFO del progetto MiniStage''',
'''    // OPEN_DAY_LICEO_PREFERENCE_V2 - scelta indirizzo liceale integrata con prenotazione e lista d'attesa
    // OPEN_DAY_WAITLIST_V1 - FIFO per turno con scorrimento automatico''',
'version marker')

p.write_text(s, encoding='utf-8')
print('OPEN_DAY_LICEO_PREFERENCE_V2_OK')
