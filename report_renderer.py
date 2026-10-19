"""Portable offline report renderer. Assets are bundled, never fetched at page load."""
import json
from pathlib import Path


def render_report(before, after, difference):
    assets = Path(__file__).with_name('report_assets')
    # Only removed records and precise field changes require old data in the browser.
    try:
        from version_compare import changes
    except ImportError:
        from compare import changes
    entries = []
    for category in ('operators', 'modules'):
        for status in ('added', 'changed', 'removed'):
            for key in difference[category][status]:
                source = before if status == 'removed' else after
                entries.append({'category': category, 'status': status, 'id': key,
                                'record': source[category][key], 'version': source['version'],
                                'changes': changes(before[category][key], after[category][key]) if status == 'changed' else []})
    payload = {'current': after, 'previous': before['version'] if before else None,
               'difference': difference, 'entries': entries}
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    data = data.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (assets / 'report.html').read_text(encoding='utf-8')
    css = (assets / 'report.css').read_text(encoding='utf-8')
    script = (assets / 'report.js').read_text(encoding='utf-8')
    library = (assets / 'html2canvas.min.js').read_text(encoding='utf-8')
    license_text = (assets / 'html2canvas.LICENSE').read_text(encoding='utf-8')
    return (template.replace('__CSS__', css).replace('__DATA__', data)
            .replace('__LIBRARY__', '/* html2canvas 1.4.1\n' + license_text + '\n*/\n' + library)
            .replace('__SCRIPT__', script))
