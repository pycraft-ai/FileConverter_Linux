/**
 * contacts-manage.js -- 联系消息管理
 */
$(function () {
    var managePanel = document.getElementById('contactsManagePanel');
    var markReadUrl = managePanel ? managePanel.getAttribute('data-mark-read-url') : '';
    var replyUrl = managePanel ? managePanel.getAttribute('data-reply-url') : '';

    // 安全读取 data-* 属性（属性值由服务端 tojson 编码，需 JSON.parse 还原原始字符串）
    function readJsonAttr($el, name) {
        var raw = $el.attr(name);
        if (!raw) return '';
        try { return JSON.parse(raw); } catch (e) { return ''; }
    }

    // 将文本插入为纯文本节点（避免 XSS）
    function appendText(parent, text) {
        parent.appendChild(document.createTextNode(text));
    }

    // 查看消息详情
    window.viewMessage = function (id) {
        var $row = $('#row' + id);
        var replies = [];
        var rawReplies = $row.attr('data-replies');
        if (rawReplies) {
            try { replies = JSON.parse(rawReplies); } catch (e) {}
        }

        var message = readJsonAttr($row, 'data-message');
        var name = readJsonAttr($row, 'data-name');
        var email = readJsonAttr($row, 'data-email');
        var subject = readJsonAttr($row, 'data-subject');
        var createdAt = readJsonAttr($row, 'data-created-at');

        var $body = $('#viewMessageBody').empty();

        // 使用 createElement + textContent 构建，绝不使用 .html() 拼接用户内容
        var field = function (label, value, isEmail) {
            var div = document.createElement('div');
            div.className = 'mb-3';
            var strong = document.createElement('strong');
            appendText(strong, label);
            div.appendChild(strong);
            if (isEmail && value) {
                var a = document.createElement('a');
                a.href = 'mailto:' + value;
                a.className = 'text-info';
                appendText(a, value);
                div.appendChild(a);
            } else {
                var span = document.createElement('span');
                appendText(span, value);
                div.appendChild(span);
            }
            $body[0].appendChild(div);
        };

        field('姓名：', name, false);
        field('邮箱：', email, true);
        field('主题：', subject, false);
        field('时间：', createdAt, false);

        var hr = document.createElement('hr');
        hr.className = 'border-secondary';
        $body[0].appendChild(hr);

        var labelDiv = document.createElement('div');
        labelDiv.className = 'mb-3';
        var labelStrong = document.createElement('strong');
        appendText(labelStrong, '内容：');
        labelDiv.appendChild(labelStrong);
        $body[0].appendChild(labelDiv);

        var contentDiv = document.createElement('div');
        contentDiv.className = 'p-3 bg-secondary bg-opacity-25 rounded';
        // 将换行替换为 <br>，但其余内容按纯文本处理
        var lines = String(message || '').split('\n');
        lines.forEach(function (line, idx) {
            if (idx > 0) contentDiv.appendChild(document.createElement('br'));
            appendText(contentDiv, line);
        });
        $body[0].appendChild(contentDiv);

        if (replies && replies.length > 0) {
            var hr2 = document.createElement('hr');
            hr2.className = 'border-secondary';
            $body[0].appendChild(hr2);

            var repLabel = document.createElement('div');
            repLabel.className = 'mb-2';
            var repStrong = document.createElement('strong');
            appendText(repStrong, '回复记录（' + replies.length + ' 条）：');
            repLabel.appendChild(repStrong);
            $body[0].appendChild(repLabel);

            replies.forEach(function (r) {
                var box = document.createElement('div');
                box.className = 'mb-2 p-2 rounded';
                box.style.background = 'rgba(255,255,255,0.05)';

                var head = document.createElement('div');
                head.className = 'd-flex justify-content-between mb-1';

                var badge = document.createElement('span');
                badge.className = 'badge ' + (r.author_type === 'admin' ? 'bg-success' : 'bg-primary');
                appendText(badge, r.author_type === 'admin' ? '管理员' : '用户');
                head.appendChild(badge);

                var small = document.createElement('small');
                small.className = 'text-muted';
                appendText(small, r.created_at || '');
                head.appendChild(small);

                box.appendChild(head);

                var bodyDiv = document.createElement('div');
                var repLines = String(r.content || '').split('\n');
                repLines.forEach(function (line, idx) {
                    if (idx > 0) bodyDiv.appendChild(document.createElement('br'));
                    appendText(bodyDiv, line);
                });
                box.appendChild(bodyDiv);

                $body[0].appendChild(box);
            });
        }

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
