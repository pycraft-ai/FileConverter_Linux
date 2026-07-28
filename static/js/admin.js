/**
 * admin.js -- 管理面板脚本
 * 标签切换、用户管理操作（封禁/解封/续期/充值）
 */

$(function () {
    // ===== 标签切换 =====
    $('.tab-btn').on('click', function () {
        var tab = $(this).data('tab');
        $('.tab-btn').removeClass('active');
        $(this).addClass('active');
        $('.tab-panel').removeClass('active');
        $('#' + tab).addClass('active');
        // 切换到图表标签时初始化图表
        if (tab === 'tab-charts' && typeof initAdminCharts === 'function') {
            initAdminCharts();
        }
    });

    // 如果 URL hash 指向 charts，自动切换
    if (window.location.hash === '#charts') {
        $('.tab-btn[data-tab="tab-charts"]').trigger('click');
    }

    // ===== 封禁/解封 =====
    $('.block-btn').click(function () {
        var username = $(this).data('username');
        if (!confirm('确认要操作用户 ' + username + ' 的封禁状态吗？')) return;

        $.post($(this).closest('[data-admin-block-url]').data('admin-block-url') || '/admin/block',
            { username: username },
            function (response) {
                showAdminToast(response.message, response.success);
                if (response.success) setTimeout(function () { location.reload(); }, 1000);
            }
        );
    });

    // 续期
    $('.renew-btn').click(function () {
        $('#renewUsername').val($(this).data('username'));
        $('#renewModal').modal('show');
    });

    $('#renewForm').submit(function (e) {
        e.preventDefault();
        $.post($(this).data('admin-renew-url') || '/admin/renew',
            {
                username: $('#renewUsername').val(),
                days: $('#renewDays').val()
            },
            function (response) {
                showAdminToast(response.message, response.success);
                if (response.success) {
                    $('#renewModal').modal('hide');
                    setTimeout(function () { location.reload(); }, 1000);
                }
            }
        );
    });

    // 充值次数
    $('.times-btn').click(function () {
        $('#timesUsername').val($(this).data('username'));
        $('#timesModal').modal('show');
    });

    $('#timesForm').submit(function (e) {
        e.preventDefault();
        $.post($(this).data('admin-times-url') || '/admin/increase_times',
            {
                username: $('#timesUsername').val(),
                times: $('#timesCount').val()
            },
            function (response) {
                showAdminToast(response.message, response.success);
                if (response.success) {
                    $('#timesModal').modal('hide');
                    setTimeout(function () { location.reload(); }, 1000);
                }
            }
        );
    });

    // ===== Toast 提示 =====
    function showAdminToast(msg, success) {
        var icon = success ? 'check-circle' : 'exclamation-circle';
        var cls = success ? 'success' : 'danger';
        var $alert = $('<div class="alert alert-' + cls + ' alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-5" style="z-index:99999;">' +
            '<i class="fas fa-' + icon + ' me-2"></i>' + msg +
            '<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>');
        $('body').append($alert);
        setTimeout(function () { $alert.alert('close'); }, 3000);
    }
});
