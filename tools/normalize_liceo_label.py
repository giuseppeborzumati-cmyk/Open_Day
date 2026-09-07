from pathlib import Path

path = Path('index.html')
text = path.read_text(encoding='utf-8')

old = 'LS - Liceo Scientifico opzione Scienze Applicate & Liceo Scienze Applicate - Curvatura Economica'
old_entity = 'LS - Liceo Scientifico opzione Scienze Applicate &amp; Liceo Scienze Applicate - Curvatura Economica'
new = 'LS - Liceo Scientifico opzione Scienze Applicate e Liceo Scienze Applicate - Curvatura Economica'

text = text.replace(old_entity, new).replace(old, new)
text = text.replace(new + '/h4>', new + '</h4>')

old_fn = """    function canonicalOpenDayStudyPath(value) {
      return String(value || '').replace(/Curvatura Economia/g, 'Curvatura Economica');
    }"""
new_fn = """    function canonicalOpenDayStudyPath(value) {
      let normalized = String(value || '').replace(/Curvatura Economia/g, 'Curvatura Economica');
      if (/Liceo Scientifico/i.test(normalized) && /Curvatura Economica/i.test(normalized)) {
        const amp = String.fromCharCode(38);
        normalized = normalized.split(amp + 'amp;').join(' e ').split(amp).join(' e ');
        normalized = normalized.replace(/\\s+/g, ' ').trim();
        if (/^LS\\s*-\\s*Liceo Scientifico opzione Scienze Applicate\\s+e\\s+Liceo Scienze Applicate\\s*-\\s*Curvatura Economica$/i.test(normalized)) {
          normalized = 'LS - Liceo Scientifico opzione Scienze Applicate e Liceo Scienze Applicate - Curvatura Economica';
        }
      }
      return normalized;
    }"""

if old_fn not in text:
    raise SystemExit('canonicalOpenDayStudyPath: blocco atteso non trovato')
text = text.replace(old_fn, new_fn, 1)

assert old not in text
assert old_entity not in text
assert new in text
assert new + '/h4>' not in text
assert new + '</h4>' in text

path.write_text(text, encoding='utf-8')
print('OPEN_DAY_LICEO_LABEL_OK', text.count(new))
