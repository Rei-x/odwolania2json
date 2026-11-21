// "Nowy typ dokumentu" — kreator klasy dokumentu bez zmian w kodzie (otwierany przyciskiem lub /app#nowy-typ).
// Korzysta z pomocników z index.html: $, esc, hjson, KEY, LABEL, toast.
(() => {
const SAMPLE_NAME = 'przystapienie';
const SAMPLE_TITLE = 'Przystąpienie do postępowania odwoławczego';
const SAMPLE_DESC = 'Pismo wykonawcy zgłaszające przystąpienie do toczącego się postępowania odwoławczego przed KIO po stronie zamawiającego albo odwołującego.';
const SAMPLE_TPL = `{
  "Przystapienie": {
    "data": "2025-10-14", // Data pisma z nagłówka (YYYY-MM-DD).
    "miejscowosc": "Gdańsk", // Miejscowość z nagłówka pisma.
    "sygnatura": "KIO 3812/25", // Sygnatura akt KIO, jeśli podana (np. 'KIO 1234/25').
    "strona": "zamawiajacy", // Po której stronie zgłoszono przystąpienie: "zamawiajacy" lub "odwolujacy".
    "data_odwolania": null // Data wniesienia odwołania, którego dotyczy przystąpienie.
  },
  "Przystepujacy": [
    {
      // Pełna nazwa wykonawcy zgłaszającego przystąpienie.
      "nazwa": "HYDRO-TRANS S.A.",
      "krs": null, // KRS przystępującego.
      "nip": null, // NIP przystępującego.
      "regon": null, // REGON przystępującego.
      "pelnomocnik": {
        "imie_nazwisko": null, // Imię i nazwisko pełnomocnika w mianowniku, bez tytułów.
        "mail": null // Adres e-mail pełnomocnika.
      }
    }
  ],
  "ZamowieniePubliczne": {
    "numer_bzp": null, // Numer ogłoszenia w BZP, format 'YYYY/BZP ########'.
    "numer_postepowania": null, // Numer referencyjny postępowania nadany przez zamawiającego.
    "tytul": null // Nazwa (tytuł) zamówienia.
  }
}`;
const TYPE_OPTS = [['string', 'tekst'], ['date', 'data'], ['integer', 'liczba całk.'], ['number', 'kwota / liczba'], ['enum', 'wybór (enum)'],
  ['object', 'obiekt'], ['array', 'lista obiektów'], ['array_string', 'lista tekstów']];
const NORM_LABEL = { auto: 'auto', none: 'brak', strip: 'tekst (strip)', digits: 'same cyfry', krs: 'KRS', nip: 'NIP', regon: 'REGON',
  pesel: 'PESEL', iban: 'rachunek (IBAN)', bzp: 'nr BZP', ted: 'nr TED', date: 'data', amount: 'kwota', integer: 'liczba', person: 'osoba', city: 'miejscowość' };
const NAME_RE = /^[a-z][a-z0-9_]{1,40}$/;
const STEPS = ['Definicja', 'YAML', 'Test na PDF', 'Zapis'];
const I = {
  x: '<path d="M6 6l12 12M18 6 6 18"/>', back: '<path d="M19 12H5M11 6l-6 6 6 6"/>', next: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  ok: '<path d="m5 12 4.5 4.5L19 7"/>', bad: '<path d="M12 7v6M12 17h.01"/>', plus: '<path d="M12 5v14M5 12h14"/>',
  child: '<path d="M6 4v9a3 3 0 0 0 3 3h9M14 12l4 4-4 4"/>', trash: '<path d="M5 7h14M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  up: '<path d="M12 19V5M6 11l6-6 6 6"/>', save: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>',
  doc: '<rect x="12" y="6" width="30" height="40" rx="6" fill="#fff" stroke="#0b1a20" stroke-width="2"/><path d="M18 17h18M18 24h18M18 31h11" stroke="#c9d1ce" stroke-width="2" stroke-linecap="round"/><circle cx="40" cy="40" r="10" fill="#e8004f"/><path d="M40 35v10M35 40h10" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>',
};
const ic = (n, vb = '0 0 24 24') => `<svg viewBox="${vb}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I[n]}</svg>`;

const S = { step: 1, mode: 'template', name: '', title: '', desc: '', template: '', rows: [], yaml: '', readonly: false, builtin: false,
  editing: null, valid: null, test: null, testing: false, saved: null, meta: null, types: [], draftErr: null, maxStep: 1 };

// ---------- shell ----------
const root = document.createElement('div');
root.id = 'wiz';
root.innerHTML = `<div class="wz-top"><a class="mark" href="/">odwołania <i>→</i> json</a><h1>Nowy typ dokumentu</h1>
  <nav class="wz-steps" id="wzsteps"></nav>
  <button class="iconbtn" id="wzclose" title="Zamknij (Esc)">${ic('x')}</button></div>
  <div class="wz-body" id="wzbody"></div><div class="wz-foot" id="wzfoot"></div>`;
document.body.appendChild(root);
const body = root.querySelector('#wzbody'), foot = root.querySelector('#wzfoot');
const api = (url, opt = {}) => fetch(url, opt).then(async r => {
  const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch { /* text */ }
  if (!r.ok) { const d = j && j.detail; const e = new Error(typeof d === 'string' ? d : (d && d.msg) || t || r.statusText); e.detail = d; e.status = r.status; throw e; }
  return j;
});
const post = (url, data) => api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

function open(reset) {
  root.classList.add('on');
  if (location.hash !== '#nowy-typ') history.replaceState(null, '', '#nowy-typ');
  if (reset) Object.assign(S, { step: 1, yaml: '', readonly: false, builtin: false, editing: null, valid: null, test: null, saved: null, maxStep: 1 });
  loadTypes(); if (!S.meta) api('/api/doctypes/meta').then(m => { S.meta = m; if (S.step === 1) render(); }).catch(() => {});
  render();
}
function close() { root.classList.remove('on'); if (location.hash) history.replaceState(null, '', location.pathname + location.search); }
root.querySelector('#wzclose').onclick = close;
addEventListener('keydown', e => { if (e.key === 'Escape' && root.classList.contains('on') && !e.target.closest('textarea,input')) close(); }, true);
addEventListener('hashchange', () => { if (location.hash === '#nowy-typ') open(); });
window.openWizard = () => open(true);

function loadTypes() {
  return api('/api/doctypes/list').then(l => { S.types = l; registerTypes(l); if (S.step === 1) renderTypes(); }).catch(() => {});
}
// types created in the wizard are first-class in the main view: label, colour dot, approve button, empty-state pill
function registerTypes(l) {
  l.forEach(t => { if (!(t.name in LABEL)) LABEL[t.name] = t.name.charAt(0).toUpperCase() + t.name.slice(1).replaceAll('_', ' '); });
  const pills = document.querySelector('#empty .types');
  if (pills) {
    pills.querySelectorAll('.pill.custom').forEach(p => p.remove());
    const ex = pills.querySelector('[data-ex]');
    l.filter(t => !t.builtin && !t.error).forEach(t => {
      const s = document.createElement('span'); s.className = `pill custom t-${t.name}`; s.title = t.description || '';
      s.innerHTML = `<span class="dot"></span>${esc(t.name.replaceAll('_', ' '))}`; pills.insertBefore(s, ex);
    });
  }
}

function go(step) { if (step > S.maxStep && !(step === 2 && S.yaml)) return; S.step = step; render(); }

function render() {
  S.maxStep = Math.max(S.maxStep, S.step);
  root.querySelector('#wzsteps').innerHTML = STEPS.map((n, i) => {
    const k = i + 1, can = k <= S.maxStep || (k <= 4 && S.yaml && k > 1 && k !== 4) || (k === 4 && S.yaml && !S.readonly);
    return `<button class="${k === S.step ? 'on' : k < S.step ? 'done' : ''}" ${can ? '' : 'disabled'} data-go="${k}"><i>${k < S.step ? '✓' : k}</i><span>${n}</span></button>`;
  }).join('');
  root.querySelectorAll('[data-go]').forEach(b => b.onclick = () => { if (!b.disabled) { S.step = +b.dataset.go; render(); } });
  [null, step1, step2, step3, step4][S.step]();
  body.scrollTop = 0;
}

// ================================================================= step 1: definition
function step1() {
  body.innerHTML = `<div class="wz-grid">
    <div class="card">
      <h2>Opisz nowy typ dokumentu</h2>
      <p class="lead">Wklej szablon JSON w stylu organizatora (wartości przykładowe + komentarze <code>//</code> jako opisy pól) albo zbuduj pola w tabeli. Kreator wygeneruje plik YAML — typ zacznie działać bez przebudowy systemu.</p>
      <div class="fgrid">
        <div class="fld"><label>Nazwa techniczna <small>(plik YAML)</small></label><input class="inp mono" id="wzname" placeholder="np. faktura" value="${esc(S.name)}" autocomplete="off" spellcheck="false"></div>
        <div class="fld"><label>Nazwa dokumentu <small>— z niej powstają słowa kluczowe klasyfikatora</small></label><input class="inp" id="wztitle" placeholder="np. Przystąpienie do postępowania odwoławczego" value="${esc(S.title)}"></div>
        <div class="fld full"><label>Opis typu <small>— czytany przez klasyfikator LLM; napisz też, czym ten dokument <i>nie</i> jest</small></label><input class="inp" id="wzdesc" placeholder="np. Pismo wykonawcy zgłaszające przystąpienie do postępowania odwoławczego…" value="${esc(S.desc)}"></div>
      </div>
      <div class="seg"><button data-mode="template" class="${S.mode === 'template' ? 'on' : ''}">Szablon JSON</button><button data-mode="table" class="${S.mode === 'table' ? 'on' : ''}">Tabela pól</button></div>
      <div id="wzmode"></div>
      ${S.draftErr ? `<div class="errbox">${esc(S.draftErr)}</div>` : ''}
    </div>
    <div class="card"><h3>Istniejące typy</h3><div class="tlist" id="wztypes"></div>
      <div class="howto"><b>Jak to działa</b><ol><li>Szablon lub tabela → YAML ze schematem, normalizatorami i słowami kluczowymi.</li><li>Walidacja na żywo, tak jak ładuje go potok.</li><li>Test na przykładowym PDF bez zapisywania.</li><li>Zapis do <code>config/doctypes/</code> — klasyfikacja i ekstrakcja od razu.</li></ol></div></div>
  </div>`;
  const bind = (id, k) => { const el = body.querySelector(id); el.oninput = () => { S[k] = el.value; if (k === 'name') checkName(); }; };
  bind('#wzname', 'name'); bind('#wztitle', 'title'); bind('#wzdesc', 'desc');
  body.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => { S.mode = b.dataset.mode; S.draftErr = null; step1(); });
  renderMode(); renderTypes(); checkName();
  foot.innerHTML = `<span class="msg" id="wzmsg"></span><span class="sp"></span>
    <button class="btn2 p" id="wzgen">Generuj YAML ${ic('next')}</button>`;
  foot.querySelector('#wzgen').onclick = generate;
}
function checkName() {
  const el = body.querySelector('#wzname'); const ok = !S.name || NAME_RE.test(S.name);
  el.classList.toggle('bad', !ok);
  const m = foot.querySelector('#wzmsg');
  if (m) m.textContent = ok ? (S.types.some(t => t.name === S.name) ? `Typ „${S.name}” już istnieje — zapis go zaktualizuje.` : '') : 'Nazwa: małe litery, cyfry i _, zaczyna się literą.';
}
function renderMode() {
  const box = body.querySelector('#wzmode');
  if (S.mode === 'template') {
    box.innerHTML = `<div class="tplbar"><span class="hint">Typy pól z wartości przykładowych (data ISO → date, liczby, listy obiektów), normalizatory z nazw pól (nip, krs, regon, pesel, rachunek, data, kwota, bzp, ted, imie_nazwisko).</span><span class="sp"></span>
      <button class="lnk" id="wzsample">Wstaw przykład: przystąpienie</button></div>
      <textarea class="tpl" id="wztpl" spellcheck="false" placeholder='{\n  "Faktura": {\n    "numer": "FV/12/2025", // Numer faktury.\n    "data_wystawienia": "2025-10-01", // Data wystawienia.\n    "nip_sprzedawcy": null, // NIP sprzedawcy.\n    "kwota_brutto": 1230.00 // Kwota brutto.\n  }\n}'>${esc(S.template)}</textarea>`;
    const ta = box.querySelector('#wztpl'); ta.oninput = () => { S.template = ta.value; };
    ta.addEventListener('keydown', e => { if (e.key === 'Tab') { e.preventDefault(); document.execCommand('insertText', false, '  '); } });
    box.querySelector('#wzsample').onclick = () => {
      S.template = SAMPLE_TPL; if (!S.name) S.name = SAMPLE_NAME; if (!S.title) S.title = SAMPLE_TITLE; if (!S.desc) S.desc = SAMPLE_DESC; step1();
    };
  } else {
    if (!S.rows.length) S.rows = [{ name: '', type: 'string', normalize: 'auto', description: '' }];
    renderTable();
  }
}
function renderTypes() {
  const el = body.querySelector('#wztypes'); if (!el) return;
  el.innerHTML = S.types.length ? S.types.map(t => `<button class="trow t-${esc(t.name)}" data-open="${esc(t.name)}"><span class="dot"></span>
    <div><b>${esc(t.name)}<span class="badge2 ${t.builtin ? '' : 'own'}">${t.builtin ? 'wbudowany' : 'własny'}</span></b><small>${esc(t.error ? 'Błąd pliku: ' + t.error : t.description)}</small></div></button>`).join('') : '<div class="note">Wczytywanie…</div>';
  el.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openExisting(b.dataset.open));
}
function openExisting(name) {
  api(`/api/doctypes/${encodeURIComponent(name)}/yaml`).then(r => {
    Object.assign(S, { yaml: r.yaml, readonly: r.builtin, builtin: r.builtin, editing: r.builtin ? null : name, name, test: null, saved: null, step: 2, maxStep: r.builtin ? 2 : 4 });
    render();
  }).catch(e => toast('Nie udało się wczytać: ' + e.message));
}

// ---------- field table ----------
function renderTable() {
  const box = body.querySelector('#wzmode');
  const norms = ['auto', 'none', ...((S.meta && S.meta.normalizers) || Object.keys(NORM_LABEL).filter(k => k !== 'auto' && k !== 'none'))];
  const rowsHtml = (rows, depth, path) => rows.map((r, i) => {
    const p = [...path, i].join('.'), nested = r.type === 'object' || r.type === 'array';
    return `<div class="ft-r" data-p="${p}">
      <div class="nm"><span class="ind">${depth ? '&nbsp;'.repeat(depth * 3) + '└' : ''}</span><input class="inp mono" data-k="name" value="${esc(r.name)}" placeholder="nazwa_pola" spellcheck="false"></div>
      <select data-k="type">${TYPE_OPTS.map(([v, l]) => `<option value="${v}" ${r.type === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <select data-k="normalize" ${nested || r.type === 'enum' || r.type === 'array_string' ? 'disabled' : ''} title="Normalizator (o2j/normalize.py)">${norms.map(n => `<option value="${n}" ${(r.normalize || 'auto') === n ? 'selected' : ''}>${NORM_LABEL[n] || n}</option>`).join('')}</select>
      <input class="inp" data-k="description" value="${esc(r.description)}" placeholder="${nested ? 'opis grupy (opcjonalnie)' : 'opis dla modelu — co wpisać, skąd wziąć'}">
      <div class="acts">${nested ? `<button data-act="child" title="Dodaj pole podrzędne">${ic('child')}</button>` : ''}<button data-act="del" title="Usuń pole">${ic('trash')}</button></div>
      ${r.type === 'enum' ? `<input class="inp enumv mono" data-k="values" value="${esc(r.values || '')}" placeholder="wartości: 1=tak, 0=nie  lub  osoba_prawna, osoba_fizyczna">` : ''}
    </div>` + (nested ? rowsHtml(r.children || [], depth + 1, [...path, i, 'c']) : '');
  }).join('');
  box.innerHTML = `<div class="ft"><div class="ft-h"><span>Pole</span><span>Typ</span><span>Normalizacja</span><span>Opis</span><span></span></div>
    ${S.rows.length ? rowsHtml(S.rows, 0, []) : '<div class="ft-empty">Brak pól</div>'}
    <div class="ft-add"><button data-act="add">+ pole</button><button data-act="addobj">+ grupa (obiekt)</button><button data-act="addlist">+ lista obiektów</button></div></div>`;
  const find = p => { const parts = p.split('.'); let arr = S.rows, idx; for (let k = 0; k < parts.length; k++) {
    if (parts[k] === 'c') continue; idx = +parts[k]; if (k < parts.length - 1) { arr[idx].children = arr[idx].children || []; arr = arr[idx].children; k++; } }
    return [arr, idx]; };
  box.querySelectorAll('.ft-r').forEach(rowEl => {
    const [arr, idx] = find(rowEl.dataset.p);
    rowEl.querySelectorAll('[data-k]').forEach(inp => {
      inp.addEventListener(inp.tagName === 'SELECT' ? 'change' : 'input', () => {
        arr[idx][inp.dataset.k] = inp.value;
        if (inp.dataset.k === 'type') { if ((inp.value === 'object' || inp.value === 'array') && !(arr[idx].children || []).length) arr[idx].children = [{ name: '', type: 'string', normalize: 'auto', description: '' }]; renderTable(); }
      });
    });
    rowEl.querySelectorAll('[data-act]').forEach(b => b.onclick = () => {
      if (b.dataset.act === 'del') arr.splice(idx, 1);
      else (arr[idx].children = arr[idx].children || []).push({ name: '', type: 'string', normalize: 'auto', description: '' });
      renderTable();
    });
  });
  box.querySelectorAll('.ft-add [data-act]').forEach(b => b.onclick = () => {
    const a = b.dataset.act;
    S.rows.push(a === 'add' ? { name: '', type: 'string', normalize: 'auto', description: '' }
      : { name: '', type: a === 'addobj' ? 'object' : 'array', description: '', children: [{ name: '', type: 'string', normalize: 'auto', description: '' }] });
    renderTable(); const last = box.querySelectorAll('.ft-r [data-k="name"]'); (a === 'add' ? last[last.length - 1] : last[last.length - 2])?.focus();
  });
}

function generate() {
  S.draftErr = null;
  if (!NAME_RE.test(S.name)) { S.draftErr = 'Podaj nazwę techniczną: małe litery, cyfry i _, np. faktura.'; return step1(); }
  const payload = { name: S.name, title: S.title, description: S.desc };
  if (S.mode === 'template') { if (!S.template.trim()) { S.draftErr = 'Wklej szablon JSON albo przełącz na tabelę pól.'; return step1(); } payload.template = S.template; }
  else payload.fields = S.rows;
  const b = foot.querySelector('#wzgen'); b.disabled = true; b.innerHTML = '<span class="spin" style="--c:#fff"></span> Generuję…';
  post('/api/doctypes/draft', payload).then(r => {
    Object.assign(S, { yaml: r.yaml, valid: r.validation, readonly: false, builtin: false, test: null, saved: null, step: 2, maxStep: 3 });
    S.editing = S.types.some(t => t.name === S.name && !t.builtin) ? S.name : null;
    render();
  }).catch(e => { S.draftErr = e.detail && e.detail.line ? `${e.message} (linia ${e.detail.line})` : e.message; step1(); });
}

// ================================================================= step 2: YAML editor + live validation
function hlYaml(src, bad) {
  return src.split('\n').map((ln, i) => {
    let q = null, cut = -1;  // YAML comment: '#' at line start or after whitespace, outside quotes
    for (let k = 0; k < ln.length; k++) {
      const c = ln[k];
      if (q) { if (c === q) q = null; continue; }
      if ((c === "'" || c === '"') && (k === 0 || /[\s:{\[,]/.test(ln[k - 1]))) q = c;
      else if (c === '#' && (k === 0 || /\s/.test(ln[k - 1]))) { cut = k; break; }
    }
    let h = esc(cut >= 0 ? ln.slice(0, cut) : ln);
    const comment = cut >= 0 ? esc(ln.slice(cut)) : '';
    h = h.replace(/^(\s*-?\s*)([\w\-\\.()|?*+\[\]{}ĄĆĘŁŃÓŚŹŻąćęłńóśźż' ]+?)(:)(?=\s|$)/, (m, a, k, c) => `${a}<span class="yk">${k}</span><span class="yp">${c}</span>`)
      .replace(/(\{|, )([a-z_]+)(:)/g, '$1<span class="yk">$2</span>$3')
      .replace(/'[^']*'|&quot;.*?&quot;/g, '<span class="ys">$&</span>')
      .replace(/(:<\/span>\s|:\s|\[|, )(-?\d+(?:\.\d+)?)(?=[,\]\}\s]|$)/g, '$1<span class="yn">$2</span>')
      .replace(/\b(true|false|null)\b/g, '<span class="yb">$1</span>');
    h += comment ? `<span class="yc">${comment}</span>` : '';
    return bad.has(i + 1) ? `<span class="lnerr">${h || ' '}</span>` : h;
  }).join('\n') + '\n';
}
let vTimer = null, vSeq = 0;
function step2() {
  const ro = S.readonly;
  body.innerHTML = `<div class="wz-grid two">
    <div class="edwrap">
      ${ro ? `<div class="ro-banner"><span><b>Typ wbudowany „${esc(S.name)}”</b> — tylko do odczytu (dane konkursowe UZP). Możesz go skopiować i zmienić kopię.</span><span class="sp"></span><button class="btn2" id="wzdup">Duplikuj jako nowy typ</button></div>`
        : S.editing ? `<div class="ro-banner" style="background:#f3e8ff;color:#6b21a8"><span><b>Edycja typu „${esc(S.editing)}”</b> — zapis nadpisze config/doctypes/${esc(S.editing)}.yaml.</span><span class="sp"></span><button class="btn2 danger" id="wzdel">${ic('trash')} Usuń typ</button></div>` : ''}
      <div class="ed ${ro ? 'ro' : ''}"><div class="gut" id="wzgut"></div><div class="area"><pre id="wzhl"></pre><textarea id="wzyaml" spellcheck="false" ${ro ? 'readonly' : ''}></textarea></div></div>
    </div>
    <div class="side">
      <div class="card"><div id="wzvstat"></div><div class="vlist" id="wzvlist"></div><div class="kpis" id="wzkpis"></div></div>
      <div class="card"><h3>Podgląd wyniku (szkielet JSON)</h3><div class="skel" id="wzskel"></div>
        <p class="note" style="margin:10px 0 0">Klucze, kolejność i null-e takie, jakie zwróci potok. Dostępne typy: string, date, integer, number, enum, object, array. Normalizatory: ${esc(((S.meta && S.meta.normalizers) || []).join(', ') || 'nip, krs, regon, pesel, iban, bzp, ted, date, amount, person, city…')}.</p></div>
    </div></div>`;
  const ta = body.querySelector('#wzyaml'), hl = body.querySelector('#wzhl'), gut = body.querySelector('#wzgut');
  ta.value = S.yaml;
  const paint = () => {
    const bad = new Set(((S.valid && S.valid.errors) || []).map(e => e.line).filter(Boolean));
    const warn = new Set(((S.valid && S.valid.warnings) || []).map(e => e.line).filter(Boolean));
    hl.innerHTML = hlYaml(ta.value, bad);
    const n = ta.value.split('\n').length;
    gut.innerHTML = Array.from({ length: n }, (_, i) => `<div class="${bad.has(i + 1) ? 'err' : warn.has(i + 1) ? 'wrn' : ''}">${i + 1}</div>`).join('') + '<div>&nbsp;</div>';
    hl.scrollTop = ta.scrollTop; hl.scrollLeft = ta.scrollLeft; gut.scrollTop = ta.scrollTop;
  };
  ta.addEventListener('scroll', () => { hl.scrollTop = ta.scrollTop; hl.scrollLeft = ta.scrollLeft; gut.scrollTop = ta.scrollTop; });
  ta.addEventListener('input', () => { S.yaml = ta.value; S.test = null; paint(); clearTimeout(vTimer); vTimer = setTimeout(validate, 350); showValid('wait'); });
  ta.addEventListener('keydown', e => { if (e.key === 'Tab' && !ro) { e.preventDefault(); document.execCommand('insertText', false, '  '); } });
  S._paint = paint; S._ta = ta;
  paint(); validate();
  if (ro) body.querySelector('#wzdup').onclick = () => {
    const nn = S.name + '_kopia';
    S.yaml = S.yaml.replace(/^name:\s*.*$/m, `name: ${nn}`); Object.assign(S, { name: nn, readonly: false, builtin: false, editing: null, maxStep: 3 }); render();
    toast(`Skopiowano jako „${nn}” — zmień nazwę i pola`);
  };
  const del = body.querySelector('#wzdel');
  if (del) del.onclick = () => {
    if (!confirm(`Usunąć typ „${S.editing}”? Plik config/doctypes/${S.editing}.yaml zostanie skasowany.`)) return;
    api(`/api/doctypes/${encodeURIComponent(S.editing)}`, { method: 'DELETE' }).then(() => {
      toast(`Usunięto typ „${S.editing}”`); delete LABEL[S.editing]; Object.assign(S, { editing: null, yaml: '', step: 1, maxStep: 1 }); loadTypes(); render();
    }).catch(e => toast('Błąd: ' + e.message));
  };
  foot.innerHTML = `<button class="btn2 ghost" id="wzb">${ic('back')} Definicja</button><span class="msg" id="wzmsg"></span><span class="sp"></span>
    ${ro ? '' : `<button class="btn2" id="wzsave">${ic('save')} Zapisz bez testu</button><button class="btn2 p" id="wzn">Test na PDF ${ic('next')}</button>`}`;
  foot.querySelector('#wzb').onclick = () => go(1);
  if (!ro) { foot.querySelector('#wzn').onclick = () => { if (S.valid && S.valid.ok) { S.step = 3; render(); } else toast('Najpierw popraw błędy w YAML'); };
    foot.querySelector('#wzsave').onclick = () => { if (S.valid && S.valid.ok) { S.maxStep = 4; S.step = 4; render(); } else toast('Najpierw popraw błędy w YAML'); }; }
}
function validate() {
  const seq = ++vSeq;
  post('/api/doctypes/validate', { yaml: S.yaml }).then(v => { if (seq !== vSeq) return; S.valid = v; if (v.name) S.name = v.name; showValid(); S._paint && S._paint(); })
    .catch(e => { if (seq === vSeq) { S.valid = { ok: false, errors: [{ line: null, msg: e.message }], warnings: [] }; showValid(); } });
}
function showValid(state) {
  const st = body.querySelector('#wzvstat'); if (!st) return;
  const v = S.valid;
  if (state === 'wait' || !v) { st.innerHTML = `<div class="vstat wait"><span class="ic"><span class="spin" style="--c:#fff;border-color:rgba(255,255,255,.3)"></span></span><div>Sprawdzam…<small>walidacja jak przy ładowaniu potoku</small></div></div>`; return; }
  const ok = v.ok;
  st.innerHTML = `<div class="vstat ${ok ? 'ok' : 'bad'}"><span class="ic">${ic(ok ? 'ok' : 'bad')}</span><div>${ok ? 'Specyfikacja poprawna' : `${v.errors.length} ${v.errors.length === 1 ? 'błąd' : v.errors.length < 5 ? 'błędy' : 'błędów'}`}
    <small>${ok ? 'ładuje się w o2j.spec, schemat JSON i szkielet wygenerowane' : 'kliknij, aby przejść do linii'}</small></div></div>`;
  const items = [...v.errors.map(e => ({ ...e, k: 'e' })), ...v.warnings.filter(w => !(S.readonly && w.path === 'name')).map(e => ({ ...e, k: 'w' }))];
  body.querySelector('#wzvlist').innerHTML = items.slice(0, 30).map(e => `<button class="vit ${e.k}" data-line="${e.line || ''}"><span class="ln">${e.line ? 'L' + e.line : '—'}</span><span>${esc(e.msg)}</span></button>`).join('');
  body.querySelectorAll('.vit[data-line]').forEach(b => b.onclick = () => jump(+b.dataset.line));
  const sp = v.spec;
  body.querySelector('#wzkpis').innerHTML = sp ? `<div class="kpi"><b>${sp.fields}</b><small>pól</small></div><div class="kpi"><b>${sp.keywords}</b><small>słów kluczowych</small></div><div class="kpi"><b>${Object.keys(sp.skeleton).length}</b><small>sekcji</small></div>` : '';
  body.querySelector('#wzskel').innerHTML = sp ? `<pre class="json">${hjson(sp.preview || sp.skeleton, 0)}</pre>` : '<p class="note" style="padding:12px">Podgląd pojawi się po usunięciu błędów.</p>';
}
function jump(line) {
  const ta = S._ta; if (!ta || !line) return;
  const lines = ta.value.split('\n'); const a = lines.slice(0, line - 1).join('\n').length + (line > 1 ? 1 : 0);
  ta.focus(); ta.setSelectionRange(a, a + lines[line - 1].length);
  ta.scrollTop = Math.max(0, (line - 6) * 20);
}

// ================================================================= step 3: test on a sample PDF (draft spec, nothing saved)
function step3() {
  foot.innerHTML = `<button class="btn2 ghost" id="wzb">${ic('back')} YAML</button><span class="msg" id="wzmsg">Szkic nie jest zapisywany — test używa YAML z edytora.</span><span class="sp"></span>
    ${S.test && !S.testing ? '<button class="btn2" id="wzagain">Inny PDF</button>' : ''}<button class="btn2 p" id="wzn">Dalej: zapis ${ic('next')}</button>`;
  foot.querySelector('#wzb').onclick = () => go(2);
  foot.querySelector('#wzn').onclick = () => { S.maxStep = 4; S.step = 4; render(); };
  const again = foot.querySelector('#wzagain'); if (again) again.onclick = () => { S.test = null; step3(); };
  if (S.testing) { body.innerHTML = `<div class="busy"><span class="spin"></span><b>Ekstrakcja szkicem „${esc(S.name)}”…</b><span class="note">tekst PDF → prompt ze specyfikacji → LLM (JSON Schema) → normalizacja → dowody</span></div>`; return; }
  if (!S.test) {
    body.innerHTML = `<div class="tdrop" id="wzdrop"><svg viewBox="0 0 54 54">${I.doc}</svg><b>Upuść przykładowy PDF typu „${esc(S.name)}”</b>
      <small>lub kliknij · jedno wywołanie modelu z profilu domyślnego, wynik z dowodami jak w głównym widoku</small></div>
      <p class="note" style="text-align:center;margin-top:14px">Zobaczysz też, czy reguły klasyfikacji wskażą nowy typ na tle istniejących.</p>
      <input type="file" id="wzfile" accept=".pdf" hidden>`;
    const drop = body.querySelector('#wzdrop'), inp = body.querySelector('#wzfile');
    drop.onclick = () => inp.click();
    inp.onchange = () => inp.files[0] && runTest(inp.files[0]);
    drop.addEventListener('dragover', e => { e.preventDefault(); e.stopPropagation(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', e => { e.preventDefault(); e.stopPropagation(); drop.classList.remove('over'); const f = [...e.dataTransfer.files].find(f => /\.pdf$/i.test(f.name)); if (f) runTest(f); });
    return;
  }
  renderTest();
}
function runTest(file) {
  S.testing = true; S.testFile = file; step3();
  const fd = new FormData(); fd.append('file', file); fd.append('yaml', S.yaml);
  api('/api/doctypes/test', { method: 'POST', body: fd }).then(r => { S.test = r; })
    .catch(e => { S.test = null; toast('Test nieudany: ' + e.message); })
    .finally(() => { S.testing = false; if (S.step === 3) step3(); });
}
function renderTest() {
  const d = S.test, t = d.trace, ev = {}; (t.evidence || []).forEach(e => ev[e.field] = e);
  const cls = t.classification || {}, scores = Object.entries(cls.scores || {}), mx = Math.max(1, ...scores.map(s => s[1]));
  const short = m => esc(String(m || '').split('/').pop());
  const chips = [`${t.pages} str.`, `${t.elapsed_s}s`, short(t.model)];
  if (t.cost_usd) chips.push(`$${t.cost_usd.toFixed(4)}`);
  if (t.ocr_pages && t.ocr_pages.length) chips.push('OCR');
  const filled = (t.evidence || []).length, located = (t.evidence || []).filter(e => e.method === 'located').length;
  body.innerHTML = `<div class="tsplit"><div class="tdoc" id="wzdoc">${Array.from({ length: t.pages || 1 }, (_, k) =>
    `<div class="page" id="wzp${k + 1}"><img loading="lazy" src="/api/page/${d.session}/${encodeURIComponent(d.file)}/${k + 1}.png" alt=""><span class="pn">${k + 1}/${t.pages}</span></div>`).join('')}</div>
    <div class="tres"><div class="rhead">
      <div class="rtitle t-${esc(d.doctype)}"><span class="dot" style="width:11px;height:11px"></span><h2>${esc(d.doctype)}</h2><span class="badge2 own">szkic</span>
        <div class="sw"><button class="${wview === 'dane' ? 'on' : ''}" data-v="dane">Dane</button><button class="${wview === 'json' ? 'on' : ''}" data-v="json">JSON</button></div></div>
      <div class="chips">${chips.map(c => `<span class="chip">${c}</span>`).join('')}<span class="chip">${located}/${filled} wartości z cytatem</span></div>
      <div><div class="note" style="margin-bottom:6px">Klasyfikacja regułami (bez LLM): ${cls.confident ? `<b style="color:var(--ok)">pewnie „${esc(cls.best)}”</b>` : cls.best === d.doctype ? `<b style="color:var(--warn)">„${esc(cls.best)}”, ale z małym marginesem — zdecyduje LLM z opisu</b>` : `<b style="color:#b91c1c">wygrywa „${esc(cls.best)}” — dodaj słowa kluczowe</b>`}</div>
        <div class="clsbars">${scores.slice(0, 5).map(([n, s]) => `<div class="clsbar ${n === d.doctype ? 'me' : ''}"><span>${esc(n)}</span><span class="bar"><i style="width:${Math.max(2, s / mx * 100)}%"></i></span><span class="n">${s}</span></div>`).join('')}</div></div>
    </div><div class="rbody" id="wzrbody"></div></div></div>`;
  body.querySelectorAll('[data-v]').forEach(b => b.onclick = () => { wview = b.dataset.v; renderTest(); });
  const rb = body.querySelector('#wzrbody');
  const issues = t.issues || [];
  rb.innerHTML = wview === 'json' ? `<pre class="json">${hjson(d.result, 0)}</pre>` :
    (issues.length ? `<div class="fixes" style="background:#fffbeb;color:#78350f"><b>Walidatory zgłosiły ${issues.length} ${issues.length === 1 ? 'uwagę' : 'uwagi'}</b> (po zapisie pętla naprawy poprawi je automatycznie):${issues.map(i => `<div>${esc(i.field)}: ${esc(i.issue)}</div>`).join('')}</div>` : '<div class="okline" style="margin:8px 12px">✓ Wszystkie walidatory (format, jedna osoba, obecność w tekście) przeszły.</div>') +
    wfields(d.result, '', ev, 0);
  rb.querySelectorAll('.row').forEach(r => r.onclick = () => wpick(r, ev));
}
let wview = 'dane';
function wfields(obj, path, ev, depth) {
  let h = '';
  for (const [k, v] of Object.entries(obj || {})) {
    const p = path ? `${path}.${k}` : k;
    if (Array.isArray(v)) {
      if (!v.length) { h += `<div class="sec">${esc(k)}</div><div class="row"><span class="k">—</span><span class="v null">brak</span></div>`; continue; }
      v.forEach((it, i) => { h += `<div class="sec">${esc(k)}${v.length > 1 ? ' ' + (i + 1) : ''}</div>` + (it && typeof it === 'object' ? wfields(it, `${p}[${i}]`, ev, depth + 1) : wrow(`${p}[${i}]`, k, it, ev)); });
    } else if (v && typeof v === 'object') h += `<div class="${depth ? 'sub' : 'sec'}">${esc(k)}</div>` + wfields(v, p, ev, depth + 1);
    else h += wrow(p, k, v, ev);
  }
  return h;
}
function wrow(p, k, v, ev) {
  const e = ev[p];
  const evt = !e ? 'Brak w dokumencie.' : e.method === 'derived' ? 'Wyznaczone regułą z konfiguracji.' : e.method === 'inferred' ? 'Wywnioskowane przez model (brak dosłownego cytatu).'
    : `str. ${e.page} · „…${esc(e.context).replace(esc(e.quote), `<mark>${esc(e.quote)}</mark>`)}…”`;
  return `<div class="row" data-p="${esc(p)}"><span class="k">${esc(KEY[k] || k.replaceAll('_', ' '))}</span><span class="v ${v === null ? 'null' : ''}">${v === null ? '—' : esc(v)}</span>
    <span class="dot ${e ? 'm-' + e.method : ''}" style="${e ? '' : 'opacity:0'}"></span><div class="ev">${evt}</div></div>`;
}
function wpick(el, ev) {
  body.querySelectorAll('#wzrbody .row.on').forEach(r => r !== el && r.classList.remove('on'));
  el.classList.toggle('on'); body.querySelectorAll('#wzdoc .hl').forEach(h => h.remove());
  if (!el.classList.contains('on')) return;
  const e = ev[el.dataset.p]; if (!e || !e.page) return;
  const pg = body.querySelector('#wzp' + e.page); if (!pg) return;
  (e.rects || []).forEach(([x, y, w, h]) => { const d = document.createElement('div'); d.className = 'hl'; Object.assign(d.style, { left: x + '%', top: y + '%', width: w + '%', height: h + '%' }); pg.appendChild(d); });
  const first = pg.querySelector('.hl'), doc = body.querySelector('#wzdoc');
  doc.scrollTo({ top: pg.offsetTop + (first ? first.offsetTop - doc.clientHeight / 3 : 0), behavior: 'smooth' });
}

// ================================================================= step 4: save
function step4() {
  const v = S.valid || {}, sp = v.spec || {};
  const builtin = (S.meta && S.meta.builtin || ['odwolanie', 'pelnomocnictwo', 'przelew']).includes(S.name);
  const exists = S.types.some(t => t.name === S.name);
  if (S.saved) {
    body.innerHTML = `<div class="card savecard"><div class="done-hero"><div class="big">${ic('ok')}</div><h2>Typ „${esc(S.saved.name)}” jest aktywny</h2>
      <p class="lead" style="margin:6px auto 0">Zapisano <code>${esc(S.saved.file)}</code>. Klasyfikator i ekstrakcja używają go od razu — bez restartu i bez zmian w kodzie. Wgraj dokument w aplikacji albo wrzuć go do <code>input/</code> dla CLI.</p></div></div>`;
    foot.innerHTML = `<button class="btn2 ghost" id="wznew">Utwórz kolejny typ</button><span class="sp"></span>
      ${S.testFile ? `<button class="btn2" id="wzrun" title="Pełny potok: klasyfikacja (reguły + LLM) → ekstrakcja → weryfikacja">Przetwórz ${esc(S.testFile.name)} w aplikacji</button>` : ''}
      <button class="btn2 p" id="wzapp">Przejdź do aplikacji ${ic('next')}</button>`;
    const run = foot.querySelector('#wzrun');
    if (run) run.onclick = () => { close(); add([S.testFile]); };
    foot.querySelector('#wznew').onclick = () => { Object.assign(S, { name: '', title: '', desc: '', template: '', rows: [], yaml: '', saved: null, test: null, editing: null, step: 1, maxStep: 1 }); render(); };
    foot.querySelector('#wzapp').onclick = () => { close(); toast(`Typ „${S.saved.name}” gotowy — wgraj PDF`); };
    return;
  }
  const tested = S.test ? `przetestowany na ${esc(S.test.file)} (${(S.test.trace.evidence || []).filter(e => e.method === 'located').length} wartości z cytatem)` : 'nie testowano';
  body.innerHTML = `<div class="card savecard"><h2>Zapis typu dokumentu</h2><p class="lead">Plik trafi do <code>config/doctypes/</code>. To ten sam format, który czyta potok CLI (<code>run.py</code>) i GUI.</p>
    <div class="sumrow"><span>Nazwa</span><b>${esc(S.name)}</b></div>
    <div class="sumrow"><span>Plik</span><code>config/doctypes/${esc(S.name)}.yaml</code></div>
    <div class="sumrow"><span>Pola</span><span style="color:var(--ink)">${sp.fields ?? '—'} pól · ${sp.keywords ?? 0} słów kluczowych klasyfikatora</span></div>
    <div class="sumrow"><span>Test</span><span style="color:var(--ink)">${tested}</span></div>
    <div class="sumrow"><span>Status</span><span style="color:var(--ink)">${v.ok ? '✓ specyfikacja poprawna' : '✗ specyfikacja zawiera błędy'}${exists ? ' · typ istnieje — zostanie zaktualizowany' : ' · nowy typ'}</span></div>
    ${builtin ? `<label class="chk2"><input type="checkbox" id="wzforce"> Rozumiem, że nadpisuję typ wbudowany „${esc(S.name)}” (dane konkursowe UZP)</label>` : ''}
  </div>`;
  foot.innerHTML = `<button class="btn2 ghost" id="wzb">${ic('back')} ${S.test ? 'Test' : 'YAML'}</button><span class="msg" id="wzmsg"></span><span class="sp"></span>
    <button class="btn2 a" id="wzsave" ${v.ok ? '' : 'disabled'}>${ic('save')} Zapisz i aktywuj</button>`;
  foot.querySelector('#wzb').onclick = () => go(S.test ? 3 : 2);
  foot.querySelector('#wzsave').onclick = () => {
    const force = body.querySelector('#wzforce');
    if (builtin && !(force && force.checked)) { foot.querySelector('#wzmsg').textContent = 'Zaznacz zgodę na nadpisanie typu wbudowanego.'; return; }
    const b = foot.querySelector('#wzsave'); b.disabled = true; b.innerHTML = '<span class="spin" style="--c:#fff"></span> Zapisuję…';
    post('/api/doctypes', { yaml: S.yaml, overwrite: exists, overwrite_builtin: builtin && force && force.checked })
      .then(r => { S.saved = r; S.editing = r.name; loadTypes(); fetch('/api/doctypes').catch(() => {}); step4(); })
      .catch(e => { b.disabled = false; b.innerHTML = `${ic('save')} Zapisz i aktywuj`; foot.querySelector('#wzmsg').textContent = e.message; });
  };
}

// ---------- boot ----------
loadTypes();
if (location.hash === '#nowy-typ') open(true);
document.addEventListener('click', e => { const b = e.target.closest('[data-wizard]'); if (b) { e.preventDefault(); open(true); } });
})();
