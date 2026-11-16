"""Independent artifact checks; optional HTTP media checks, never video downloads."""
import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from prepare_data import ROOT, SOURCES, read_csv, motion, eligibility, sort_key


def check_artifacts():
    original, columns, encoding = read_csv(SOURCES / 'signdata.csv')
    output, out_columns, _ = read_csv(ROOT / 'one_handed_signs_by_frequency.csv')
    expected = []
    for row in original:
        if row['SignType.2.0'] != 'OneHanded':
            continue
        try:
            n = int(row['NumberOfMorphemes.2.0'])
        except ValueError:
            continue
        if 1 <= n <= 6 and all(row[f'SignTypeM{m}.2.0'] == 'OneHanded' for m in range(2, n + 1)):
            expected.append(row)
    def numeric_order(row):
        value = row['SignFrequency(M)']
        if value in {'', 'NA', 'N/A', 'NaN', 'nan', 'NULL', 'null'}:
            return (True, 0, row['EntryID'])
        return (False, -float(value), row['EntryID'])
    expected.sort(key=numeric_order)
    assert columns == out_columns and output == expected, 'CSV differs from independent full-row selection'
    text = (ROOT / 'data.js').read_text(encoding='utf-8')
    assert text.startswith('window.ASL_DATA = ') and text.endswith(';\n')
    data = json.loads(text[len('window.ASL_DATA = '):-2])
    signs = data['signs']
    assert len(signs) == 200
    assert [(s['entryId'], s['code']) for s in signs] == [(r['EntryID'], r['Code']) for r in expected[:200]]
    assert [s['rank'] for s in signs] == list(range(1, 201))
    assert [s['frequency'] for s in signs] == [float(r['SignFrequency(M)']) if r['SignFrequency(M)'] else None for r in expected[:200]]
    props = {(r['EntryID'], r['Code']): r for r in json.loads((SOURCES / 'visualization/data/sign_props.json').read_text(encoding='utf-8'))}
    missing = []
    for sign, row in zip(signs, expected):
        mapping = props[(sign['entryId'], sign['code'])]
        assert sign['video'] == mapping.get('VimeoVideo')
        image = re.search(r'src="([^"]+)"', mapping.get('HandshapeImage', ''))
        assert sign['handshape']['image'] == (image.group(1) if image else None)
        assert sign['handshape']['code'] == row['Handshape.2.0'] == mapping['Handshape.2.0']
        assert len(sign['morphemes']) == int(row['NumberOfMorphemes.2.0'])
        assert all(row[k] == v for morpheme in sign['morphemes'] for k, v in morpheme.items())
        if not sign['video'] or not image:
            missing.append(sign['id'])
    # Boundary cases guard against the mistakes most likely to affect selection.
    base = dict(expected[0])
    base.update({'NumberOfMorphemes.2.0':'2', 'SignTypeM2.2.0':'NA'})
    assert eligibility(base)[0] is False and eligibility(base)[1]
    base['SignTypeM2.2.0'] = 'SymmetricalOrAlternating'
    assert eligibility(base) == (False, None)
    base.update({'NumberOfMorphemes.2.0':'1', 'Movement.2.0':'None', 'UlnarRotation.2.0':'0',
                 'FlexionChange.2.0':'0', 'SpreadChange.2.0':'0', 'RepeatedMovement.2.0':'0',
                 'SecondMinorLocation.2.0':'NA'})
    assert eligibility(base)[0], 'Nonexistent later morphemes should be ignored'
    assert motion(base)[0] == 'Static candidate'
    base['SpreadChange.2.0'] = 'NA'
    assert motion(base)[0] == 'Unclear', 'Missing must not mean static'
    base['UlnarRotation.2.0'] = '1'
    assert motion(base)[0] == 'Dynamic', 'Explicit motion takes precedence over missing fields'
    base.update({'NumberOfMorphemes.2.0':'2', 'SignTypeM2.2.0':'OneHanded', 'UlnarRotation.2.0':'0',
                 'MovementM2.2.0':'Straight'})
    assert motion(base)[0] == 'Dynamic', 'Later morphemes must be inspected'
    low, high, absent = (dict(expected[0]) for _ in range(3))
    low['SignFrequency(M)'], high['SignFrequency(M)'], absent['SignFrequency(M)'] = '2', '6.5', 'NA'
    assert sorted([low, absent, high], key=sort_key) == [high, low, absent]
    local_count = 0
    if (ROOT / 'local_media.json').exists():
        local = json.loads((ROOT / 'local_media.json').read_text(encoding='utf-8'))['videos']
        for sign in signs:
            record = local[sign['id']]
            assert record['status'] == 'verified' and record['source'] == sign['video']
            assert sign['localVideo'] == record['path']
            video_bytes = (ROOT / sign['localVideo']).read_bytes()
            assert len(video_bytes) == record['bytes']
            assert hashlib.sha256(video_bytes).hexdigest() == record['sha256']
            local_count += 1
    report = {'checkedAtUTC': datetime.now(timezone.utc).isoformat(), 'inputCount':len(original),
              'verifiedLocalVideos': local_count,
              'eligibleCount':len(expected), 'websiteSignCount':len(signs), 'missingMediaMappings':missing,
              'sourceSHA256':hashlib.sha256((SOURCES/'signdata.csv').read_bytes()).hexdigest(),
              'encoding':encoding, 'checks':'PASS: independent eligibility, full rows/columns, numeric order, exact variants/ranks, media and coding joins, ambiguous/missing and motion boundary cases',
              'browserVerification':'Brave native UI verified desktop rendering, search, local playback, shortlist persistence after reload, simplified one-click autoplay/card replacement and close. Export opened the save dialog; completed download was not verified. Mobile layout not tested.'}
    parent_source = ROOT.parent / 'signdata.csv'
    if parent_source.exists():
        report['existingParentCSVMatchesOfficialDownload'] = parent_source.read_bytes() == (SOURCES/'signdata.csv').read_bytes()
    (ROOT/'verification_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return signs


def check_media(signs):
    refs = {}
    for s in signs:
        for kind, url in [('video', s['video']), ('image', s['handshape']['image'])]:
            if url:
                refs.setdefault(url, {'kind':kind, 'entries':[]})['entries'].append(s['id'])
    def request(item):
        url, info = item
        result = {'url':url, **info}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0', 'Referer':'http://127.0.0.1:8000/'}), timeout=25) as response:
                result.update(status=response.status, contentType=response.headers.get('Content-Type'))
                response.read(512)  # Only sample the embed HTML / image, never a video file.
        except urllib.error.HTTPError as error:
            result.update(status=error.code, error=str(error))
        except Exception as error:
            result['error'] = str(error)
        return result
    with ThreadPoolExecutor(max_workers=10) as pool:
        checks = list(pool.map(request, sorted(refs.items())))
    report = {'checkedAtUTC':datetime.now(timezone.utc).isoformat(),
              'scope':'GET requests sampling at most 512 bytes of each mapped embed HTML / image, with localhost Referer. No video files downloaded. HTTP status does not prove browser playback.',
              'signCount':len(signs), 'uniqueVideoURLs':sum(v['kind']=='video' for v in refs.values()),
              'uniqueImageURLs':sum(v['kind']=='image' for v in refs.values()), 'checks':checks}
    (ROOT/'media_check_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('HTTP media checks:',dict(Counter(str(c.get('status','network error')) for c in checks)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-media', action='store_true', help='Check mapped HTTP endpoints without downloading videos')
    args = parser.parse_args()
    signs = check_artifacts()
    if args.check_media:
        check_media(signs)
