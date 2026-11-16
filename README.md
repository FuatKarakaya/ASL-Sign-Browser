# ASL Sign Browser

A local sign-selection tool for the sensor-glove project: Python preparation plus plain HTML/CSS/JavaScript. No backend or package installation. The prepared data is ready to use.

## Open on your computer

Download and extract this repository's ZIP, or clone it:

```powershell
git clone https://github.com/FuatKarakaya/ASL-Sign-Browser.git
cd ASL-Sign-Browser
python -m http.server 8000 --bind 127.0.0.1
```

For a ZIP download, open a terminal in the extracted folder (the one containing `index.html`) and run the last command. Python 3 is the only requirement to serve the files; all 200 MP4 videos and the prepared metadata are included. No data preparation or video downloads are needed.

Open **http://127.0.0.1:8000/**. Stop with Ctrl+C. Use the same browser, hostname and port to retain your shortlist. Videos play locally; handshape images and external links require internet access. Visible cards preload their videos. Frequency determines card order, but the cards do not display frequency numbers.

## Preparation

```powershell
python prepare_data.py
```

Python 3 standard library only. Downloads in `sources/` are reused and never overwritten, and the original `..\signdata.csv` is untouched. Generated outputs are replaced. Repository references are pinned in `sources/repository-commit.txt`.

The source CSV is not valid UTF-8 or Windows-1252. Lossless Latin-1 decoding matches the existing garbled translation strings in the official visualization JSON. Upstream text artifacts are preserved. The output is UTF-8 with every original column and cell value retained. Blank/NA-style tokens are missing; literal `None` is a valid movement code.

Eligibility requires a valid morpheme count (1-6) and `OneHanded` in the sign-type field of **every existing morpheme**. Uncertain handedness excludes the record and is reported; unused later fields are ignored. Frequency sorts numerically descending, then by EntryID. Missing ratings remain missing and sort last. Frequency is a **subjective 1-7 rating**, not a usage count.

## Media and variants

Official `visualization/data/sign_props.json` supplies `VimeoVideo` and `HandshapeImage`; `visualization/js/renderNetworkGraph.js` demonstrates embedding and `?sign=EntryID` source links. Image URLs are cross-checked against `data-analysis/scripts/data/HandshapeImages.csv`. URLs are extracted from real mappings, not guessed.

Joins and stored identities use **EntryID + Code**: the source has duplicate EntryIDs `type`, `take_off`, `bite`, and `drag` representing different videos. No variants are collapsed. Handshape filters use stable mapped image identifiers, such as `flat_b`; original handshape codes are retained in the prepared metadata.

All 200 reference videos are now stored as MP4 files in `media/videos/`, named with the original Code and Vimeo ID. Videos for cards intersecting the viewport preload automatically. Clicking Play replaces the card body and starts playback immediately; only one video plays at a time. Close returns to the compact card. Original hosted source links remain available. Missing/corrupt local files show an unavailable message.

To download or re-verify the files:

```powershell
python -m pip install --target .tools yt-dlp imageio-ffmpeg
python download_videos.py
```

These extra dependencies are only for downloading/verification and stay in `.tools/`. Viewing the site still needs no packages. The downloader uses the official embed context, selects video up to 720p with available audio, and merges into MP4. It checks the Vimeo ID, fully decodes every file with FFmpeg, and records its source, size and SHA-256 in `local_media.json`. Existing MP4s are reused and rechecked. Preparation preserves verified local references on reruns.

## Derived motion labels

The data key does not provide a definitive static/dynamic column. For **all existing morphemes**, the rule uses path movement, wrist twist (`UlnarRotation`), flexion/spread changes, repetition, and location/handshape transitions:

- **Dynamic:** explicit path movement, rotation, finger change, repetition, distinct coded first/second locations, or a coded configuration/location change between sequential morphemes.
- **Static candidate:** `Movement=None` and explicit zeros for rotation, flexion change, spread change and repetition throughout, with no coded location change. Multi-morpheme configuration/location comparisons must be complete and unchanged.
- **Unclear:** no explicit motion, but required coding/comparisons are missing or ambiguous. Missing never means static; explicit motion takes precedence over other gaps.

The prepared data retains raw supporting fields for every morpheme. The compact interface omits phonological details; static candidates use blue cards, dynamic signs use green, and unclear signs use a neutral amber theme. These labels aid screening; they do not guarantee linguistic classification or sensor feasibility. The current top 200 contain 197 Dynamic and 3 Unclear signs; there are no Static candidates.

For manual review, edit `motion_overrides.json` and rerun preparation. Keys are exact `EntryID|Code` identities; a reason is required. Example (the supplied file is empty):

```json
{"water|A_02_031": {"status": "Unclear", "reason": "Manual review pending; example only."}}
```

Overrides retain derived evidence. Search includes available dominant, nondominant and Signbank translations. Filters stay within the original top 200 and preserve ranks. Reset leaves the shortlist intact. Export saves the **entire shortlist**, including signs hidden by filters, as CSV. Storage failure shows a warning.

## Verification

```powershell
python verify.py
python verify.py --check-media
node --check app.js
node verify_ui_logic.cjs
```

Node is optional for logic checks; no npm packages are needed.

- **2,723 input rows; 954 eligible; 30 ambiguous exclusions.** Reasons are in `preparation_report.json`. No eligible frequencies are missing.
- Independent checks pass for full rows/columns, all-morpheme eligibility, numerical ordering, exact first 200 EntryID/Code pairs/ranks, and media/coding joins. The original parent CSV matches the download byte-for-byte.
- **Zero missing media mappings.** All 42 distinct handshape-image URLs returned HTTP 200 (image_check_report.json). All 200 exact reference videos are stored locally (see local_media.json for verified file sizes) and fully decoded successfully with FFmpeg. `local_media.json` records provenance and checksums; `verify.py` checks those hashes and the website mappings. Historical hosted checks remain in `media_check_report.json`.
- JavaScript VM checks pass for search, translations, filters, reset, ranks, shortlist save/restore logic, CSV escaping/content, safe markup, simplified card themes/source links and storage warnings.
- **Brave verification:** desktop rendering, search, local video playback, shortlist persistence after reload, one-click autoplay replacing the card body, and closing the video passed. Export opened the save dialog, but saving the export file was not verified. Mobile layout was not tested.

## Files and attribution

`index.html`, `styles.css`, `app.js`: interface; `data.js`: top 200 metadata; `one_handed_signs_by_frequency.csv`: all eligible rows; `prepare_data.py`: preparation; `motion_overrides.json`: manual labels; `verify.py`/`verify_ui_logic.cjs`: checks; `download_videos.py`: repeatable downloader; `media/videos/`: 200 MP4s; `local_media.json`: provenance and checksums; `*_report.json`: results; `sources/`: unmodified downloads and inspected official reference code.

[Visualization](https://asl-lex.org/visualization/) | [Downloads/licensing](https://asl-lex.org/download.html) | [CSV](https://osf.io/download/9nygd) | [Data key](https://osf.io/download/ygq4v) | [Official repository](https://github.com/ASL-LEX/asl-lex)

Please cite Sevcikova Sehyr, Z., Caselli, N., Cohen-Goldberg, A. M., & Emmorey, K. (2021), *The ASL-LEX 2.0 Project: A database of lexical and phonological properties for 2,723 signs in American Sign Language*, [doi:10.1093/deafed/enaa038](https://doi.org/10.1093/deafed/enaa038); and Caselli, N., Sevcikova Sehyr, Z., Cohen-Goldberg, A. M., & Emmorey, K. (2017), *ASL-LEX: A lexical database of American Sign Language*, Behavior Research Methods 49(2), 784-801, [doi:10.3758/s13428-016-0742-0](https://doi.org/10.3758/s13428-016-0742-0).

The download page identifies database/visualization licensing as CC BY 4.0; the older repository README says CC BY-NC. Consult the source licensing for reuse. Reference videos remain copyright ASL-LEX.org. This is an independent filtered/derived tool.

The browser now includes ranks 1-200, extending the original 100 with the next 100 eligible signs in numerical frequency order. The official image table names `think_chin` as `think_chin.m4v`; that explicit alias is cross-checked using the identical video Code `K_03_120` and image URL. The original EntryID is retained.
