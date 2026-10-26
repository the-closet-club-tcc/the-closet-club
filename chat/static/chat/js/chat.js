/* chat.js: perilaku halaman chat. */
(function () {
  const toast = (msg, kind) => window.showToast(msg, kind);

  /* Toast setelah hapus percakapan (halaman dimuat dengan ?deleted=1) */
  const params = new URLSearchParams(window.location.search);
  if (params.get('deleted')) {
    toast('Percakapan dihapus');
    params.delete('deleted');
    const rest = params.toString();
    history.replaceState(null, '', window.location.pathname + (rest ? '?' + rest : ''));
  }

  /* Pencarian percakapan: disaring di browser, tetap berlaku setelah daftar diperbarui */
  const convSearch = document.getElementById('conv-search');
  const applyConvFilter = () => {
    if (!convSearch) return;
    const q = convSearch.value.trim().toLowerCase();
    const items = document.querySelectorAll('.conv-item');
    const emptyMsg = document.getElementById('conv-empty');
    let shown = 0;
    items.forEach((el) => {
      const match = !q || el.dataset.search.includes(q);
      el.hidden = !match;
      if (match) shown += 1;
    });
    if (emptyMsg) emptyMsg.hidden = !(q && items.length > 0 && shown === 0);
  };
  if (convSearch) convSearch.addEventListener('input', applyConvFilter);
  document.body.addEventListener('htmx:afterSwap', (e) => {
    if (e.target.id === 'conv-list') applyConvFilter();
  });

  /* Penanganan error request HTMX (polling GET diabaikan) */
  document.body.addEventListener('htmx:responseError', (e) => {
    const { xhr, requestConfig } = e.detail;
    if (requestConfig && requestConfig.verb === 'get') return;
    const text = xhr.responseText || '';
    if (xhr.status === 413) toast('File terlalu besar untuk server.', 'error');
    else if (xhr.status === 403) toast('Kamu tidak punya izin untuk aksi ini.', 'error');
    else if (xhr.status === 400 && text && !text.startsWith('<')) toast(text.slice(0, 200), 'error');
    else toast(`Terjadi kesalahan (kode ${xhr.status}).`, 'error');
  });
  document.body.addEventListener('htmx:sendError', (e) => {
    const cfg = e.detail && e.detail.requestConfig;
    if (cfg && cfg.verb === 'get') return;
    toast('Koneksi bermasalah. Coba lagi.', 'error');
  });

  /* ---- Bagian berikut hanya untuk halaman dengan chat room terbuka ---- */
  const box = document.getElementById('messages');
  const form = document.getElementById('message-form');
  if (!box || !form) return;

  let stick = true;
  const toBottom = () => { box.scrollTop = box.scrollHeight; };

  /* Scroll otomatis ke pesan terbaru */
  toBottom();
  window.addEventListener('load', () => setTimeout(toBottom, 100));
  box.addEventListener('scroll', () => {
    stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  });
  form.addEventListener('submit', () => { stick = true; });
  form.addEventListener('htmx:afterRequest', (e) => {
    if (e.detail.successful) form.reset();
  });
  document.body.addEventListener('htmx:afterSwap', (e) => {
    if (e.target === box && stick) toBottom();
  });

  /* Kolom pesan: Enter kirim, Shift+Enter baris baru, tinggi otomatis, hitungan karakter */
  const msgInput = form.querySelector('textarea[name="content"]');
  const counter = document.getElementById('char-count');
  if (msgInput) {
    const grow = () => {
      msgInput.style.height = 'auto';
      msgInput.style.height = Math.min(msgInput.scrollHeight, 128) + 'px';
      msgInput.style.overflowY = msgInput.scrollHeight > 128 ? 'auto' : 'hidden';
      if (counter) {
        const left = msgInput.maxLength - msgInput.value.length;
        counter.hidden = left > 200;
        counter.textContent = left + ' karakter tersisa';
      }
    };
    msgInput.addEventListener('input', grow);
    msgInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        if (msgInput.value.trim()) form.requestSubmit();
      }
    });
    form.addEventListener('htmx:afterRequest', () => setTimeout(grow, 0));
    grow();
  }

  /* Menu lampiran: tutup setelah satu pilihan diklik */
  const attachMenu = document.getElementById('attach-menu');
  if (attachMenu) {
    attachMenu.querySelectorAll('.menu-item').forEach((b) => {
      b.addEventListener('click', () => attachMenu.removeAttribute('open'));
    });
  }

  /* Lampiran: foto, kamera, dokumen */
  const attachForm = document.getElementById('attach-form');
  const attachInput = document.getElementById('attach-input');
  if (attachForm && attachInput) {
    const buttons = document.querySelectorAll('.upload-btn');
    const status = document.getElementById('upload-status');
    const statusName = document.getElementById('upload-name');
    const statusPct = document.getElementById('upload-pct');
    const statusBar = document.getElementById('upload-bar');

    const setUploading = (on, name = '') => {
      if (status) status.classList.toggle('hidden', !on);
      buttons.forEach((b) => { b.disabled = on; });
      if (statusName) statusName.textContent = on ? `Mengunggah ${name}...` : '';
      if (statusPct) statusPct.textContent = '0%';
      if (statusBar) statusBar.style.width = '0%';
    };

    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        attachInput.accept = btn.dataset.accept;
        if (btn.dataset.capture) attachInput.setAttribute('capture', btn.dataset.capture);
        else attachInput.removeAttribute('capture');
        attachInput.click();
      });
    });

    attachForm.addEventListener('change', () => { stick = true; });
    attachForm.addEventListener('htmx:beforeRequest', (e) => {
      const file = attachInput.files[0];
      if (!file) { e.preventDefault(); return; }
      const isImage = /\.(jpe?g|png|webp|gif)$/i.test(file.name);
      const limit = Number(isImage ? attachForm.dataset.maxImage : attachForm.dataset.maxDoc);
      if (limit && file.size > limit) {
        e.preventDefault();
        toast(`File terlalu besar. Maksimal ${Math.round(limit / 1048576)} MB.`, 'error');
        attachForm.reset();
        return;
      }
      setUploading(true, file.name);
    });
    attachForm.addEventListener('htmx:xhr:progress', (e) => {
      if (!e.detail.lengthComputable) return;
      const pct = Math.round((e.detail.loaded / e.detail.total) * 100);
      if (statusPct) statusPct.textContent = pct + '%';
      if (statusBar) statusBar.style.width = pct + '%';
    });
    attachForm.addEventListener('htmx:afterRequest', (e) => {
      setUploading(false);
      if (e.detail.successful) toast('Berkas terkirim');
    });
    attachForm.addEventListener('htmx:sendError', () => setUploading(false));
  }

  /* Modal konfirmasi hapus pesan: satu modal dipakai untuk semua pesan */
  const modal = document.getElementById('confirm-modal');
  const okBtn = document.getElementById('confirm-modal-ok');
  if (modal && okBtn) {
    document.addEventListener('click', (e) => {
      const trigger = e.target.closest('[data-confirm-url]');
      if (!trigger) return;
      okBtn.setAttribute('hx-post', trigger.dataset.confirmUrl);
      htmx.process(okBtn);
      modal.showPopover();
    });
    okBtn.addEventListener('htmx:afterRequest', (e) => {
      if (modal.matches(':popover-open')) modal.hidePopover();
      if (e.detail.successful) toast('Pesan dihapus');
    });
  }
})();