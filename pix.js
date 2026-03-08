'use strict';

// ── State ─────────────────────────────────────────────────────────────────────

let gallery  = null;   // parsed index.json
let dirMap   = {};     // path -> DirNode (built once on load)

// Lightbox
let lbPhotos  = [];     // photos in the currently-displayed directory
let lbIndex   = -1;     // index into lbPhotos; -1 = closed
let lbLarge   = false;  // true = showing large; false = showing medium
let hasMedium = true;   // set from gallery.sizes after index.json loads
let hasLarge  = true;   // set from gallery.sizes after index.json loads

// ── Bootstrap ─────────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', () => {
  // Optional auth gate: if pix-auth.cgi exists and returns {ok:false}, redirect to login.
  // If the CGI is absent or errors, proceed without auth (backward-compatible).
  fetch('pix-auth.cgi?action=check')
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      if (d && !d.ok) { location.href = 'pix-auth.cgi'; return; }
      if (d &&  d.ok) {
        const a = document.createElement('a');
        a.href = 'pix-auth.cgi?action=logout';
        a.className = 'logout-link';
        a.textContent = 'Logout';
        document.querySelector('header').appendChild(a);
      }
      loadGallery();
    })
    .catch(() => loadGallery());
});

function loadGallery() {
  fetch('_pix/index.json')
    .then(r => {
      if (!r.ok) throw new Error(r.status === 404 ? 'not_initialized' : String(r.status));
      return r.json();
    })
    .then(data => {
      gallery = data;
      const sz = gallery.sizes || ['thumb', 'medium', 'large'];
      hasMedium = sz.includes('medium');
      hasLarge  = sz.includes('large');
      buildDirMap(gallery.tree, '');
      window.addEventListener('hashchange', navigate);
      navigate();
    })
    .catch(err => {
      const app = document.getElementById('app');
      if (err.message === 'not_initialized') {
        app.innerHTML = notInitHtml();
      } else {
        app.innerHTML = `<p class="msg-err">Error loading gallery: ${esc(err.message)}</p>`;
      }
    });
}

function buildDirMap(node, path) {
  dirMap[path] = node;
  for (const d of node.dirs) buildDirMap(d, d.path);
}

// ── Routing ───────────────────────────────────────────────────────────────────

function navigate() {
  closeLightbox();
  const hash = decodeURIComponent(location.hash.slice(1));  // strip leading '#'
  const dir  = dirMap[hash];
  if (!dir && hash !== '') { location.hash = ''; return; }  // unknown path → root
  renderDir(dir || gallery.tree);
}

// ── Directory view ────────────────────────────────────────────────────────────

function renderDir(dir) {
  lbPhotos = dir.photos;

  const grid = document.createElement('div');
  grid.className = 'grid';

  for (const sub of dir.dirs)           grid.appendChild(makeDirCard(sub));
  dir.photos.forEach((p, i) =>          grid.appendChild(makePhotoCard(p, i)));

  const app = document.getElementById('app');
  app.innerHTML = '';
  app.appendChild(makeBreadcrumb(dir.path));

  if (!dir.dirs.length && !dir.photos.length) {
    const msg = document.createElement('p');
    msg.className = 'empty';
    msg.textContent = 'No photos in this directory.';
    app.appendChild(msg);
    return;
  }

  app.appendChild(grid);
}

function makeBreadcrumb(path) {
  const nav = document.createElement('nav');
  nav.className = 'breadcrumb';

  const a0 = document.createElement('a');
  a0.href = '#';
  a0.textContent = 'Home';
  nav.appendChild(a0);

  let acc = '';
  for (const part of (path ? path.split('/') : [])) {
    nav.appendChild(document.createTextNode(' \u203a '));
    acc = acc ? acc + '/' + part : part;
    const a = document.createElement('a');
    a.href = '#' + encodeURIComponent(acc);
    a.textContent = part;
    nav.appendChild(a);
  }
  return nav;
}

function makeDirCard(dir) {
  const div = document.createElement('div');
  div.className = 'card dir-card';

  const thumb = document.createElement('div');
  thumb.className = 'card-thumb';
  if (dir.cover) {
    const img = document.createElement('img');
    img.src = dir.cover;
    img.alt = '';
    img.loading = 'lazy';
    thumb.appendChild(img);
  } else {
    thumb.innerHTML = '<span class="dir-icon">\uD83D\uDCC1</span>';
  }

  const label = document.createElement('div');
  label.className = 'card-label';
  label.textContent = dir.name;

  div.appendChild(thumb);
  div.appendChild(label);
  div.addEventListener('click', () => { location.hash = '#' + encodeURIComponent(dir.path); });
  return div;
}

function makePhotoCard(photo, index) {
  const div = document.createElement('div');
  div.className = 'card photo-card';

  const thumb = document.createElement('div');
  thumb.className = 'card-thumb';
  const img = document.createElement('img');
  img.src = thumbUrl(photo);
  img.alt = photo.name;
  img.loading = 'lazy';
  thumb.appendChild(img);

  const label = document.createElement('div');
  label.className = 'card-label';
  label.textContent = photo.name;

  div.appendChild(thumb);
  div.appendChild(label);
  div.addEventListener('click', () => openLightbox(index));
  return div;
}

// ── Lightbox ──────────────────────────────────────────────────────────────────

function openLightbox(index) {
  lbIndex = index;
  lbLarge = !hasMedium;   // start in large if medium was not generated
  renderLightbox();
  document.getElementById('lightbox').classList.remove('hidden');
  document.getElementById('lightbox').focus();
  // Preload large version silently (only if it exists)
  if (hasLarge) {
    const large = new Image();
    large.src = largeUrl(lbPhotos[index]);
  }
}

function closeLightbox() {
  document.getElementById('lightbox').classList.add('hidden');
  lbIndex = -1;
}

function lbPrev() { if (lbIndex > 0)                   { lbIndex--; renderLightbox(); } }
function lbNext() { if (lbIndex < lbPhotos.length - 1) { lbIndex++; renderLightbox(); } }

function renderLightbox() {
  const p  = lbPhotos[lbIndex];
  const lb = document.getElementById('lightbox');

  lb.querySelector('.lb-img').src             = lbLarge ? largeUrl(p) : mediumUrl(p);
  lb.querySelector('.lb-img').alt             = p.name;
  lb.querySelector('.lb-title').textContent   = p.name;
  lb.querySelector('.lb-counter').textContent = `${lbIndex + 1}\u202F/\u202F${lbPhotos.length}`;
  lb.querySelector('.lb-download').href       = origUrl(p);
  lb.querySelector('.lb-prev').disabled       = lbIndex === 0;
  lb.querySelector('.lb-next').disabled       = lbIndex === lbPhotos.length - 1;

  const btn = lb.querySelector('.lb-fullscreen');
  if (hasMedium && hasLarge) {
    btn.classList.remove('hidden');
    btn.textContent = lbLarge ? 'Medium\u202F\u2199' : 'Full\u202Fsize\u202F\u2197';
  } else {
    btn.classList.add('hidden');
  }
}

function lbToggleLarge() {
  if (!hasMedium || !hasLarge) return;
  lbLarge = !lbLarge;
  renderLightbox();
}

// Keyboard navigation
document.addEventListener('keydown', e => {
  if (document.getElementById('lightbox').classList.contains('hidden')) return;
  if (e.key === 'ArrowLeft')  { lbPrev(); }
  else if (e.key === 'ArrowRight') { lbNext(); }
  else if (e.key === 'Escape')     { closeLightbox(); }
});

// ── URL helpers ───────────────────────────────────────────────────────────────

// Generated sizes are always JPEG regardless of source extension
function toJpgPath(p) { return p.replace(/\.[^./]+$/, '.jpg'); }

function thumbUrl(p)  { return '_pix/thumb/'  + toJpgPath(p.path); }
function mediumUrl(p) { return '_pix/medium/' + toJpgPath(p.path); }
function largeUrl(p)  { return '_pix/large/'  + toJpgPath(p.path); }
function origUrl(p)   { return p.path; }  // original file, kept as-is

// ── Utility ───────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Image click zones: left 20% = prev, right 20% = next ──────────────────────

const _lbImg = document.querySelector('.lb-img');
_lbImg.addEventListener('click', e => {
  if (e.offsetX / e.currentTarget.offsetWidth < 0.5) lbPrev(); else lbNext();
});
_lbImg.addEventListener('mousemove', e => {
  e.currentTarget.style.cursor =
    e.offsetX / e.currentTarget.offsetWidth < 0.5 ? 'w-resize' : 'e-resize';
});

function notInitHtml() {
  return `
<div class="not-init">
  <h2>Gallery Not Initialized</h2>
  <p>Run the initialization script before viewing the gallery:</p>
  <pre>perl pix-init.pl /path/to/this/gallery</pre>
  <p>Or open <a href="pix-init.cgi">pix-init.cgi</a> in your browser to initialize from the web.</p>
</div>`;
}
