/* chat.js: chat page behavior. */
(function () {
  const toast = (msg, kind) => window.showToast(msg, kind);

  /* Notifications after redirect (?deleted=1, ?blocked=1, etc.) */
  const NOTICES = {
    deleted: ['Conversation deleted', 'success'],
    blocked: ['User blocked', 'success'],
    unblocked: ['User unblocked', 'success'],
    accepted: ['Conversation accepted', 'success'],
    cannot_start: ['Cannot start conversation with this user.', 'error'],
  };

  const params = new URLSearchParams(window.location.search);
  let noticed = false;

  Object.keys(NOTICES).forEach((key) => {
    if (params.get(key)) {
      toast(NOTICES[key][0], NOTICES[key][1]);
      params.delete(key);
      noticed = true;
    }
  });

  if (noticed) {
    const rest = params.toString();
    history.replaceState(null, '', window.location.pathname + (rest ? '?' + rest : ''));
  }

  /* Conversation search */
  function applyConvFilter() {
    const input = document.getElementById('conv-search');
    const list = document.getElementById('conv-list');

    if (!input || !list) return;

    const query = input.value.trim().toLowerCase();
    const items = list.querySelectorAll('.conv-item');
    const emptyMsg = document.getElementById('conv-empty');
    let shown = 0;

    items.forEach((item) => {
      const searchText = (item.dataset.search || '').toLowerCase();
      const match = !query || searchText.includes(query);

      item.classList.toggle('conv-hidden', !match);

      // Inline !important avoids conflict with Tailwind utilities.
      if (match) {
        item.style.removeProperty('display');
      } else {
        item.style.setProperty('display', 'none', 'important');
      }

      shown += match ? 1 : 0;
    });

    if (emptyMsg) {
      const showEmpty = Boolean(query && items.length > 0 && shown === 0);

      emptyMsg.classList.toggle('conv-hidden', !showEmpty);

      if (showEmpty) {
        emptyMsg.style.removeProperty('display');
      } else {
        emptyMsg.style.setProperty('display', 'none', 'important');
      }
    }
  }

  // Delegated event so it keeps working if elements are swapped.
  document.addEventListener('input', (event) => {
    if (event.target.id === 'conv-search') {
      applyConvFilter();
    }
  });

  document.addEventListener('search', (event) => {
    if (event.target.id === 'conv-search') {
      applyConvFilter();
    }
  });

  // Re-apply after HTMX swaps the conversation list.
  document.body.addEventListener('htmx:afterSwap', (event) => {
    if (
      event.target.id === 'conv-list' ||
      event.target.querySelector?.('#conv-list')
    ) {
      applyConvFilter();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyConvFilter, {
      once: true
    });
  } else {
    applyConvFilter();
  }

  /* HTMX request error handling (GET polling ignored) */
  document.body.addEventListener('htmx:responseError', (e) => {
    const { xhr, requestConfig } = e.detail;

    if (requestConfig && requestConfig.verb === 'get') return;

    const text = xhr.responseText || '';
    const plain = text && !text.startsWith('<');

    if (xhr.status === 413) {
      toast('File too large for server.', 'error');
    } else if (xhr.status === 403) {
      toast(
        plain ? text.slice(0, 200) : 'You do not have permission for this action.',
        'error'
      );
    } else if (xhr.status === 400 && plain) {
      toast(text.slice(0, 200), 'error');
    } else {
      toast(`An error occurred (code ${xhr.status}).`, 'error');
    }
  });

  document.body.addEventListener('htmx:sendError', (e) => {
    const cfg = e.detail && e.detail.requestConfig;

    if (cfg && cfg.verb === 'get') return;

    toast('Connection error. Please try again.', 'error');
  });

  /* ---- The following section is only for pages with an open chat room ---- */
  const box = document.getElementById('messages');
  const form = document.getElementById('message-form');

  // No open chat room.
  if (!box) return;

  let stick = true;

  const toBottom = () => {
    box.scrollTop = box.scrollHeight;
  };

  /* Automatically scroll to latest message */
  toBottom();

  window.addEventListener('load', () => setTimeout(toBottom, 100));

  box.addEventListener('scroll', () => {
    stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  });

  if (form) {
    form.addEventListener('submit', () => {
      stick = true;
    });

    form.addEventListener('htmx:afterRequest', (e) => {
      if (e.detail.successful) {
        form.reset();
        clearReply();
      }
    });
  }

  document.body.addEventListener('htmx:afterSwap', (e) => {
    if (e.target === box && stick) toBottom();
  });

  document.addEventListener('click', (e) => {
    if (e.target.closest('.quick-chip')) stick = true;
  });

  /* Message input: Enter to send, Shift+Enter for new line,
     auto height, character counter */
  const msgInput = form ? form.querySelector('textarea[name="content"]') : null;
  const counter = document.getElementById('char-count');

  if (msgInput) {
    const grow = () => {
      msgInput.style.height = 'auto';
      msgInput.style.height = Math.min(msgInput.scrollHeight, 128) + 'px';
      msgInput.style.overflowY = msgInput.scrollHeight > 128 ? 'auto' : 'hidden';

      if (counter) {
        const left = msgInput.maxLength - msgInput.value.length;
        counter.hidden = left > 200;
        counter.textContent = left + ' characters remaining';
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

  /* Reply to specific message */
  const replyInput = document.getElementById('reply-to-input');
  const replyChip = document.getElementById('reply-chip');
  const replyWho = document.getElementById('reply-who');
  const replyText = document.getElementById('reply-text');
  const replyCancel = document.getElementById('reply-cancel');

  const clearReply = () => {
    if (!replyInput) return;

    replyInput.value = '';

    if (replyChip) replyChip.classList.add('hidden');
  };

  const setReply = (id, who, text) => {
    if (!replyInput || !replyChip) return;

    replyInput.value = id;
    replyWho.textContent = who;
    replyText.textContent = text;
    replyChip.classList.remove('hidden');

    if (msgInput) msgInput.focus();
  };

  if (replyCancel) replyCancel.addEventListener('click', clearReply);

  if (msgInput) {
    msgInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && replyInput && replyInput.value) {
        clearReply();
      }
    });
  }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-reply-id]');

    if (btn) {
      setReply(
        btn.dataset.replyId,
        btn.dataset.replyWho,
        btn.dataset.replyText
      );
    }
  });

  /* Safety banner: dismissible, remembered per conversation */
  const safety = document.getElementById('safety-banner');

  if (safety) {
    const key = 'chat-safety-dismissed-' + (safety.dataset.conv || '');

    try {
      if (localStorage.getItem(key) === '1') {
        safety.classList.add('is-gone');
      }
    } catch (err) {
      /* Browser storage disabled: banner remains visible */
    }

    const dismiss = document.getElementById('safety-dismiss');

    if (dismiss) {
      dismiss.addEventListener('click', () => {
        safety.classList.add('is-gone');

        try {
          localStorage.setItem(key, '1');
        } catch (err) {
          /* Ignore */
        }
      });
    }
  }

  /* Header options menu: close after selecting an option */
  const roomMenu = document.getElementById('room-menu');

  if (roomMenu) {
    roomMenu.querySelectorAll('.menu-item').forEach((b) => {
      b.addEventListener('click', () => roomMenu.removeAttribute('open'));
    });
  }

  /* Report modal: single modal used for both user reports and message reports */
  const reportModal = document.getElementById('report-modal');
  const reportForm = document.getElementById('report-form');

  if (reportModal && reportForm) {
    const reportMsgId = document.getElementById('report-message-id');
    const reportTarget = document.getElementById('report-target');

    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-report-message]');

      if (!btn) return;

      reportMsgId.value = btn.dataset.reportMessage || '';

      reportTarget.textContent = btn.dataset.reportLabel
        ? `Reporting message: "${btn.dataset.reportLabel}"`
        : `Reporting ${reportModal.dataset.user || 'user'}`;

      reportModal.showPopover();
    });

    reportForm.addEventListener('htmx:afterRequest', (e) => {
      if (!e.detail.successful) return;

      reportForm.reset();

      if (reportModal.matches(':popover-open')) {
        reportModal.hidePopover();
      }

      toast('Report sent. Thank you.');
    });
  }

  /* Attachment menu: close after selecting an option */
  const attachMenu = document.getElementById('attach-menu');

  if (attachMenu) {
    attachMenu.querySelectorAll('.menu-item').forEach((b) => {
      b.addEventListener('click', () => attachMenu.removeAttribute('open'));
    });
  }

  /* Attachments: photo, camera, document */
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

      buttons.forEach((b) => {
        b.disabled = on;
      });

      if (statusName) statusName.textContent = on ? `Uploading ${name}...` : '';
      if (statusPct) statusPct.textContent = '0%';
      if (statusBar) statusBar.style.width = '0%';
    };

    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        attachInput.accept = btn.dataset.accept;

        if (btn.dataset.capture) {
          attachInput.setAttribute('capture', btn.dataset.capture);
        } else {
          attachInput.removeAttribute('capture');
        }

        attachInput.click();
      });
    });

    attachForm.addEventListener('change', () => {
      stick = true;
    });

    attachForm.addEventListener('htmx:beforeRequest', (e) => {
      const file = attachInput.files[0];

      if (!file) {
        e.preventDefault();
        return;
      }

      const isImage = /\.(jpe?g|png|webp|gif)$/i.test(file.name);
      const limit = Number(
        isImage ? attachForm.dataset.maxImage : attachForm.dataset.maxDoc
      );

      if (limit && file.size > limit) {
        e.preventDefault();

        toast(
          `File is too large. Maximum size is ${Math.round(limit / 1048576)} MB.`,
          'error'
        );

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

      if (e.detail.successful) toast('File sent');
    });

    attachForm.addEventListener('htmx:sendError', () => setUploading(false));
  }

  /* Delete message confirmation modal: single modal used for all messages */
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

      if (e.detail.successful) toast('Message deleted');
    });
  }
})();