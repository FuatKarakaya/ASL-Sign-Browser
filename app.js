'use strict';
const signs = window.ASL_DATA.signs;
const storageKey = 'asl-sign-browser.shortlist.v1';
const byId = new Map(signs.map(sign => [sign.id, sign]));
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalize = value => String(value ?? '').toLocaleLowerCase('en').replace(/_/g, ' ').trim();
let shortlist = new Set();
let activePlayer = null;

function readShortlist() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (!Array.isArray(saved)) throw new Error('Invalid stored shortlist');
    shortlist = new Set(saved.filter(id => byId.has(id)));
  } catch (_) {
    $('storage-notice').hidden = false;
    $('storage-notice').textContent = 'Browser storage is unavailable or invalid. Your shortlist works for this visit; export it to keep a copy.';
  }
}

function matchingSigns(items, filters, saved) {
  const query = normalize(filters.query);
  return items.filter(s => (!query || normalize([s.entryId, s.name, ...s.translations].join(' ')).includes(query)) &&
    (!filters.handshape || s.handshape.id === filters.handshape) &&
    (!filters.motion || s.motion === filters.motion) && (!filters.shortlistOnly || saved.has(s.id)));
}

function exportCSV(items) {
  const columns = ['Rank', 'EntryID', 'Code', 'SignFrequency(M)', 'MotionStatus', 'HandshapeID', 'HandshapeCode', 'Source', 'Video', 'LocalVideo'];
  const cell = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  return '\ufeff' + [columns, ...items.map(s => [s.rank, s.entryId, s.code, s.frequency, s.motion, s.handshape.id, s.handshape.code, s.source, s.video, s.localVideo])].map(row => row.map(cell).join(',')).join('\r\n') + '\r\n';
}

let visibilityObserver = null;
const videoPlayers = new Map();

function updateShortlistUI() {
  $('shortlist-count').textContent = shortlist.size;
  $('export').disabled = !shortlist.size;
  document.querySelectorAll('.save').forEach(button => {
    const sign = byId.get(button.dataset.id);
    const saved = shortlist.has(sign.id);
    button.setAttribute('aria-pressed', String(saved));
    button.innerHTML = saved ? '&#9733;' : '&#9734;';
    button.setAttribute('aria-label', `${saved ? 'Remove' : 'Add'} ${sign.entryId} ${saved ? 'from' : 'to'} shortlist`);
  });
}

function ensureVideo(card, sign) {
  if (videoPlayers.has(sign.id)) return videoPlayers.get(sign.id);
  if (!sign.localVideo) return null;
  const video = document.createElement('video');
  video.controls = true;
  video.playsInline = true;
  video.preload = 'auto';
  video.setAttribute('aria-label', `Reference video for ${sign.name}`);
  video.src = sign.localVideo;
  const state = {card, video, sign};
  videoPlayers.set(sign.id, state);
  card.querySelector('.video-wrap').append(video);
  video.addEventListener('error', () => {
    const status = card.querySelector('.media-status');
    status.hidden = false;
    status.textContent = 'Video unavailable. Check the local media folder.';
  });
  video.addEventListener('play', () => {
    if (activePlayer && activePlayer !== state) stopPlayer();
    activePlayer = state;
  });
  video.load();
  return state;
}

function stopPlayer() {
  if (!activePlayer) return;
  const {card, video} = activePlayer;
  video.pause();
  card.querySelector('.card-summary').hidden = false;
  card.querySelector('.video-wrap').hidden = true;
  card.querySelector('.back').hidden = true;
  card.querySelector('.save').hidden = false;
  card.querySelector('.media-status').hidden = true;
  activePlayer = null;
}

function playCard(card, sign) {
  stopPlayer();
  const state = ensureVideo(card, sign);
  const status = card.querySelector('.media-status');
  if (!state) {
    status.hidden = false;
    status.textContent = 'Local video unavailable.';
    return;
  }
  activePlayer = state;
  card.querySelector('.card-summary').hidden = true;
  card.querySelector('.video-wrap').hidden = false;
  card.querySelector('.back').hidden = false;
  card.querySelector('.save').hidden = true;
  state.video.currentTime = 0;
  state.video.play().catch(() => {
    if (activePlayer !== state) return;
    status.hidden = false;
    status.textContent = 'Press play on the video to start.';
  });
}

function cardHTML(s) {
  const e = escapeHTML;
  const theme = s.motion === 'Static candidate' ? 'static' : s.motion === 'Unclear' ? 'unclear' : 'dynamic';
  return `<article class="card ${theme}" data-id="${e(s.id)}">
    <div class="card-top"><span class="rank">${s.rank}</span><h2><a href="${e(s.source)}" target="_blank" rel="noopener">${e(s.name)}</a></h2>
    <button class="save" type="button" data-id="${e(s.id)}" aria-pressed="false">&#9734;</button><button class="back" type="button" aria-label="Close video for ${e(s.name)}" hidden>&times;</button></div>
    <div class="card-body"><div class="card-summary"><div class="overview">${s.handshape.image ? `<img class="handshape" src="${e(s.handshape.image)}" alt="${e(s.handshape.name)} handshape" loading="lazy" width="90" height="90">` : '<span class="image-error">Image unavailable</span>'}</div><button class="play" type="button" aria-label="Play ${e(s.name)}">&#9654; Play</button></div>
    <div class="video-wrap" hidden></div><p class="media-status error" role="status" hidden></p></div></article>`;
}

function render() {
  stopPlayer();
  visibilityObserver?.disconnect();
  for (const {video} of videoPlayers.values()) {
    video.pause(); video.removeAttribute('src'); video.load();
  }
  videoPlayers.clear();
  const visible = matchingSigns(signs, {query:$('search').value, handshape:$('handshape').value, motion:$('motion').value, shortlistOnly:$('shortlist-only').checked}, shortlist);
  $('cards').innerHTML = visible.map(cardHTML).join('');
  $('result-count').textContent = visible.length === signs.length ? `${signs.length} signs` : `${visible.length} / ${signs.length} signs`;
  $('empty').hidden = visible.length > 0;
  // Preload only cards intersecting the viewport; never request the entire collection at startup.
  visibilityObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const card = entry.target;
        ensureVideo(card, byId.get(card.dataset.id));
        visibilityObserver.unobserve(card);
      }
    }
  }, {rootMargin:'0px', threshold:0.01});
  document.querySelectorAll('.card').forEach(card => {
    const sign = byId.get(card.dataset.id);
    visibilityObserver.observe(card);
    card.querySelector('.save').addEventListener('click', () => {
      shortlist.has(sign.id) ? shortlist.delete(sign.id) : shortlist.add(sign.id);
      try { localStorage.setItem(storageKey, JSON.stringify([...shortlist])); }
      catch (_) { $('storage-notice').hidden = false; $('storage-notice').textContent = 'Could not save shortlist. Export it to keep a copy.'; }
      if ($('shortlist-only').checked) render(); else updateShortlistUI();
    });
    card.querySelector('.play').addEventListener('click', () => playCard(card, sign));
    card.querySelector('.back').addEventListener('click', stopPlayer);
    card.querySelector('img')?.addEventListener('error', event => {
      const note = document.createElement('span'); note.className = 'image-error'; note.textContent = 'Image unavailable';
      event.target.replaceWith(note);
    });
  });
  updateShortlistUI();
}

function resetFilters() {
  $('search').value = ''; $('handshape').value = ''; $('motion').value = ''; $('shortlist-only').checked = false; render();
}

const handshapes = [...new Map(signs.map(s => [s.handshape.id, s.handshape])).values()].sort((a,b) => a.id.localeCompare(b.id, 'en', {numeric:true}));
for (const h of handshapes) {
  const option = document.createElement('option'); option.value = h.id; option.textContent = `${h.name} [${h.id}]`; $('handshape').append(option);
}
$('search').addEventListener('input', render);
for (const id of ['handshape','motion','shortlist-only']) $(id).addEventListener('change', render);
for (const id of ['reset','empty-reset']) $(id).addEventListener('click', resetFilters);
$('export').addEventListener('click', () => {
  const selected = signs.filter(s => shortlist.has(s.id));
  const blob = new Blob([exportCSV(selected)], {type:'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = 'asl-sign-shortlist.csv';
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
window.addEventListener('pagehide', stopPlayer);
readShortlist();
render();
