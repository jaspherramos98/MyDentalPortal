// treatment-add.js — extracted from templates/treatments/add.html (2026-09-26).
// Treatment add form: live balance display.
// Auto-calculate balance
const charged = document.getElementById('amount_charged');
const paid = document.getElementById('amount_paid');
const balance = document.getElementById('balance_display');

function updateBalance() {
    const c = parseFloat(charged.value) || 0;
    const p = parseFloat(paid.value) || 0;
    balance.value = (c - p).toFixed(2);
}
charged.addEventListener('input', updateBalance);
paid.addEventListener('input', updateBalance);
