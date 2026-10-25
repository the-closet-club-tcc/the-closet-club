/* chat.js: scroll, lampiran, modal konfirmasi, dan penanganan error halaman chat. */
(function () {
  const box = document.getElementById('messages');
  const form = document.getElementById('message-form');
  if (!box || !form) return; // halaman tanpa percakapan terpilih

  const toast = (msg, kind) => window.showToast(msg, kind);
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
  }

  /* Modal konfirmasi hapus: satu modal dipakai untuk semua pesan */
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

  /* Penanganan error untuk semua request HTMX (kecuali polling GET) */
  document.body.addEventListener('htmx:responseError', (e) => {
    const { xhr, requestConfig } = e.detail;
    if (requestConfig && requestConfig.verb === 'get') return;
    const text = xhr.responseText || '';
    if (xhr.status === 413) toast('File terlalu besar untuk server.', 'error');
    else if (xhr.status === 403) toast('Kamu tidak punya izin untuk aksi ini.', 'error');
    else if (xhr.status === 400 && text && !text.startsWith('<')) toast(text.slice(0, 200), 'error');
    else toast(`Terjadi kesalahan (kode ${xhr.status}).`, 'error');
  });
  document.body.addEventListener('htmx:sendError', () => {
    toast('Koneksi bermasalah. Coba lagi.', 'error');
  });
})();