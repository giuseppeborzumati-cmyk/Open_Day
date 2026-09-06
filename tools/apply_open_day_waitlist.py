from pathlib import Path
import re

p = Path('index.html')
html = p.read_text(encoding='utf-8')

if 'OPEN_DAY_WAITLIST_V1' in html:
    print('OPEN_DAY_WAITLIST_ALREADY_APPLIED')
    raise SystemExit(0)

# Verifica richiesta: il liceo con curvatura economica è già presente nel progetto.
assert 'LS - Liceo Scientifico (Scienze Applicate & Curvatura Economia)' in html, 'Curvatura economica non trovata nel repository'

old_import = 'import { getFirestore, collection, doc, setDoc, deleteDoc, updateDoc, onSnapshot, getDocs, getDoc } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-firestore.js";'
new_import = 'import { getFirestore, collection, doc, setDoc, deleteDoc, updateDoc, onSnapshot, getDocs, getDoc, runTransaction } from "https://www.gstatic.com/firebasejs/11.6.1/firebase-firestore.js";'
assert old_import in html, 'Import Firestore atteso non trovato'
html = html.replace(old_import, new_import, 1)

app_anchor = "    const appId = 'openday-primolevi-seregno';\n"
assert app_anchor in html, 'appId anchor non trovato'
html = html.replace(app_anchor, app_anchor + """

    // OPEN_DAY_WAITLIST_V1 - stesso meccanismo FIFO del progetto MiniStage
    const WAITLIST_TYPE = 'lista_attesa';
    const ACTIVE_TYPE = 'prenotazione';
    const WAITLIST_LOCK_COLLECTION = 'openday_waitlist_locks';
    const waitlistOwnerId = `OD-WEB-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    let openDayWaitlistMode = false;
    let openDayWaitlistReconcileTimer = null;
""", 1)

helper_anchor = '    window.inviaEmailScript = inviaEmailScript;\n'
assert helper_anchor in html, 'Anchor inviaEmailScript non trovato'
helper_block = r'''

    // =========================
    // LISTA D'ATTESA OPEN DAY
    // FIFO, blocco per turno, scorrimento automatico e pannello docenti.
    // =========================
    const normalizeWaitlistText = (v) => String(v || '').trim().toLowerCase().replace(/\s+/g, ' ');
    const waitlistStamp = (r) => Number(r?.waitlistRequestedAt || r?.timestamp || r?.createdAt || 0);
    const isWaitlistRegistration = (r) => r?.type === WAITLIST_TYPE;
    const waitlistQueueFor = (dateId, source = state.registrations) => source
      .filter(r => r.dateId === dateId && isWaitlistRegistration(r))
      .sort((a,b) => waitlistStamp(a) - waitlistStamp(b));
    const activeRegistrationsFor = (dateId, source = state.registrations) => source
      .filter(r => r.dateId === dateId && !isWaitlistRegistration(r));
    const seatsOf = (r) => Math.max(1, Number(r?.totalPeople || 1) || 1);
    const activeSeatsFor = (dateId, source = state.registrations) => activeRegistrationsFor(dateId, source)
      .reduce((sum, r) => sum + seatsOf(r), 0);

    function escWaitlist(v) {
      return String(v ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    async function acquireOpenDayWaitlistLock(dateId) {
      const ref = doc(db, 'artifacts', appId, 'public', 'data', WAITLIST_LOCK_COLLECTION, dateId);
      try {
        return await runTransaction(db, async tx => {
          const snap = await tx.get(ref);
          const data = snap.exists() ? snap.data() : {};
          const now = Date.now();
          if (Number(data.lockedUntil || 0) > now && data.owner !== waitlistOwnerId) return false;
          tx.set(ref, { owner: waitlistOwnerId, lockedAt: now, lockedUntil: now + 15000 }, { merge: true });
          return true;
        });
      } catch (e) {
        console.warn('OpenDay waitlist: lock non acquisito', e);
        return false;
      }
    }

    async function releaseOpenDayWaitlistLock(dateId) {
      try {
        await setDoc(doc(db, 'artifacts', appId, 'public', 'data', WAITLIST_LOCK_COLLECTION, dateId), {
          owner: '', lockedUntil: 0, releasedAt: Date.now()
        }, { merge: true });
      } catch (_) {}
    }

    async function uniqueOpenDayCode() {
      for (let i = 0; i < 12; i++) {
        const code = `LEVI-${Math.floor(100000 + Math.random() * 900000)}`;
        const snap = await getDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', code));
        if (!snap.exists()) return code;
      }
      return `LEVI-${String(Date.now()).slice(-6)}`;
    }

    async function generateWaitlistReceiptPDF(reg, position) {
      const { jsPDF } = window.jspdf;
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
      pdf.setFillColor(76, 29, 149); pdf.rect(0, 0, 210, 38, 'F');
      pdf.setTextColor(255,255,255); pdf.setFont('helvetica','bold'); pdf.setFontSize(20);
      pdf.text('ITSCG "PRIMO LEVI" - SEREGNO', 105, 16, { align: 'center' });
      pdf.setFontSize(11); pdf.text('ISCRIZIONE CON RISERVA - OPEN DAY', 105, 26, { align: 'center' });
      pdf.setFillColor(250,245,255); pdf.setDrawColor(168,85,247); pdf.roundedRect(15,50,180,30,3,3,'FD');
      pdf.setTextColor(88,28,135); pdf.setFontSize(13); pdf.text('NON È ANCORA UN PASS DI ACCESSO', 105, 62, {align:'center'});
      pdf.setFont('helvetica','normal'); pdf.setFontSize(9);
      pdf.text('Attendi una seconda e-mail di conferma: solo quella renderà definitiva la prenotazione.', 105, 71, {align:'center'});
      pdf.setTextColor(15,23,42); pdf.setFont('helvetica','bold'); pdf.setFontSize(11);
      const rows = [
        ['Studente', `${reg.cognome || ''} ${reg.nome || ''}`.trim()],
        ['Codice richiesta', reg.code],
        ['Percorso', reg.studyPath],
        ['Turno', reg.dateStr],
        ['Persone richieste', String(reg.totalPeople || 1)],
        ['Posizione indicativa', String(position || 'in aggiornamento')]
      ];
      let y = 96;
      rows.forEach(([label, value]) => {
        pdf.setFont('helvetica','bold'); pdf.setTextColor(100,116,139); pdf.text(`${label}:`, 22, y);
        pdf.setFont('helvetica','normal'); pdf.setTextColor(15,23,42);
        const lines = pdf.splitTextToSize(String(value || '-'), 105); pdf.text(lines, 72, y); y += Math.max(12, lines.length * 5 + 5);
      });
      pdf.setFillColor(254,242,242); pdf.setDrawColor(248,113,113); pdf.roundedRect(15,205,180,36,3,3,'FD');
      pdf.setTextColor(153,27,27); pdf.setFont('helvetica','bold'); pdf.setFontSize(11); pdf.text('COME FUNZIONA', 22,216);
      pdf.setFont('helvetica','normal'); pdf.setFontSize(8.5);
      const note = 'La lista segue rigorosamente l’ordine cronologico. Se si libera capienza, il sistema ammette automaticamente il primo gruppo utile in coda. La presente ricevuta non consente l’ingresso finché non arriva la conferma definitiva.';
      pdf.text(pdf.splitTextToSize(note,160),22,224);
      pdf.setFontSize(7.5); pdf.setTextColor(120,120,130); pdf.text(`Generato il ${new Date().toLocaleString('it-IT')}`,15,285);
      return pdf.output('datauristring').split(',')[1];
    }

    async function queuePositionOpenDay(reg, source = state.registrations) {
      const q = waitlistQueueFor(reg.dateId, source);
      const idx = q.findIndex(x => x.code === reg.code);
      return idx >= 0 ? idx + 1 : null;
    }

    async function sendOpenDayWaitlistEmail(reg, position) {
      try {
        const pdfBase64 = await generateWaitlistReceiptPDF(reg, position);
        await window.inviaEmailScript(CONFIRM_SCRIPT_URL, {
          ...reg,
          pdfBase64,
          type: 'iscrizione_con_riserva',
          stato: 'ISCRIZIONE CON RISERVA',
          posizione_lista: position || '',
          subject: `Open Day Primo Levi - Iscrizione con riserva ${reg.code}`,
          oggetto: `Open Day Primo Levi - Iscrizione con riserva ${reg.code}`,
          message: `La richiesta ${reg.code} è stata inserita in lista d'attesa. Posizione indicativa: ${position || 'in aggiornamento'}. Attendere la conferma definitiva.`,
          messaggio: `La richiesta ${reg.code} è stata inserita in lista d'attesa. Posizione indicativa: ${position || 'in aggiornamento'}. Attendere la conferma definitiva.`
        });
        await updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', reg.code), {
          waitlistEmailSentAt: Date.now()
        }).catch(() => {});
      } catch (e) {
        console.warn('OpenDay waitlist: e-mail riserva non completata', e);
      }
    }

    async function sendOpenDayPromotionEmail(reg) {
      try {
        const pdfBase64 = await window.generateReceiptPDF(reg, reg.code);
        await window.inviaEmailScript(CONFIRM_SCRIPT_URL, {
          ...reg,
          pdfBase64,
          type: 'ammesso_da_scorrimento',
          stato: 'AMMESSO DA SCORRIMENTO',
          subject: `Open Day Primo Levi - Posto assegnato dalla lista d'attesa ${reg.code}`,
          oggetto: `Open Day Primo Levi - Posto assegnato dalla lista d'attesa ${reg.code}`,
          message: `Il posto è stato assegnato automaticamente dalla lista d'attesa. La prenotazione ${reg.code} è ora confermata.`,
          messaggio: `Il posto è stato assegnato automaticamente dalla lista d'attesa. La prenotazione ${reg.code} è ora confermata.`
        });
        await updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', reg.code), {
          passSentDate: new Date().toLocaleString('it-IT'),
          waitlistPromotionEmailSentAt: Date.now()
        }).catch(() => {});
      } catch (e) {
        console.warn('OpenDay waitlist: e-mail promozione non completata', e);
      }
    }

    async function promoteOpenDayWaitlist(dateId) {
      if (!dateId) return false;
      const locked = await acquireOpenDayWaitlistLock(dateId);
      if (!locked) return false;
      const promoted = [];
      try {
        let slot = state.dates.find(d => d.id === dateId);
        if (!slot) {
          const snap = await getDoc(doc(db, 'artifacts', appId, 'public', 'data', 'dates', dateId));
          if (snap.exists()) slot = { id: snap.id, ...snap.data() };
        }
        if (!slot) return false;

        const snap = await getDocs(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'));
        const fresh = []; snap.forEach(d => fresh.push({ id: d.id, ...d.data() }));
        let available = Math.max(0, Number(slot.maxSeats || 0) - activeSeatsFor(dateId, fresh));
        const queue = waitlistQueueFor(dateId, fresh);

        while (queue.length && available > 0) {
          const next = queue[0];
          const needed = seatsOf(next);
          if (needed > available) break;
          queue.shift();
          const patch = {
            type: ACTIVE_TYPE,
            status: 'Iscritto',
            iscrizioneConRiserva: false,
            waitlistPromotedAt: Date.now(),
            waitlistPromotionStatus: 'Ammesso da scorrimento',
            waitlistPromotionSource: 'automatico_fifo',
            waitlistPositionAtPromotion: 1
          };
          await updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', next.code), patch);
          promoted.push({ ...next, ...patch });
          available -= needed;
        }
      } finally {
        await releaseOpenDayWaitlistLock(dateId);
      }

      for (const reg of promoted) await sendOpenDayPromotionEmail(reg);
      if (promoted.length) window.showToast?.(`${promoted.length} iscrizione/i ammesse automaticamente dalla lista d'attesa.`, 'info');
      return promoted.length > 0;
    }
    window.promoteOpenDayWaitlist = promoteOpenDayWaitlist;

    async function reconcileAllOpenDayWaitlists() {
      for (const d of state.dates) await promoteOpenDayWaitlist(d.id).catch(() => false);
      renderOpenDayWaitlistAdmin();
      window.renderHomeDates?.();
    }
    window.reconcileAllOpenDayWaitlists = reconcileAllOpenDayWaitlists;

    function scheduleOpenDayWaitlistReconcile() {
      clearTimeout(openDayWaitlistReconcileTimer);
      openDayWaitlistReconcileTimer = setTimeout(() => reconcileAllOpenDayWaitlists().catch(() => {}), 450);
    }

    function setOpenDayBookingMode(isWait) {
      openDayWaitlistMode = !!isWait;
      const btn = document.getElementById('btnSubmitBooking');
      if (btn) {
        btn.innerHTML = isWait
          ? '<i data-lucide="clock-3" class="w-5 h-5"></i> Inserisci in Lista d\'attesa'
          : '<i data-lucide="check-circle" class="w-5 h-5"></i> Conferma Iscrizione';
        btn.className = isWait
          ? 'w-full sm:w-2/3 py-3.5 bg-violet-600 hover:bg-violet-500 text-white font-black rounded-xl text-sm uppercase tracking-widest shadow-xl transition flex items-center justify-center gap-2'
          : 'w-full sm:w-2/3 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-black rounded-xl text-sm uppercase tracking-widest shadow-xl transition flex items-center justify-center gap-2';
      }
      const box = document.getElementById('openDayWaitlistBookingNotice');
      if (box) box.remove();
      if (isWait) {
        const info = document.getElementById('lblBookingAula')?.parentElement;
        if (info) info.insertAdjacentHTML('afterend', '<div id="openDayWaitlistBookingNotice" class="p-4 rounded-2xl border border-violet-200 bg-violet-50 text-violet-900 text-xs font-bold">Posti esauriti o coda già attiva: la richiesta sarà registrata <strong>con riserva</strong> e seguirà l’ordine cronologico. Non riceverai un pass valido finché non sarai ammesso dallo scorrimento.</div>');
      }
      try { lucide.createIcons(); } catch(e) {}
    }

    function startWaitlistProcess(sid) {
      window.startBookingProcess(sid);
      setOpenDayBookingMode(true);
    }
    window.startWaitlistProcess = startWaitlistProcess;

    function prepareOpenDayConfirmation(reg) {
      const header = document.querySelector('#sectionConfirmation .bg-gradient-to-tr');
      const title = document.querySelector('#sectionConfirmation h3');
      const status = document.getElementById('confirmationEmailStatus');
      const download = document.querySelector('#sectionConfirmation button[onclick="window.downloadTicketPDF()"]');
      if (isWaitlistRegistration(reg)) {
        if (header) {
          header.classList.remove('from-emerald-500','to-teal-600');
          header.classList.add('from-violet-600','to-purple-700');
        }
        if (title) title.textContent = 'Iscrizione con Riserva';
        if (status) status.textContent = 'Sei in lista d’attesa. Riceverai una seconda e-mail solo se il posto viene assegnato.';
        if (download) {
          download.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i><span>Scarica Ricevuta di Riserva</span>';
          download.classList.remove('bg-indigo-600','hover:bg-indigo-500');
          download.classList.add('bg-violet-600','hover:bg-violet-500');
        }
      } else {
        if (header) {
          header.classList.remove('from-violet-600','to-purple-700');
          header.classList.add('from-emerald-500','to-teal-600');
        }
        if (title) title.textContent = reg.waitlistPromotedAt ? 'Ammesso da Scorrimento!' : 'Prenotazione Confermata!';
        if (status) status.textContent = reg.waitlistPromotedAt ? 'Il posto è stato assegnato dalla lista d’attesa. Il pass è ora valido.' : "L'iscrizione è immediata. L'e-mail di riepilogo è in arrivo.";
        if (download) {
          download.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i><span>Scarica il Pass PDF</span>';
          download.classList.remove('bg-violet-600','hover:bg-violet-500');
          download.classList.add('bg-indigo-600','hover:bg-indigo-500');
        }
      }
      try { lucide.createIcons(); } catch(e) {}
    }

    function ensureOpenDayWaitlistAdminUI() {
      const regBtn = document.querySelector('button[onclick="window.switchAdminTab(\'tabRegistrations\')"]');
      if (regBtn && !document.getElementById('btnOpenDayWaitlistTab')) {
        const b = document.createElement('button');
        b.id = 'btnOpenDayWaitlistTab';
        b.type = 'button';
        b.className = 'px-5 py-2.5 bg-violet-600 text-white font-bold rounded-xl text-xs shadow-sm uppercase tracking-wider';
        b.innerHTML = '<span>Lista d\'attesa</span> <span id="adminWaitlistBadge" class="ml-1 bg-white/20 px-1.5 py-0.5 rounded">0</span>';
        b.onclick = () => window.switchAdminTab('tabWaitlist');
        regBtn.insertAdjacentElement('afterend', b);
      }
      const admin = document.getElementById('sectionAdmin');
      if (admin && !document.getElementById('tabWaitlist')) {
        const section = document.createElement('div');
        section.id = 'tabWaitlist';
        section.className = 'hidden space-y-6';
        section.innerHTML = `
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="glass-card p-5 rounded-2xl border border-violet-200 bg-white"><p class="text-[10px] uppercase font-black text-violet-600">In lista d'attesa</p><p id="odWaitRows" class="text-3xl font-black text-violet-950">0</p></div>
            <div class="glass-card p-5 rounded-2xl border border-purple-200 bg-white"><p class="text-[10px] uppercase font-black text-purple-600">Persone in attesa</p><p id="odWaitPeople" class="text-3xl font-black text-purple-950">0</p></div>
            <div class="glass-card p-5 rounded-2xl border border-fuchsia-200 bg-white"><p class="text-[10px] uppercase font-black text-fuchsia-600">Ammessi da scorrimento</p><p id="odWaitPromoted" class="text-3xl font-black text-fuchsia-950">0</p></div>
          </div>
          <div class="glass-card p-6 rounded-3xl border border-violet-200 bg-white space-y-4">
            <div class="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
              <div><h3 class="text-xl font-black text-violet-950 font-outfit">Lista d'attesa Open Day</h3><p class="text-xs text-slate-500 font-bold mt-1">Ordine FIFO automatico: posizione calcolata per singolo turno. Nessun nominativo viene saltato.</p></div>
              <button onclick="window.reconcileAllOpenDayWaitlists()" class="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 text-white font-black rounded-xl text-xs uppercase tracking-wider">Ricalcola scorrimento</button>
            </div>
            <div class="grid md:grid-cols-2 gap-3">
              <select id="waitlistDateFilter" onchange="window.renderOpenDayWaitlistAdmin()" class="p-3 rounded-xl border border-slate-200 bg-slate-50 text-xs font-bold"><option value="all">Tutti i turni</option></select>
              <select id="waitlistPathFilter" onchange="window.renderOpenDayWaitlistAdmin()" class="p-3 rounded-xl border border-slate-200 bg-slate-50 text-xs font-bold"><option value="all">Tutti gli indirizzi</option></select>
            </div>
            <div class="overflow-x-auto border border-slate-200 rounded-2xl">
              <table class="w-full text-left text-xs min-w-[900px]"><thead class="bg-violet-50 text-violet-950"><tr><th class="p-3">Pos.</th><th class="p-3">Codice</th><th class="p-3">Studente</th><th class="p-3">Contatto</th><th class="p-3">Persone</th><th class="p-3">Turno</th><th class="p-3">Indirizzo</th></tr></thead><tbody id="openDayWaitlistTableBody"></tbody></table>
            </div>
          </div>`;
        admin.appendChild(section);
      }
    }

    function renderOpenDayWaitlistAdmin() {
      ensureOpenDayWaitlistAdminUI();
      const waitsAll = state.registrations.filter(isWaitlistRegistration).sort((a,b) => waitlistStamp(a)-waitlistStamp(b));
      const promoted = state.registrations.filter(r => !!r.waitlistPromotedAt || r.waitlistPromotionStatus === 'Ammesso da scorrimento');
      const badge = document.getElementById('adminWaitlistBadge'); if (badge) badge.textContent = String(waitsAll.length);
      const rowsEl = document.getElementById('odWaitRows'); if (rowsEl) rowsEl.textContent = String(waitsAll.length);
      const peopleEl = document.getElementById('odWaitPeople'); if (peopleEl) peopleEl.textContent = String(waitsAll.reduce((s,r)=>s+seatsOf(r),0));
      const promEl = document.getElementById('odWaitPromoted'); if (promEl) promEl.textContent = String(promoted.length);

      const dateFilter = document.getElementById('waitlistDateFilter');
      const pathFilter = document.getElementById('waitlistPathFilter');
      if (dateFilter) {
        const keep = dateFilter.value || 'all';
        dateFilter.innerHTML = '<option value="all">Tutti i turni</option>' + state.dates
          .slice().sort((a,b)=>String(a.date).localeCompare(String(b.date)) || String(a.timeSlot).localeCompare(String(b.timeSlot)))
          .map(d=>`<option value="${escWaitlist(d.id)}">${new Date(d.date).toLocaleDateString('it-IT')} · ${escWaitlist(d.timeSlot)}</option>`).join('');
        if ([...dateFilter.options].some(o=>o.value===keep)) dateFilter.value = keep;
      }
      if (pathFilter) {
        const keep = pathFilter.value || 'all';
        const paths = [...new Set(state.dates.map(d=>d.studyPath).filter(Boolean))].sort();
        pathFilter.innerHTML = '<option value="all">Tutti gli indirizzi</option>' + paths.map(p=>`<option value="${escWaitlist(p)}">${escWaitlist(p)}</option>`).join('');
        if ([...pathFilter.options].some(o=>o.value===keep)) pathFilter.value = keep;
      }
      const df = dateFilter?.value || 'all';
      const pf = pathFilter?.value || 'all';
      const waits = waitsAll.filter(r => (df==='all' || r.dateId===df) && (pf==='all' || r.studyPath===pf));
      const body = document.getElementById('openDayWaitlistTableBody');
      if (body) body.innerHTML = waits.map(r => {
        const pos = waitlistQueueFor(r.dateId).findIndex(x=>x.code===r.code)+1;
        return `<tr class="border-t border-slate-100"><td class="p-3"><span class="inline-flex min-w-9 justify-center bg-violet-100 text-violet-800 font-black px-2 py-1 rounded-lg">${pos}</span></td><td class="p-3 font-mono font-black text-indigo-700">${escWaitlist(r.code)}</td><td class="p-3 font-black text-slate-900">${escWaitlist(r.cognome)} ${escWaitlist(r.nome)}</td><td class="p-3"><div>${escWaitlist(r.email)}</div><div class="text-[10px] text-slate-400">${new Date(waitlistStamp(r)).toLocaleString('it-IT')}</div></td><td class="p-3 font-black">${seatsOf(r)}</td><td class="p-3">${escWaitlist(r.dateStr)}</td><td class="p-3 max-w-[260px]">${escWaitlist(r.studyPath)}</td></tr>`;
      }).join('') || '<tr><td colspan="7" class="p-8 text-center text-slate-400 font-bold">Nessuna iscrizione in lista d\'attesa.</td></tr>';
    }
    window.renderOpenDayWaitlistAdmin = renderOpenDayWaitlistAdmin;

    setTimeout(() => { ensureOpenDayWaitlistAdminUI(); renderOpenDayWaitlistAdmin(); }, 0);
'''
html = html.replace(helper_anchor, helper_anchor + helper_block, 1)

render_pattern = re.compile(r"    function renderHomeDates\(\) \{.*?\n    window\.renderHomeDates = renderHomeDates;", re.S)
render_repl = r'''    function renderHomeDates() {
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
          const activeSeats = activeSeatsFor(s.id);
          const queue = waitlistQueueFor(s.id);
          const available = Math.max(0, Number(s.maxSeats || 0) - activeSeats);
          const mustWait = queue.length > 0 || available <= 0;
          return `
            <div class="p-4 bg-white/80 rounded-xl border border-slate-200 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 text-xs font-semibold shadow-sm transition hover:border-indigo-300">
              <div class="w-full sm:w-2/3"><span class="font-black text-slate-900 block text-[12px] sm:text-[13px] leading-tight mb-1 whitespace-normal">${s.studyPath}</span><span class="inline-block text-[10px] text-indigo-700 font-bold bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-lg mb-1">Ore ${s.timeSlot} • Sede: ${s.aula}</span></div>
              <div class="flex items-center gap-2 w-full sm:w-auto">
                ${mustWait ? `<span class="text-[9px] font-black text-violet-700 bg-violet-50 border border-violet-200 px-2 py-1.5 rounded-lg whitespace-nowrap">⏳ ${queue.length ? `IN ATTESA: ${queue.length}` : 'POSTI ESAURITI'}</span>` : `<span class="text-[9px] font-black text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-1.5 rounded-lg whitespace-nowrap">🔥 ${available} LIBERI</span>`}
                <button onclick="${mustWait ? `window.startWaitlistProcess('${s.id}')` : `window.startBookingProcess('${s.id}')`}" class="w-full sm:w-auto px-4 py-2.5 ${mustWait?'bg-violet-600 hover:bg-violet-500 text-white':'bg-indigo-600 hover:bg-indigo-500 text-white'} rounded-lg uppercase font-black text-[10px] shadow-sm transition tracking-wider flex items-center justify-center gap-1 shrink-0">${mustWait ? `LISTA D'ATTESA${queue.length ? ` (${queue.length})` : ''}` : 'ISCRIVITI <i data-lucide="arrow-right" class="w-3 h-3"></i>'}</button>
              </div>
            </div>`;
        }).join('');
        return `<div class="glass-card p-5 rounded-3xl border space-y-4 shadow-sm hover:shadow-md transition"><h4 class="text-lg font-black text-indigo-950 font-outfit uppercase border-b border-slate-200 pb-2">${new Date(dateVal).toLocaleDateString('it-IT', {weekday:'long', day:'numeric', month:'long', year:'numeric'})}</h4><div class="space-y-3">${slotsHtml}</div></div>`;
      }).join('');
      try { lucide.createIcons(); } catch(e){}
    }
    window.renderHomeDates = renderHomeDates;'''
html, n = render_pattern.subn(render_repl, html, count=1)
assert n == 1, f'renderHomeDates replacement count {n}'

start_pattern = re.compile(r"    function startBookingProcess\(sid\) \{.*?\n    window\.startBookingProcess = startBookingProcess;", re.S)
start_repl = r'''    function startBookingProcess(sid) {
      const target = state.dates.find(x => x.id === sid);
      if (!target) return;
      setOpenDayBookingMode(false);
      document.getElementById('formEventId').value = sid;
      document.getElementById('lblBookingPath').innerText = target.studyPath;
      document.getElementById('lblBookingDate').innerText = `${new Date(target.date).toLocaleDateString('it-IT')} • Ore ${target.timeSlot}`;
      document.getElementById('lblBookingAula').innerText = target.aula;
      window.navigateTo('booking');
    }
    window.startBookingProcess = startBookingProcess;'''
html, n = start_pattern.subn(start_repl, html, count=1)
assert n == 1, f'startBooking replacement count {n}'

html = html.replace("    function cancelBookingProcess() { document.getElementById('bookingForm').reset(); window.navigateTo('home'); setTimeout(() => document.getElementById('datesSection')?.scrollIntoView({ behavior: 'smooth' }), 100); }", "    function cancelBookingProcess() { openDayWaitlistMode = false; document.getElementById('bookingForm').reset(); window.navigateTo('home'); setTimeout(() => document.getElementById('datesSection')?.scrollIntoView({ behavior: 'smooth' }), 100); }", 1)

booking_pattern = re.compile(r"    async function handleBookingSubmit\(e\) \{.*?\n    window\.handleBookingSubmit = handleBookingSubmit;", re.S)
booking_repl = r'''    async function handleBookingSubmit(e) {
      e.preventDefault();
      const targetSession = state.dates.find(x => x.id === document.getElementById('formEventId').value);
      const submitBtn = document.getElementById('btnSubmitBooking');
      if (!targetSession || !submitBtn) return showToast("Turno non disponibile.", "error");
      if (submitBtn.dataset.saving === '1') return;
      submitBtn.dataset.saving = '1'; submitBtn.disabled = true;
      setProgress(0, "Controllo disponibilità e ordine di coda...");
      const dateId = targetSession.id;
      const locked = await acquireOpenDayWaitlistLock(dateId);
      if (!locked) { submitBtn.dataset.saving = '0'; submitBtn.disabled = false; return showToast("Il turno è in aggiornamento. Riprova tra pochi secondi.", "warning"); }
      try {
        const cognome = toTitleCase(document.getElementById('formCognome').value.trim());
        const nome = toTitleCase(document.getElementById('formNome').value.trim());
        const email = document.getElementById('formEmail').value.trim();
        const totalPeople = parseInt(document.getElementById('formNumAlunni').value || 1) + parseInt(document.getElementById('formNumAccompagnatori').value || 0);
        const freshSnap = await getDocs(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'));
        const fresh = []; freshSnap.forEach(d => fresh.push({id:d.id, ...d.data()}));
        const duplicate = fresh.some(r => r.dateId === dateId && normalizeWaitlistText(r.email) === normalizeWaitlistText(email) && normalizeWaitlistText(r.cognome) === normalizeWaitlistText(cognome) && normalizeWaitlistText(r.nome) === normalizeWaitlistText(nome));
        if (duplicate) throw new Error('DUPLICATE');
        const activeSeats = activeSeatsFor(dateId, fresh);
        const queue = waitlistQueueFor(dateId, fresh);
        const maxSeats = Math.max(1, Number(targetSession.maxSeats || 1));
        const shouldWait = openDayWaitlistMode || queue.length > 0 || (activeSeats + totalPeople > maxSeats);
        const code = await uniqueOpenDayCode();
        const timestamp = Date.now();
        const regData = { code, cognome, nome, provenienza: toTitleCase(document.getElementById('formProvenienza').value.trim()), email, totalPeople, dateId: targetSession.id, studyPath: targetSession.studyPath, dateStr: `${new Date(targetSession.date).toLocaleDateString('it-IT')} • ${targetSession.timeSlot}`, status: shouldWait ? 'Con riserva' : 'Iscritto', type: shouldWait ? WAITLIST_TYPE : ACTIVE_TYPE, inclusione: document.getElementById('formInclusione').checked, timestamp };
        if (shouldWait) Object.assign(regData, { waitlistRequestedAt: timestamp, waitlistStatus: 'Iscrizione con riserva', iscrizioneConRiserva: true }); else regData.passSentDate = 'IN_CODA_Q1';
        state.currentBooking = regData;
        await setDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', code), regData);
        document.getElementById('ticketCode').innerText = code; document.getElementById('ticketStudent').innerText = `${regData.cognome} ${regData.nome}`; document.getElementById('ticketPath').innerText = regData.studyPath; document.getElementById('ticketDate').innerText = regData.dateStr;
        prepareOpenDayConfirmation(regData);
        if (shouldWait) { const position = queue.length + 1; await sendOpenDayWaitlistEmail(regData, position); showToast(`Richiesta registrata con riserva. Posizione indicativa: ${position}.`, 'info'); } else window.SmartEmailEngine.flushNow();
        window.navigateTo('confirmation');
      } catch(err) { console.error('OpenDay booking/waitlist', err); if (err.message === 'DUPLICATE') showToast("Esiste già una richiesta per questo studente nello stesso turno.", "error"); else showToast("Errore durante il salvataggio. Riprova.", "error"); }
      finally { await releaseOpenDayWaitlistLock(dateId); submitBtn.dataset.saving = '0'; submitBtn.disabled = false; setProgress(100, openDayWaitlistMode ? "Richiesta in lista registrata" : "Prenotazione registrata"); }
    }
    window.handleBookingSubmit = handleBookingSubmit;'''
html, n = booking_pattern.subn(booking_repl, html, count=1)
assert n == 1, f'handleBookingSubmit replacement count {n}'

pdf_pattern = re.compile(r"    async function downloadTicketPDF\(\) \{.*?\n    window\.downloadTicketPDF = downloadTicketPDF;", re.S)
pdf_repl = r'''    async function downloadTicketPDF() {
      if(!state.currentBooking) return;
      showToast("Download PDF in corso...", "success");
      try {
        let b64, fileName;
        if (isWaitlistRegistration(state.currentBooking)) { const pos = await queuePositionOpenDay(state.currentBooking); b64 = await generateWaitlistReceiptPDF(state.currentBooking, pos); fileName = `Riserva_OpenDay_${state.currentBooking.cognome}_${state.currentBooking.code}.pdf`; }
        else { b64 = await window.generateReceiptPDF(state.currentBooking, state.currentBooking.code); fileName = `Pass_Levi_${state.currentBooking.cognome}.pdf`; }
        const link = document.createElement('a'); link.href = 'data:application/pdf;base64,' + b64; link.download = fileName; link.click();
      } catch(e) { showToast("Errore di generazione PDF.", "error"); }
    }
    window.downloadTicketPDF = downloadTicketPDF;'''
html, n = pdf_pattern.subn(pdf_repl, html, count=1)
assert n == 1, f'downloadTicketPDF replacement count {n}'

recovery_pattern = re.compile(r"    async function handleRecovery\(e\) \{.*?\n    window\.handleRecovery = handleRecovery;", re.S)
recovery_repl = r'''    async function handleRecovery(e) {
      e.preventDefault();
      const codeTerm = document.getElementById('recoveryCode').value.trim(); const cogTerm = document.getElementById('recoveryCognome').value.trim().toLowerCase(); const nomTerm = document.getElementById('recoveryNome').value.trim().toLowerCase();
      if (!codeTerm && (!cogTerm || !nomTerm)) return showToast("Inserisci il codice oppure Nome e Cognome.", "error");
      const reg = codeTerm ? state.registrations.find(x => x.code === codeTerm.toUpperCase()) : state.registrations.find(x => x.cognome.toLowerCase() === cogTerm && x.nome.toLowerCase() === nomTerm);
      if(!reg) return showToast("Prenotazione non trovata.", "error");
      const btn = document.getElementById('btnSubmitRecovery'); btn.innerHTML = `<span class="animate-pulse">Invio in corso...</span>`; btn.disabled = true;
      try {
        if (isWaitlistRegistration(reg)) { const pos = await queuePositionOpenDay(reg); await sendOpenDayWaitlistEmail(reg, pos); const msg = document.getElementById('recoveryModalMessage'); if (msg) msg.textContent = `Ricevuta di riserva reinviata. Posizione indicativa attuale: ${pos || 'in aggiornamento'}.`; }
        else { const pdfBase64 = await window.generateReceiptPDF(reg, reg.code); await window.inviaEmailScript(CONFIRM_SCRIPT_URL, { ...reg, pdfBase64, type: 'recupero' }); const msg = document.getElementById('recoveryModalMessage'); if (msg) msg.textContent = 'Il pass di prenotazione è stato reinviato via e-mail.'; }
        document.getElementById('recoveryModalFormView').classList.add('hidden'); document.getElementById('recoveryModalSuccessView').classList.remove('hidden');
      } catch(err) { showToast("Errore durante l'invio.", "error"); }
      btn.innerHTML = `Invia Conferma via Email`; btn.disabled = false;
    }
    window.handleRecovery = handleRecovery;'''
html, n = recovery_pattern.subn(recovery_repl, html, count=1)
assert n == 1, f'handleRecovery replacement count {n}'

cancel_pattern = re.compile(r"    async function handleCancellation\(e\) \{.*?\n    window\.handleCancellation = handleCancellation;", re.S)
cancel_repl = r'''    async function handleCancellation(e) {
      e.preventDefault();
      const codeTerm = document.getElementById('cancelCode').value.trim(); const cogTerm = document.getElementById('cancelCognome').value.trim().toLowerCase(); const nomTerm = document.getElementById('cancelNome').value.trim().toLowerCase();
      if (!codeTerm && (!cogTerm || !nomTerm)) return showToast("Inserisci il codice oppure Nome e Cognome.", "error");
      const reg = codeTerm ? state.registrations.find(x => x.code === codeTerm.toUpperCase()) : state.registrations.find(x => x.cognome.toLowerCase() === cogTerm && x.nome.toLowerCase() === nomTerm);
      if(!reg) return showToast("Nessuna prenotazione trovata.", "error");
      const btn = document.getElementById('btnSubmitCancellation'); btn.innerHTML = `<span class="animate-pulse">Annullamento in corso...</span>`; btn.disabled = true;
      try { await window.inviaEmailScript(CANCEL_SCRIPT_URL, reg); await window.triggerManualDelete(reg.code, true); await promoteOpenDayWaitlist(reg.dateId); document.getElementById('cancelModalFormView').classList.add('hidden'); document.getElementById('cancelModalSuccessView').classList.remove('hidden'); }
      catch(err) { showToast("Errore durante l'annullamento.", "error"); }
      btn.innerHTML = `Conferma Annullamento`; btn.disabled = false;
    }
    window.handleCancellation = handleCancellation;'''
html, n = cancel_pattern.subn(cancel_repl, html, count=1)
assert n == 1, f'handleCancellation replacement count {n}'

delete_pattern = re.compile(r"    async function triggerManualDelete\(code, silent = false\) \{.*?\n    window\.triggerManualDelete = triggerManualDelete;", re.S)
delete_repl = r'''    async function triggerManualDelete(code, silent = false) {
      if(!silent && !confirm("Cancellare definitivamente questo iscritto dal database?")) return;
      const existing = state.registrations.find(r => r.code === code);
      try { const riga = document.getElementById(`riga-${code}`); if(riga && !silent) { riga.style.transition="opacity 0.3s"; riga.style.opacity="0"; } await deleteDoc(doc(db, 'artifacts', appId, 'public', 'data', 'registrations', code)); if (existing?.dateId) await promoteOpenDayWaitlist(existing.dateId); if(!silent) showToast("Eliminato. Lista d'attesa ricalcolata.", "success"); }
      catch(e) { if(!silent) showToast("Errore durante l'eliminazione", "error"); }
    }
    window.triggerManualDelete = triggerManualDelete;'''
html, n = delete_pattern.subn(delete_repl, html, count=1)
assert n == 1, f'triggerManualDelete replacement count {n}'

old_switch = "    function switchAdminTab(id) { ['tabRegistrations','tabLiveScanner','tabSettings','tabStatistics','tabSmartEmail'].forEach(t => document.getElementById(t)?.classList.add('hidden')); document.getElementById(id)?.classList.remove('hidden'); }"
new_switch = "    function switchAdminTab(id) { ['tabRegistrations','tabLiveScanner','tabSettings','tabStatistics','tabSmartEmail','tabWaitlist'].forEach(t => document.getElementById(t)?.classList.add('hidden')); ensureOpenDayWaitlistAdminUI(); document.getElementById(id)?.classList.remove('hidden'); if(id === 'tabWaitlist') renderOpenDayWaitlistAdmin(); }"
assert old_switch in html, 'switchAdminTab atteso non trovato'
html = html.replace(old_switch, new_switch, 1)

html = html.replace("        populateFilters();\n      });\n      onSnapshot(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'), s => {", "        populateFilters();\n        scheduleOpenDayWaitlistReconcile();\n      });\n      onSnapshot(collection(db, 'artifacts', appId, 'public', 'data', 'registrations'), s => {", 1)
old_admin_listener = "        if (state.currentView === 'admin') { window.renderRegistrations(); window.updateStatistics(); window.renderAdminDatesList(); }"
assert old_admin_listener in html, 'listener admin registrazioni non trovato'
html = html.replace(old_admin_listener, "        if (state.currentView === 'admin') { window.renderRegistrations(); window.updateStatistics(); window.renderAdminDatesList(); renderOpenDayWaitlistAdmin(); }\n        scheduleOpenDayWaitlistReconcile();", 1)

old_scanner = "            if (reg && reg.status !== 'Ammesso' && reg.status !== 'Concluso') {"
new_scanner = "            if (reg && reg.type !== WAITLIST_TYPE && reg.status !== 'Ammesso' && reg.status !== 'Concluso') {"
assert old_scanner in html, 'condizione scanner non trovata'
html = html.replace(old_scanner, new_scanner, 1)

old_reset = "    function resetAndGoHome() { document.getElementById('bookingForm').reset(); window.navigateTo('home'); }"
if old_reset in html:
    html = html.replace(old_reset, "    function resetAndGoHome() { openDayWaitlistMode = false; document.getElementById('bookingForm').reset(); window.navigateTo('home'); }", 1)

assert "const WAITLIST_TYPE = 'lista_attesa'" in html
assert "window.startWaitlistProcess" in html
assert "waitlistPromotionStatus: 'Ammesso da scorrimento'" in html
assert "id = 'tabWaitlist'" in html
assert "reg.type !== WAITLIST_TYPE" in html
assert 'Curvatura Economia' in html

p.write_text(html, encoding='utf-8')
print('OPEN_DAY_WAITLIST_PATCH_OK')
