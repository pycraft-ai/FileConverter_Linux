/**
 * announcements.js -- 公告管理
 * 依赖：#announceManage 上的 data-announce-*-url 属性
 */
$(function () {
    var $panel = $('#announceManage');
    var createUrl = $panel.data('announce-create-url') || '';
    var toggleUrl = $panel.data('announce-toggle-url') || '';
    var deleteUrl = $panel.data('announce-delete-url') || '';

    // 发布公告
    $('#announcementForm').on('submit', function (e) {
        e.preventDefault();
        var title = $('#announceTitle').val().trim();
        var content = $('#announceContent').val().trim();
        if (!title || !content) { alert('标题和内容不能为空'); return; }

        $.post(createUrl, { title: title, content: content }, function (res) {
            alert(res.message);
            if (res.success) location.reload();
        });
    });

    // 切换公告状态
    $(document).on('click', '.toggle-announce-btn', function () {
        var id = $(this).data('id');
        $.post(toggleUrl, { announcement_id: id }, function (res) {
            alert(res.message);
            if (res.success) location.reload();
        });
    });

    // 删除公告
    $(document).on('click', '.delete-announce-btn', function () {
        var id = $(this).data('id');
        if (!confirm('确定要删除此公告吗？')) return;
        $.post(deleteUrl, { announcement_id: id }, function (res) {
            alert(res.message);
            if (res.success) location.reload();
        });
    });
});
