// confirm-dialog.js — the app's own confirm popup, replacing the browser's
// built-in confirm dialog (unstyled, titled with the site address, a system
// alert on iPad).
//
//   AppConfirm(message, {title, confirmText, cancelText, danger}) -> Promise<boolean>
//
// Forms opt in declaratively — no inline JS:
//   <form method="POST" data-confirm="Delete this file?"
//         data-confirm-title="Delete file" data-confirm-ok="Delete" data-confirm-danger>
//
// The submit listener runs on WINDOW in the capture phase, i.e. before every
// other submit handler (resilient-submit's document listener, base-ui's
// spinner, page validators). Unconfirmed: the event is stopped. Confirmed: the
// form is re-submitted with requestSubmit() so those handlers run normally.
// Messages go in via textContent, so record names can't inject markup.
// Loaded synchronously in <head> by partials/_head_common.html; builds its
// modal lazily (needs Bootstrap's JS, loaded later in the page).
(function () {
    let modalEl = null;
    let modal = null;

    function build() {
        modalEl = document.createElement('div');
        modalEl.className = 'modal fade';
        modalEl.id = 'appConfirmModal';
        modalEl.tabIndex = -1;
        modalEl.setAttribute('aria-labelledby', 'appConfirmTitle');
        modalEl.setAttribute('aria-hidden', 'true');
        modalEl.innerHTML =
            '<div class="modal-dialog modal-dialog-centered">' +
              '<div class="modal-content">' +
                '<div class="modal-header">' +
                  '<h5 class="modal-title" id="appConfirmTitle"></h5>' +
                  '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
                '</div>' +
                '<div class="modal-body"><p class="mb-0" id="appConfirmMessage"></p></div>' +
                '<div class="modal-footer">' +
                  '<button type="button" class="btn btn-outline-secondary" id="appConfirmCancel" data-bs-dismiss="modal"></button>' +
                  '<button type="button" class="btn" id="appConfirmOk"></button>' +
                '</div>' +
              '</div>' +
            '</div>';
        document.body.appendChild(modalEl);
        modal = new bootstrap.Modal(modalEl);
    }

    function AppConfirm(message, options) {
        const opts = options || {};
        if (!window.bootstrap) return Promise.resolve(window.confirm(message));  // never block an action
        if (!modalEl) build();
        modalEl.querySelector('#appConfirmTitle').textContent = opts.title || 'Please confirm';
        modalEl.querySelector('#appConfirmMessage').textContent = message;
        const ok = modalEl.querySelector('#appConfirmOk');
        ok.textContent = opts.confirmText || 'OK';
        modalEl.querySelector('#appConfirmCancel').textContent = opts.cancelText || 'Cancel';
        ok.className = 'btn ' + (opts.danger ? 'btn-danger' : 'btn-primary');

        // Bootstrap modals don't stack (their focus traps fight), so a confirm
        // asked from inside an open dialog swaps it out and puts it back on
        // Cancel. data-confirm-swap tells that dialog's own close handlers
        // (e.g. the calendar's unsaved-changes guard) this isn't a real close.
        const open = document.querySelector('.modal.show:not(#appConfirmModal)');
        const openModal = open ? bootstrap.Modal.getInstance(open) : null;

        return new Promise(function (resolve) {
            let confirmed = false;
            function onOk() { confirmed = true; modal.hide(); }
            function onHidden() {
                ok.removeEventListener('click', onOk);
                modalEl.removeEventListener('hidden.bs.modal', onHidden);
                if (openModal && !confirmed) {
                    open.addEventListener('shown.bs.modal', function () {
                        delete open.dataset.confirmSwap;
                    }, { once: true });
                    openModal.show();
                } else if (open) {
                    delete open.dataset.confirmSwap;
                }
                resolve(confirmed);
            }
            function ask() {
                ok.addEventListener('click', onOk);
                modalEl.addEventListener('hidden.bs.modal', onHidden);
                modalEl.addEventListener('shown.bs.modal', function () { ok.focus(); }, { once: true });
                modal.show();
            }
            if (openModal) {
                open.dataset.confirmSwap = '1';
                open.addEventListener('hidden.bs.modal', ask, { once: true });
                openModal.hide();
            } else {
                ask();
            }
        });
    }

    window.addEventListener('submit', function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-confirm')) return;
        if (form.dataset.confirmed === '1') {   // second pass, after OK
            delete form.dataset.confirmed;
            return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        const submitter = event.submitter || null;
        AppConfirm(form.getAttribute('data-confirm'), {
            title: form.getAttribute('data-confirm-title'),
            confirmText: form.getAttribute('data-confirm-ok'),
            cancelText: form.getAttribute('data-confirm-cancel'),
            danger: form.hasAttribute('data-confirm-danger'),
        }).then(function (yes) {
            if (!yes) return;
            form.dataset.confirmed = '1';
            if (submitter && submitter.form === form) form.requestSubmit(submitter);
            else form.requestSubmit();
        });
    }, true);

    window.AppConfirm = AppConfirm;
})();
