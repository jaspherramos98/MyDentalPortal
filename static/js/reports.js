// reports.js — extracted from templates/reports/index.html (2026-09-26).
// Performance page charts (Chart.js); data from the #reports-data JSON island.
(function () {
    const D = JSON.parse(document.getElementById('reports-data').textContent);
    const sym = D.symbol || '';
    const money = (v) => sym + Number(v).toLocaleString(undefined, {maximumFractionDigits: 0});
    const palette = ['#0d6efd','#1e9e6a','#fd7e14','#6f42c1','#20c4d4','#dc3545','#e0a800','#59359a','#1399a6'];

    Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
    Chart.defaults.color = '#5a6473';

    // Revenue over time (billed line + paid filled area)
    new Chart(document.getElementById('revenueChart'), {
        type: 'line',
        data: {
            labels: D.month_labels,
            datasets: [
                {
                    label: 'Collected', data: D.monthly_paid,
                    borderColor: '#1e9e6a', backgroundColor: 'rgba(30,158,106,.15)',
                    fill: true, tension: .35, borderWidth: 2, pointRadius: 3,
                },
                {
                    label: 'Billed', data: D.monthly_billed,
                    borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,.05)',
                    fill: false, tension: .35, borderWidth: 2, borderDash: [5,4], pointRadius: 2,
                },
            ],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { tooltip: { callbacks: { label: (c) => c.dataset.label + ': ' + money(c.parsed.y) } } },
            scales: { y: { beginAtZero: true, ticks: { callback: (v) => money(v) } } },
        },
    });

    // Collected vs Outstanding doughnut
    new Chart(document.getElementById('collectionChart'), {
        type: 'doughnut',
        data: {
            labels: ['Collected', 'Outstanding'],
            datasets: [{ data: [D.collected, D.outstanding], backgroundColor: ['#1e9e6a','#e0a800'], borderWidth: 0 }],
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '62%',
            plugins: {
                legend: { position: 'bottom' },
                tooltip: { callbacks: { label: (c) => c.label + ': ' + money(c.parsed) } },
            },
        },
    });

    // Top procedures (horizontal bar)
    new Chart(document.getElementById('procChart'), {
        type: 'bar',
        data: {
            labels: D.proc_labels,
            datasets: [{ label: 'Revenue', data: D.proc_values, backgroundColor: '#0d6efd', borderRadius: 5 }],
        },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false },
                tooltip: { callbacks: { label: (c) => money(c.parsed.x) } } },
            scales: { x: { beginAtZero: true, ticks: { callback: (v) => money(v) } } },
        },
    });

    // Treatments by status (doughnut)
    new Chart(document.getElementById('statusChart'), {
        type: 'doughnut',
        data: {
            labels: D.status_labels,
            datasets: [{ data: D.status_values, backgroundColor: palette, borderWidth: 0 }],
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '58%',
            plugins: { legend: { position: 'bottom' } },
        },
    });

    // New patients per month (bar)
    new Chart(document.getElementById('patientsChart'), {
        type: 'bar',
        data: {
            labels: D.month_labels,
            datasets: [{ label: 'New patients', data: D.monthly_new, backgroundColor: '#fd7e14', borderRadius: 5 }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        },
    });
})();
