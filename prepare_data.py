"""Prepare ASL-LEX once. Python standard library only; originals are never overwritten."""
import csv
import io
import json
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'sources'
TOP_COUNT = 200
MISSING = {'', 'NA', 'N/A', 'NaN', 'nan', 'NULL', 'null'}  # None is a real movement code!
CSV_URL = 'https://osf.io/download/9nygd'
KEY_URL = 'https://osf.io/download/ygq4v'
REPO = 'https://raw.githubusercontent.com/ASL-LEX/asl-lex/'
DETAILS = ['SignType', 'Handshape', 'SelectedFingers', 'Movement', 'RepeatedMovement',
           'UlnarRotation', 'Flexion', 'FlexionChange', 'Spread', 'SpreadChange',
           'ThumbPosition', 'ThumbContact', 'MajorLocation', 'MinorLocation',
           'SecondMinorLocation', 'Contact']


def fetch(url, target):
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=90) as response:
            content = response.read()
        target.write_bytes(content)
    return target


def read_csv(path):
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8-sig')
        encoding = 'utf-8-sig'
    except UnicodeDecodeError:
        # Official CSV contains Latin-1 bytes (including existing garbled translations).
        # This lossless decoding also matches those strings in official sign_props.json.
        text, encoding = raw.decode('latin-1'), 'latin-1'
    reader = csv.DictReader(io.StringIO(text, newline=''))
    rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError('Malformed CSV row')
    return rows, reader.fieldnames, encoding


def field(stem, m):
    return f'{stem}{"M" + str(m) if m > 1 else ""}.2.0'


def present(value):
    return value is not None and value.strip() not in MISSING


def morpheme_count(row):
    try:
        number = float(row.get('NumberOfMorphemes.2.0', ''))
        return int(number) if number.is_integer() and 1 <= number <= 6 else None
    except ValueError:
        return None


def eligibility(row):
    if row.get('SignType.2.0') != 'OneHanded':
        return False, None
    n = morpheme_count(row)
    if n is None:
        return False, 'Missing or invalid morpheme count'
    ambiguous = []
    non_one_handed = []
    known = {'OneHanded', 'SymmetricalOrAlternating', 'AsymmetricalDifferentHandshape',
             'AsymmetricalSameHandshape', 'DominanceViolation', 'SymmetryViolation'}
    for m in range(2, n + 1):
        value = row.get(field('SignType', m), '')
        if value not in known:
            ambiguous.append(f'{field("SignType", m)}={value!r}')
        elif value != 'OneHanded':
            non_one_handed.append(m)
    # Report uncertainty even if another existing morpheme already makes it ineligible.
    if ambiguous:
        return False, '; '.join(ambiguous)
    return not non_one_handed, None


def frequency(row):
    value = row.get('SignFrequency(M)', '')
    if not present(value):
        return None
    rating = float(value)
    if not math.isfinite(rating) or not 1 <= rating <= 7:
        raise ValueError(f'Invalid frequency for {row["EntryID"]}: {value}')
    return rating


def sort_key(row):
    rating = frequency(row)
    return (rating is None, -rating if rating is not None else 0, row['EntryID'])


def motion(row):
    evidence, gaps = [], []
    n = morpheme_count(row)
    for m in range(1, n + 1):
        key = field('Movement', m)
        value = row.get(key, '')
        if value in {'Straight', 'Curved', 'Circular', 'Z-shaped', 'BackAndForth', 'Other', 'X-shaped'}:
            evidence.append(f'{key}={value}')
        elif value != 'None':
            gaps.append(key)
        for stem in ['UlnarRotation', 'FlexionChange', 'SpreadChange', 'RepeatedMovement']:
            key = field(stem, m)
            value = row.get(key, '')
            if value == '1':
                evidence.append(f'{key}=1')
            elif value != '0':
                gaps.append(key)
        # A coded second location, or a change between sequential units, is evidence.
        a, b = row.get(field('MinorLocation', m), ''), row.get(field('SecondMinorLocation', m), '')
        if present(a) and present(b) and a != b:
            evidence.append(f'Morpheme {m}: MinorLocation {a} → {b}')
        if m > 1:
            for stem in ['Handshape', 'SelectedFingers', 'Flexion', 'Spread', 'ThumbPosition',
                         'ThumbContact', 'MajorLocation', 'MinorLocation']:
                a, b = row.get(field(stem, m - 1), ''), row.get(field(stem, m), '')
                if not (present(a) and present(b)):
                    gaps.append(f'{stem} transition M{m-1}→M{m}')
                elif a != b:
                    evidence.append(f'{stem} M{m-1}→M{m}: {a} → {b}')
    if evidence:
        return 'Dynamic', evidence
    if gaps:
        return 'Unclear', ['Missing/ambiguous coding: ' + ', '.join(gaps)]
    return 'Static candidate', ['Every existing morpheme explicitly codes no path movement, rotation, flexion/spread change or repetition; no coded location/handshape transition.']


def image_url(html):
    match = re.search(r'src\s*=\s*["\x27]([^"\x27]+)', html or '')
    return match.group(1) if match else None


def main():
    SOURCES.mkdir(exist_ok=True)
    rows, columns, encoding = read_csv(fetch(CSV_URL, SOURCES / 'signdata.csv'))
    fetch(KEY_URL, SOURCES / 'data-key')
    commit_file = SOURCES / 'repository-commit.txt'
    if not commit_file.exists():
        with urllib.request.urlopen('https://api.github.com/repos/ASL-LEX/asl-lex/commits/master', timeout=60) as response:
            commit_file.write_text(json.load(response)['sha'], encoding='utf-8')
    commit = commit_file.read_text().strip()
    paths = ['visualization/data/sign_props.json', 'visualization/js/renderNetworkGraph.js',
             'visualization/js/filters_data.js', 'data-analysis/scripts/data/HandshapeImages.csv']
    for path in paths:
        target = SOURCES / ('HandshapeImages.csv' if path.endswith('HandshapeImages.csv') else path)
        fetch(REPO + commit + '/' + path, target)
    props_list = json.loads((SOURCES / paths[0]).read_text(encoding='utf-8'))
    props = {(r['EntryID'], r['Code']): r for r in props_list}
    images_list, _, _ = read_csv(SOURCES / 'HandshapeImages.csv')
    images = {(r['EntryID'], r['Code']): r for r in images_list}
    assert len(props) == len(props_list), 'Duplicate visualization EntryID/Code pairs'
    assert len(images) == len(images_list), 'Duplicate image EntryID/Code pairs'
    assert len({(r['EntryID'], r['Code']) for r in rows}) == len(rows), 'Duplicate source identities'
    eligible, ambiguous = [], []
    for row in rows:
        ok, reason = eligibility(row)
        if ok:
            eligible.append(row)
        if reason:
            ambiguous.append({'EntryID': row['EntryID'], 'reason': reason})
    eligible.sort(key=sort_key)
    with (ROOT / 'one_handed_signs_by_frequency.csv').open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(eligible)
    override_path = ROOT / 'motion_overrides.json'
    if not override_path.exists():
        override_path.write_text('{}\n', encoding='utf-8')
    overrides = json.loads(override_path.read_text(encoding='utf-8'))
    assert set(overrides) <= {r['EntryID'] + '|' + r['Code'] for r in rows}, 'Unknown override EntryID|Code'
    signs, missing_video, missing_image, missing_join = [], [], [], []
    image_table_aliases = []
    for rank, row in enumerate(eligible[:TOP_COUNT], 1):
        entry = row['EntryID']
        identity = (entry, row['Code'])
        stable_id = '|'.join(identity)
        prop, img = props.get(identity, {}), images.get(identity, {})
        # The official image table calls this entry think_chin.m4v; both tables
        # identify the same original video Code. Preserve the CSV EntryID.
        if not img and entry == 'think_chin' and row['Code'] == 'K_03_120':
            img = images.get(('think_chin.m4v', row['Code']), {})
            if img:
                image_table_aliases.append({'EntryID': entry, 'imageTableEntryID': img['EntryID'], 'Code': row['Code']})
        # Exact EntryID plus original video Code guards against joining a lemma variant.
        for mapped in [prop, img]:
            if not mapped:
                missing_join.append(entry)
            elif mapped['Code'] != row['Code']:
                raise ValueError(f'Media Code mismatch: {entry}')
        video = prop.get('VimeoVideo')
        image = image_url(prop.get('HandshapeImage'))
        table_image = image_url(img.get('HandshapeImage'))
        if image and table_image and image != table_image:
            raise ValueError(f'Conflicting image mappings: {entry}')
        if video and not re.fullmatch(r'https://player\.vimeo\.com/video/\d+', video):
            raise ValueError(f'Unexpected embed: {video}')
        if not video:
            missing_video.append(entry)
        if not image:
            missing_image.append(entry)
        hs = Path(urlparse(image).path).stem if image else row['Handshape.2.0']
        status, reasons = motion(row)
        derived = status
        if stable_id in overrides:
            override = overrides[stable_id]
            assert override['status'] in {'Dynamic', 'Static candidate', 'Unclear'}
            assert override.get('reason', '').strip(), 'Override needs a reason'
            status = override['status']
            reasons = ['Manual override: ' + override['reason']] + reasons
        translations = [row.get(k, '') for k in ['DominantTranslation', 'NondominantTranslations', 'SignBankEnglishTranslations']]
        signs.append({'id': stable_id, 'rank': rank, 'entryId': entry, 'name': entry.replace('_', ' '),
                      'code': row['Code'], 'frequency': frequency(row),
                      'translations': [v for v in translations if present(v)],
                      'handshape': {'id': hs, 'name': hs.replace('_', ' '), 'code': row['Handshape.2.0'], 'image': image},
                      'video': video, 'source': 'https://asl-lex.org/visualization/?sign=' + quote(entry),
                      'motion': status, 'derivedMotion': derived, 'motionReasons': reasons,
                      'morphemes': [{field(s, m): row.get(field(s, m), '') for s in DETAILS}
                                    for m in range(1, morpheme_count(row) + 1)]})
    media_manifest = ROOT / 'local_media.json'
    local_media = json.loads(media_manifest.read_text(encoding='utf-8')).get('videos', {}) if media_manifest.exists() else {}
    for sign in signs:
        local = local_media.get(sign['id'], {})
        sign['localVideo'] = None
        if local.get('status') == 'verified' and local.get('source') == sign['video']:
            path = ROOT / local['path']
            if path.is_file() and path.stat().st_size == local['bytes']:
                sign['localVideo'] = local['path']
    data = {'source': CSV_URL, 'inputCount': len(rows), 'eligibleCount': len(eligible),
            'repositoryCommit': commit, 'signs': signs}
    (ROOT / 'data.js').write_text('window.ASL_DATA = ' + json.dumps(data, ensure_ascii=True, indent=2) + ';\n', encoding='utf-8')
    report = {'inputCount': len(rows), 'encoding': encoding, 'eligibleCount': len(eligible),
              'ambiguousExcluded': ambiguous, 'missingFrequency': [r['EntryID'] for r in eligible if frequency(r) is None],
              'websiteSignCount': len(signs), 'missingMediaJoins': sorted(set(missing_join)),
              'missingVideoMappings': missing_video, 'missingImageMappings': missing_image,
              'motionCounts': dict(Counter(s['motion'] for s in signs)), 'repositoryCommit': commit,
              'duplicateSourceEntryIDs': {k: v for k, v in Counter(r['EntryID'] for r in rows).items() if v > 1}}
    report['imageTableAliases'] = image_table_aliases
    (ROOT / 'preparation_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    # Re-read artifacts to verify full rows, all original columns, order and exact variants.
    output, out_columns, _ = read_csv(ROOT / 'one_handed_signs_by_frequency.csv')
    assert out_columns == columns and output == eligible
    assert all(eligibility(r)[0] for r in output)
    assert output == sorted(output, key=sort_key)
    assert [(s['entryId'], s['code']) for s in signs] == [(r['EntryID'], r['Code']) for r in output[:TOP_COUNT]]
    assert len(signs) == TOP_COUNT and len({s['id'] for s in signs}) == TOP_COUNT
    print('PASS: original columns/values, one-handed eligibility, numeric ordering, exact top 200 EntryIDs.')


if __name__ == '__main__':
    main()
