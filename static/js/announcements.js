/**
 * announcements.js -- 公告管理
 * 依赖：#announceManage 上的 data-announce-*-url 属性
 */
$(function () {
    var $panel = $('#announceManage');
    var createUrl = $panel.data('announce-create-url') || '';
    var toggleUrl = $panel.data('announce-toggle-url') || '';
    var deleteUrl = $panel.data('announce-delete-url') || '';
    var editUrl = $panel.data('announce-edit-url') || '';

    // 发布公告
    $('#announcementForm').on('submit', function (e) {
        e.preventDefault();
        var title = $('#announceTitle').val().trim();
        var content = $('#announceContent').val().trim();
        if (!title || !content) { alert('标题和内容不能为空'); return; }

        var type = $('#announceType').val() || 'info';
        var priority = parseInt($('#announcePriority').val(), 10) || 0;
        var autoHide = parseInt($('#announceAutoHide').val(), 10) || 0;
        if (autoHide < 0) autoHide = 0;

        $.post(createUrl, {
            title: title,
            content: content,
            type: type,
            priority: priority,
            auto_hide_seconds: autoHide
        }, function (res) {
            alert(res.message);
            if (res.success) location.reload();
        });
    });

    // 切换公告状态
    $(document).on('click', '.toggle-btn', function () {
        var id = $(this).data('id');
        $.post(toggleUrl, { id: id }, function (res) {
            alert(res.message);
            if (res.success) location.reload();
        });
    });

    // 删除公告
    $(document).on('click', '.delete-btn', function () {
        var id = $(this).data('id');
        if (!confirm('确定要删除此公告吗？')) return;
        $.post(deleteUrl, { id: id }, function (res) {
            alert(res.message);
            if (res.success) location.reload();
        });
    });

    // 编辑公告：打开弹窗并填充数据
    $(document).on('click', '.edit-btn', function () {
        $('#editAnnounceId').val($(this).data('id'));
        $('#editAnnounceTitle').val($(this).data('title'));
        $('#editAnnounceContent').val($(this).data('content'));
        $('#editAnnounceType').val($(this).data('type') || 'info');
        $('#editAnnouncePriority').val($(this).data('priority') || 0);
        $('#editAnnounceAutoHide').val($(this).data('autohide') || 0);
        $('#editAnnounceModal').modal('show');
    });

    // 保存编辑
    $('#editAnnounceSave').on('click', function () {
        var id = $('#editAnnounceId').val();
        var title = $('#editAnnounceTitle').val().trim();
        var content = $('#editAnnounceContent').val().trim();
        if (!title || !content) { alert('标题和内容不能为空'); return; }

        var type = $('#editAnnounceType').val() || 'info';
        var priority = parseInt($('#editAnnouncePriority').val(), 10) || 0;
        var autoHide = parseInt($('#editAnnounceAutoHide').val(), 10) || 0;
        if (autoHide < 0) autoHide = 0;

        $.post(editUrl, {
            id: id,
            title: title,
            content: content,
            type: type,
            priority: priority,
            auto_hide_seconds: autoHide
        }, function (res) {
            alert(res.message);
            if (res.success) {
                $('#editAnnounceModal').modal('hide');
                location.reload();
            }
        });
    });
});
