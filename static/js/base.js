/**
 * base.js -- 全局基础脚本
 * 侧边栏切换、主题管理、CSRF 防护、消息轮询、Flash 消息
 */

// ===== 移动端侧边栏切换 =====
function toggleSidebar() {
    var sidebar = document.getElementById('appSidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (sidebar && overlay) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('show');
    }
}

document.addEventListener('DOMContentLoaded', function () {
    // 移动端菜单按钮
    var menuBtn = document.getElementById('mobileMenuBtn');
    if (menuBtn) {
        menuBtn.addEventListener('click', toggleSidebar);
    }
    // 遮罩层点击关闭
    var overlay = document.getElementById('sidebarOverlay');
    if (overlay) {
        overlay.addEventListener('click', toggleSidebar);
    }
    // 移动端主题按钮：循环切换
    var mobileThemeBtn = document.getElementById('mobileThemeBtn');
    if (mobileThemeBtn) {
        mobileThemeBtn.addEventListener('click', function () {
            var themes = ['light', 'eye-care', 'dark'];
            var current = document.documentElement.getAttribute('data-theme') || 'light';
            var idx = themes.indexOf(current);
            var next = themes[(idx + 1) % themes.length];
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            updateThemeBtns(next);
        });
    }
});

// ===== 主题切换 =====
(function () {
    // 初始化已保存的主题（由 <head> 中的防闪烁脚本设置 data-theme）
    var saved = document.documentElement.getAttribute('data-theme') || 'light';
    updateThemeBtns(saved);

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.theme-btn');
        if (!btn) return;
        var theme = btn.getAttribute('data-theme');
        if (!theme) return;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        updateThemeBtns(theme);
    });
})();

function updateThemeBtns(theme) {
    document.querySelectorAll('.theme-btn').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-theme') === theme);
    });
}

// ===== CSRF 防护 =====
(function () {
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMeta) return;
    var _token = csrfMeta.getAttribute('content');

    // 猴子补丁 window.fetch：自动注入 X-CSRF-Token
    var _originalFetch = window.fetch;
    window.fetch = function (url, options) {
        options = options || {};
        var method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].indexOf(method) >= 0) {
            options.headers = options.headers || {};
            if (!(options.body instanceof FormData)) {
                options.headers['Content-Type'] = options.headers['Content-Type'] || 'application/x-www-form-urlencoded';
            }
            options.headers['X-CSRF-Token'] = _token;
        }
        return _originalFetch.call(this, url, options);
    };

    // jQuery AJAX 拦截
    if (typeof $ !== 'undefined') {
        $(document).ajaxSend(function (event, jqXHR, settings) {
            var method = (settings.type || 'GET').toUpperCase();
            if (['POST', 'PUT', 'DELETE', 'PATCH'].indexOf(method) >= 0) {
                jqXHR.setRequestHeader('X-CSRF-Token', _token);
            }
        });
    }
})();

// ===== HTML 转义 =====
function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function safeSetText(el, text) {
    if (typeof el === 'string') el = document.getElementById(el);
    if (el) el.textContent = text;
}

// ===== Flash 消息自动消失 =====
$(function () {
    $('#flashArea .alert').each(function () {
        var $el = $(this);
        setTimeout(function () { $el.alert('close'); }, 1000);
    });
});

// ===== 消息未读数轮询 =====
(function () {
    var badgeTimer = null;
    var isAdmin = document.querySelector('meta[name="is-admin"]');
    var hasUser = document.querySelector('meta[name="has-user"]');
    var _isAdmin = isAdmin && isAdmin.getAttribute('content') === 'true';
    var _hasUser = hasUser && hasUser.getAttribute('content') === 'true';

    function updateAllBadges() {
        if (document.hidden) return;

        if (_isAdmin) {
            fetch('/admin/unread_count')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var badge = document.getElementById('msgBadge');
                    if (badge && data.count > 0) {
                        badge.textContent = data.count > 99 ? '99+' : data.count;
                        badge.style.display = 'flex';
                    } else if (badge) {
                        badge.style.display = 'none';
                    }
                })
                .catch(function () {});
        }

        if (_hasUser && !_isAdmin) {
            fetch('/api/user_unread_replies')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var badge = document.getElementById('userMsgBadge');
                    if (badge && data.count > 0) {
                        badge.textContent = data.count > 99 ? '99+' : data.count;
                        badge.style.display = 'flex';
                    } else if (badge) {
                        badge.style.display = 'none';
                    }
                })
                .catch(function () {});
        }
    }

    if (!document.hidden) updateAllBadges();
    badgeTimer = setInterval(updateAllBadges, 60000);
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) updateAllBadges();
    });
})();
