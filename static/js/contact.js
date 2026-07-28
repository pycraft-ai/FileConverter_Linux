/**
 * contact.js -- 联系作者页面
 */
$(function () {
    var repliesUrl = $('#contactPanel').data('replies-url') || '';

    // 提交留言
    document.getElementById('contactForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var form = e.target;
        var formData = new FormData(form);

        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            alert(data.message);
            if (data.success) {
                form.reset();
                loadReplies();
            }
        })
        .catch(function () { alert('提交失败，请重试'); });
    });

    // 加载回复
    if (repliesUrl) {
        loadReplies();
    }

    function loadReplies() {
        fetch(repliesUrl)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var container = document.getElementById('repliesContainer');
                if (!container) return;
                if (!data.success || !data.replies || data.replies.length === 0) {
                    container.innerHTML = '<p class="text-muted text-center">暂无回复</p>';
                    return;
                }
                container.innerHTML = data.replies.map(function (r) {
                    return '<div class="reply-item" style="padding:12px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:8px;">' +
                        '<div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">' +
                        '<i class="fas fa-user"></i> 回复于 ' + r.created_at + '</div>' +
                        '<div style="color:var(--text-primary);">' + escapeHtml(r.content) + '</div></div>';
                }).join('');
            })
            .catch(function (err) { console.error('加载回复失败:', err); });
    }
});
