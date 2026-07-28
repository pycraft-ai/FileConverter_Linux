/**
 * contacts-manage.js -- 联系消息管理
 */
$(function () {
    var managePanel = document.getElementById('contactsManagePanel');
    var markReadUrl = managePanel ? managePanel.getAttribute('data-mark-read-url') : '';
    var replyUrl = managePanel ? managePanel.getAttribute('data-reply-url') : '';

    // 查看消息详情
    window.viewMessage = function (id) {
        var $row = $('#row' + id);
        var replies = [];
        var rawReplies = $row.attr('data-replies');
        if (rawReplies) {
            try { replies = JSON.parse(rawReplies); } catch (e) {}
        }

        var message = $row.attr('data-message') || '';
        var name = $row.attr('data-name') || '';
        var email = $row.attr('data-email') || '';
        var subject = $row.attr('data-subject') || '';
        var createdAt = $row.attr('data-created-at') || '';

        var html = '';
        html += '<div class="mb-3"><strong>姓名：</strong>' + name + '</div>';
        html += '<div class="mb-3"><strong>邮箱：</strong><a href="mailto:' + email + '" class="text-info">' + email + '</a></div>';
        html += '<div class="mb-3"><strong>主题：</strong><span class="badge bg-info">' + subject + '</span></div>';
        html += '<div class="mb-3"><strong>时间：</strong>' + createdAt + '</div>';
        html += '<hr class="border-secondary">';
        html += '<div class="mb-3"><strong>内容：</strong></div>';
        html += '<div class="p-3 bg-secondary bg-opacity-25 rounded">' + message.replace(/\n/g, '<br>') + '</div>';

        if (replies && replies.length > 0) {
            html += '<hr class="border-secondary">';
            html += '<div class="mb-2"><strong><i class="fas fa-reply-all me-1"></i>回复记录（' + replies.length + ' 条）：</strong></div>';
            replies.forEach(function (r, i) {
                var badgeClass = r.author_type === 'admin' ? 'bg-success' : 'bg-primary';
                var author = r.author_type === 'admin' ? '管理员' : '用户';
                html += '<div class="mb-2 p-2 rounded" style="background:rgba(255,255,255,0.05);">';
                html += '<div class="d-flex justify-content-between mb-1">';
                html += '<span class="badge ' + badgeClass + '">' + author + '</span>';
                html += '<small class="text-muted">' + (r.created_at || '') + '</small>';
                html += '</div>';
                html += '<div>' + (r.content || '').replace(/\n/g, '<br>') + '</div>';
                html += '</div>';
            });
        }

        $('#viewMessageBody').html(html);
        var modal = new bootstrap.Modal(document.getElementById('viewMessageModal'));
        modal.show();

        // 标记已读
        markAsRead(id);
    };

    // 标记已读
    window.markAsRead = function (id) {
        if (!markReadUrl) return;
        $.post(markReadUrl, { id: id }, function (res) {
            if (res.success) {
                $('#row' + id).removeClass('fw-bold');
                $('#row' + id).find('.badge.bg-danger').removeClass('bg-danger').addClass('bg-secondary').text('已读');
            }
        });
    };

    // 打开回复模态框
    window.showReplyModal = function (id) {
        $('#replyMessageId').val(id);
        $('#replyText').val('');
        var modal = new bootstrap.Modal(document.getElementById('replyModal'));
        modal.show();
    };

    // 发送回复
    $('#replyForm').on('submit', function (e) {
        e.preventDefault();
        var messageId = $('#replyMessageId').val();
        var reply = $('#replyText').val().trim();
        if (!reply) { alert('回复内容不能为空'); return; }

        $.post(replyUrl, {
            id: messageId,
            reply: reply
        }, function (res) {
            alert(res.message);
            if (res.success) {
                // 隐藏模态框
                bootstrap.Modal.getInstance(document.getElementById('replyModal')).hide();
                location.reload();
            }
        }).fail(function (err) {
            alert('请求失败：' + err.statusText);
        });
    });
});
