/**
 * dashboard.js -- 用户仪表盘脚本
 * 图表渲染、筛选器联动
 */

$(function () {
    var currentCharts = {};

    function destroyCharts() {
        Object.values(currentCharts).forEach(function (c) { if (c) c.destroy(); });
        currentCharts = {};
    }

    function renderCharts(stats, byMode, trend) {
        destroyCharts();

        // 成功/失败 环形图
        var doughnutCtx = document.getElementById('successRateChart');
        if (doughnutCtx) {
            currentCharts.doughnut = new Chart(doughnutCtx, {
                type: 'doughnut',
                data: {
                    labels: ['成功', '失败'],
                    datasets: [{
                        data: [stats.success_count || 0, stats.fail_count || 0],
                        backgroundColor: ['#10b981', '#ef4444'],
                        borderWidth: 3,
                        borderColor: 'var(--bg-card)'
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: true,
                    plugins: {
                        legend: { position: 'bottom', labels: { padding: 16, usePointStyle: true, font: { size: 12 } } }
                    },
                    cutout: '60%'
                }
            });
        }

        // 按模式柱状图
        var barCtx = document.getElementById('modeBarChart');
        if (barCtx && byMode.length > 0) {
            var modeLabels = byMode.map(function (m) { return m.mode; });
            var modeSuccess = byMode.map(function (m) { return m.success_count; });
            var modeFail = byMode.map(function (m) { return m.fail_count; });

            currentCharts.bar = new Chart(barCtx, {
                type: 'bar',
                data: {
                    labels: modeLabels,
                    datasets: [
                        { label: '成功', data: modeSuccess, backgroundColor: '#10b981', borderRadius: 4 },
                        { label: '失败', data: modeFail, backgroundColor: '#ef4444', borderRadius: 4 }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: true,
                    plugins: { legend: { labels: { usePointStyle: true, padding: 12, font: { size: 11 } } } },
                    scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1 } } }
                }
            });
        }

        // 趋势折线图
        var trendCtx = document.getElementById('trendChart');
        if (trendCtx && trend.length > 0) {
            var tLabels = trend.map(function (t) { return t.day; });
            var tSuccess = trend.map(function (t) { return t.success_count; });
            var tFail = trend.map(function (t) { return t.fail_count; });

            currentCharts.trend = new Chart(trendCtx, {
                type: 'line',
                data: {
                    labels: tLabels,
                    datasets: [
                        { label: '成功', data: tSuccess, borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,.08)', fill: true, tension: .3, pointRadius: 4 },
                        { label: '失败', data: tFail, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,.08)', fill: true, tension: .3, pointRadius: 4 }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: true,
                    plugins: { legend: { labels: { usePointStyle: true, padding: 16, font: { size: 11 } } } },
                    scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
                }
            });
        }
    }

    // 初始渲染
    var initialData = document.getElementById('dashboard-init-data');
    if (initialData) {
        try {
            var init = JSON.parse(initialData.textContent);
            renderCharts(init.stats, init.by_mode, init.trend);
        } catch (e) {}
    }

    // 筛选器切换
    var apiUrl = (document.getElementById('dashboard-filter') || {}).getAttribute('data-api-url') || '';
    $('#modeFilter, #trendDays').on('change', function () {
        var mode = $('#modeFilter').val();
        var days = $('#trendDays').val();

        $.get(apiUrl, { mode: mode, days: days }, function (res) {
            if (!res.success) return;
            var s = res.stats;
            var rate = s.total > 0 ? (s.success_count / s.total * 100).toFixed(1) : 0;

            $('#statTotal').text(s.total);
            $('#statSuccess').text(s.success_count);
            $('#statFail').text(s.fail_count);
            $('#statRate').text(rate + '%');

            // 重建模式明细表
            var tbody = '';
            res.by_mode.forEach(function (m) {
                var mr = m.count > 0 ? (m.success_count / m.count * 100).toFixed(0) : 0;
                tbody += '<tr>' +
                    '<td><span class="mode-badge" style="background:rgba(102,126,234,.1);color:#667eea;">' + escapeHtml(m.mode) + '</span></td>' +
                    '<td><strong>' + m.count + '</strong></td>' +
                    '<td style="color:#10b981;">' + m.success_count + '</td>' +
                    '<td style="color:#ef4444;">' + m.fail_count + '</td>' +
                    '<td><span style="font-size:12px;">' + mr + '%</span>' +
                    '<div class="rate-bar-wrap"><div class="rate-bar-fill" style="width:' + mr + '%;"></div></div></td>' +
                    '</tr>';
            });
            $('#modeDetailTable tbody').html(tbody);

            renderCharts(s, res.by_mode, res.trend);
        });
    });
});
