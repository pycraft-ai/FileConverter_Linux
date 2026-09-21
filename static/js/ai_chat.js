/**
 * ai_chat.js -- FileConverter AI 智能客服悬浮聊天窗
 *
 * 用法：POST /api/ai_chat，body 采用 application/x-www-form-urlencoded 的 question 字段。
 *
 * 可独立使用（如欢迎页这类不继承 base.html 的页面）：
 *   - 页面需提供 <meta name="csrf-token"> 与 <meta name="ai-enabled">
 *   - 本脚本自带 HTML 转义与 CSRF 注入，不依赖 base.js 的全局函数
 * 若页面已加载 base.js（它会给 fetch 补 X-CSRF-Token header），也不会冲突。
 *
 * AI_ENABLED 未开启时，后端会返回 success=false；本脚本同样给出友好提示，
 * 不破坏站点其它功能。
 */
(function () {
    'use strict';

    // ===== 仅当后端启用时才真正展示客服按钮 =====
    // 由后端在渲染页面时注入 meta（见 base.html）。
    var aiMeta = document.querySelector('meta[name="ai-enabled"]');
    var aiEnabled = aiMeta && aiMeta.getAttribute('content') === 'true';
    if (!aiEnabled) {
        // 未开启：不渲染任何入口，静默跳过
        return;
    }

    var CONFIG = {
        apiUrl: '/api/ai_chat',
        minQuestionLen: 1,
        maxQuestionLen: 1000,
        inputRows: 2
    };

    // ===== 独立运行所需的两个小工具（不依赖 base.js） =====
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');

    function esc(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // ===== 客服回答中的「直达页面」占位符 → 真实链接的映射 =====
    // 模型在回答末尾会输出一行：【直达:页面名】；这里把它替换成可点击跳转的按钮。
    // key 与后端 SYSTEM_PROMPT 中的「页面名」保持一致。
    var DIRECT_PAGES = {
        '联系作者': { url: '/contact', label: '前往联系作者' },
        '文件转换': { url: '/',       label: '去文件转换' },
        '注册':     { url: '/register', label: '立即注册' },
        '登录':     { url: '/login',    label: '去登录' },
        '隐私政策': { url: '/privacy',  label: '查看隐私政策' },
        '仪表盘':   { url: '/dashboard', label: '打开仪表盘' },
        '转换记录': { url: '/my_logs',  label: '查看转换记录' }
    };

    // 渲染一条机器人消息：转义正文安全显示，并把 【直达:xx】 渲染成可点击链接
    function renderBotMessage(text) {
        // 1) 整体 HTML 转义，杜绝任何 XSS（占位符为中文方括号，转义后仍可被匹配）
        var safeText = esc(text || '');
        // 2) 把每个 【直达:页面名】 占位符替换成可点击链接（从正文中摘出，堆到末尾作为按钮）
        var jumpHtml = '';
        safeText = safeText.replace(/【直达:([^】]+)】/g, function (m, name) {
            var page = DIRECT_PAGES[name.trim()];
            if (page) {
                jumpHtml += '<a class="fc-link" href="' + page.url + '">' +
                    '<i class="fas fa-arrow-right"></i> ' + esc(page.label) + '</a>';
            }
            return '';
        });
        // 3) 处理换行（safeText 已被转义，这里直接把换行转成 <br>，不做二次转义）
        var bodyHtml = safeText.replace(/\n/g, '<br>');
        return bodyHtml + jumpHtml;
    }

    // 简洁样式（沿用站点主题 CSS 变量，适配三档主题）
    var style = document.createElement('style');
    style.textContent = [
        '#fc-wrap{position:fixed;right:20px;bottom:20px;z-index:10000;font-family:inherit;}' +
        '#fc-btn{width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;' +
        'background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;font-size:24px;' +
        'box-shadow:0 6px 18px rgba(102,126,234,.4);display:flex;align-items:center;' +
        'justify-content:center;transition:transform .2s;}' +
        '#fc-btn:hover{transform:scale(1.06);}' +
        '#fc-btn .fa-times{display:none;}' +
        '#fc-wrap.open #fc-btn .fa-comment{display:none;}' +
        '#fc-wrap.open #fc-btn .fa-times{display:block;}' +
        // 面板：使用不透明实色，避免站点半透明玻璃变量导致"透明"。
        // 实色通过 fc-* 自定义变量按主题覆盖（见下方 :root/[data-theme] 规则）。
        '#fc-panel{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 40px);' +
        'height:480px;max-height:calc(100vh - 120px);display:none;flex-direction:column;' +
        'background:var(--fc-panel-bg,#fff);border:1px solid var(--fc-border,#e5e7eb);' +
        'border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.18);overflow:hidden;}' +
        '#fc-wrap.open #fc-panel{display:flex;}' +
        '#fc-head{padding:12px 16px;background:linear-gradient(135deg,#667eea,#764ba2);' +
        'color:#fff;display:flex;align-items:center;gap:10px;}' +
        '#fc-head .fa-robot{font-size:18px;}' +
        '#fc-head-title{flex:1;font-weight:600;font-size:14px;}' +
        '#fc-reset{cursor:pointer;opacity:.85;font-size:13px;}' +
        '#fc-reset:hover{opacity:1;}' +
        '#fc-body{flex:1;overflow-y:auto;padding:14px;background:var(--fc-body-bg,#f7f8fa);' +
        'display:flex;flex-direction:column;gap:10px;}' +
        '#fc-body::-webkit-scrollbar{width:6px;}' +
        '#fc-body::-webkit-scrollbar-thumb{background:var(--fc-scroll,#c9cdd6);border-radius:3px;}' +
        '.fc-msg{max-width:85%;padding:9px 12px;border-radius:12px;font-size:13px;line-height:1.55;' +
        'white-space:pre-wrap;word-break:break-word;}' +
        '.fc-msg.bot{background:var(--fc-bot-bg,#fff);color:var(--fc-text,#111);' +
        'border:1px solid var(--fc-border,#eee);align-self:flex-start;' +
        'border-bottom-left-radius:4px;}' +
        '.fc-msg.user{background:#667eea;color:#fff;align-self:flex-end;' +
        'border-bottom-right-radius:4px;}' +
        '.fc-msg.err{background:rgba(239,68,68,.1);color:#ef4444;border:1px solid rgba(239,68,68,.25);' +
        'align-self:flex-start;}' +
        '#fc-quick{padding:8px 14px;display:flex;gap:6px;flex-wrap:wrap;' +
        'background:var(--fc-panel-bg,#fff);border-top:1px solid var(--fc-border,#eee);}' +
        '.fc-quick-btn{border:1px solid var(--fc-btn-border,#e0e3ea);background:var(--fc-panel-bg,#fff);' +
        'color:#667eea;font-size:12px;padding:4px 10px;border-radius:999px;cursor:pointer;' +
        'transition:all .15s;}' +
        '.fc-quick-btn:hover{background:rgba(102,126,234,.1);}' +
        '#fc-input{padding:10px 12px;background:var(--fc-panel-bg,#fff);border-top:1px solid var(--fc-border,#eee);' +
        'display:flex;align-items:flex-end;gap:8px;}' +
        '#fc-text{flex:1;border:1px solid var(--fc-btn-border,#ddd);border-radius:10px;padding:8px 12px;' +
        'font-size:13px;background:var(--fc-input-bg,#fff);color:var(--fc-text,#111);' +
        'resize:none;outline:none;font-family:inherit;}' +
        '#fc-text:focus{border-color:#667eea;}' +
        '#fc-send{border:none;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;' +
        'width:34px;height:34px;border-radius:10px;cursor:pointer;font-size:14px;flex-shrink:0;' +
        'display:flex;align-items:center;justify-content:center;}' +
        '#fc-send:disabled{opacity:.6;cursor:not-allowed;}' +
        '.fc-typing{color:#888;font-size:13px;padding:2px 2px 0;}' +
        '.fc-link{display:inline-block;margin-top:10px;padding:7px 14px;border-radius:8px;' +
        'background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;text-decoration:none;' +
        'font-size:13px;font-weight:600;transition:opacity .15s;}' +
        '.fc-link:hover{opacity:.88;color:#fff;}' +
        '.fc-link i{margin-right:5px;}' +
        '.fc-msg .fc-link{display:block;width:fit-content;}' +
        /* 引导气泡：位于客服按钮旁 */
        '#fc-tip{position:fixed;right:86px;bottom:32px;z-index:9999;background:var(--fc-tip-bg,#fff);' +
        'color:var(--fc-text,#3a3a4a);border:1px solid var(--fc-border,#e3e6ee);' +
        'box-shadow:0 6px 18px rgba(0,0,0,.12);' +
        'padding:8px 14px;border-radius:18px;font-size:13px;display:flex;align-items:center;' +
        'gap:6px;cursor:pointer;opacity:0;transform:translateY(6px);' +
        'transition:opacity .3s,transform .3s;animation:fc-tip-bounce 1.2s ease-in-out 1.2s 3;}' +
        '#fc-tip.show{opacity:1;transform:translateY(0);}' +
        '#fc-tip .fc-tip-tail{position:absolute;right:-6px;top:50%;width:0;height:0;' +
        'border-top:6px solid transparent;border-bottom:6px solid transparent;' +
        'border-left:6px solid var(--fc-tip-bg,#fff);transform:translateY(-50%);}' +
        '#fc-tip .fc-tip-close{margin-left:4px;color:#a0a4b0;font-size:11px;line-height:1;}' +
        '#fc-tip .fc-tip-close:hover{color:#ef4444;}' +
        '@keyframes fc-tip-bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}' +
        /* ===== 面板不透明实色：按站点三档主题分别覆盖 ===== */
        ':root,[data-theme="light"]{' +
        '--fc-panel-bg:#fff;--fc-body-bg:#f7f8fa;--fc-bot-bg:#fff;--fc-input-bg:#fff;' +
        '--fc-border:#e5e7eb;--fc-btn-border:#e0e3ea;--fc-text:#333;--fc-tip-bg:#fff;' +
        '--fc-scroll:#c9cdd6;}' +
        '[data-theme="eye-care"]{' +
        '--fc-panel-bg:#fdf6e3;--fc-body-bg:#f5e6c8;--fc-bot-bg:#fffdf5;--fc-input-bg:#fffdf5;' +
        '--fc-border:#e0d5b8;--fc-btn-border:#d8cba8;--fc-text:#5b4636;--fc-tip-bg:#fdf6e3;' +
        '--fc-scroll:#d8cba8;}' +
        '[data-theme="dark"]{' +
        '--fc-panel-bg:#1a1a2e;--fc-body-bg:#15152b;--fc-bot-bg:#242447;--fc-input-bg:#242447;' +
        '--fc-border:#3a3a5c;--fc-btn-border:#3a3a5c;--fc-text:#e0e0e0;--fc-tip-bg:#242447;' +
        '--fc-scroll:#4a4a6a;}'
    ].join('');
    document.head.appendChild(style);

    function build() {
        var wrap = document.createElement('div');
        wrap.id = 'fc-wrap';
        wrap.innerHTML =
            '<div id="fc-tip" title="有疑问？">' +
            '  <span>有疑问？问问AI客服吧😊</span><i class="fas fa-times fc-tip-close"></i>' +
            '  <span class="fc-tip-tail"></span>' +
            '</div>' +
            '<button id="fc-btn" title="智能客服" aria-label="打开智能客服">' +
            '<i class="fas fa-comment"></i><i class="fas fa-times"></i></button>' +
            '<div id="fc-panel">' +
            '  <div id="fc-head">' +
            '    <i class="fas fa-robot"></i>' +
            '    <span id="fc-head-title">智能客服 · 小转</span>' +
            '    <span id="fc-reset" title="清空对话"><i class="fas fa-eraser"></i></span>' +
            '  </div>' +
            '  <div id="fc-body">' +
            '    <div class="fc-msg bot">您好，我是智能客服「小转」😊 您可以问我：<br>· 该用哪个功能转换文件<br>· 转换报错怎么解决<br>· 次数 / 文件大小等规则</div>' +
            '  </div>' +
            '  <div id="fc-quick"></div>' +
            '  <div id="fc-input">' +
            '    <textarea id="fc-text" rows="' + CONFIG.inputRows + '" placeholder="请输入您的问题…（回车发送）"></textarea>' +
            '    <button id="fc-send" title="发送"><i class="fas fa-paper-plane"></i></button>' +
            '  </div>' +
            '</div>';
        document.body.appendChild(wrap);

        var quickList = [
            'PDF 转可编辑 Word 用哪个功能？',
            '图片上传提示尺寸过大怎么办？',
            '转换失败一般是什么原因？',
            '文件能保留多久？',
            '游客和登录用户有什么区别？'
        ];
        var quickBox = document.getElementById('fc-quick');
        quickList.forEach(function (t) {
            var b = document.createElement('button');
            b.className = 'fc-quick-btn';
            b.textContent = t;
            b.addEventListener('click', function () {
                send(t);
                hideQuick();
            });
            quickBox.appendChild(b);
        });

        // 打开/关闭
        var btn = document.getElementById('fc-btn');
        function hideTip() {
            var tip = document.getElementById('fc-tip');
            if (tip) tip.classList.remove('show');
        }
        btn.addEventListener('click', function () {
            wrap.classList.toggle('open');
            if (wrap.classList.contains('open')) {
                document.getElementById('fc-text').focus();
                updateQuick();
                hideTip();
            }
        });

        // 引导气泡：点击整条气泡 = 打开客服并隐藏气泡
        var tip = document.getElementById('fc-tip');
        // 点右上角 × 仅关闭气泡、不打开面板
        var tipClose = tip.querySelector('.fc-tip-close');
        if (tipClose) {
            tipClose.addEventListener('click', function (e) {
                e.stopPropagation();
                hideTip();
            });
        }
        tip.addEventListener('click', function () {
            if (!wrap.classList.contains('open')) {
                wrap.classList.add('open');
                document.getElementById('fc-text').focus();
                updateQuick();
            }
            hideTip();
        });

        // 延迟一下再显示气泡，形成"引导"感；并让气泡出现在按钮旁
        setTimeout(function () {
            var t = document.getElementById('fc-tip');
            if (t) t.classList.add('show');
        }, 1000);

        // 清空对话
        document.getElementById('fc-reset').addEventListener('click', function () {
            document.getElementById('fc-body').innerHTML =
                '<div class="fc-msg bot">已清空对话，请问有什么可以帮您？</div>';
            showQuick();
        });

        // 回车发送（Shift+回车换行）
        var text = document.getElementById('fc-text');
        text.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!document.getElementById('fc-send').disabled) doSend();
            }
        });
        document.getElementById('fc-send').addEventListener('click', doSend);
    }

    // —— 快捷问题区逻辑 ——
    function updateQuick() {
        var body = document.getElementById('fc-body');
        var hide = body.querySelectorAll('.fc-msg').length > 1;
        if (hide) { hideQuick(); } else { showQuick(); }
    }
    function hideQuick() { document.getElementById('fc-quick').style.display = 'none'; }
    function showQuick() { document.getElementById('fc-quick').style.display = 'flex'; }

    function addMsg(text, cls) {
        var body = document.getElementById('fc-body');
        var div = document.createElement('div');
        div.className = 'fc-msg ' + (cls || 'bot');
        div.textContent = text;
        body.appendChild(div);
        body.scrollTop = body.scrollHeight;
        return div;
    }

    // 机器人回答消息：支持解析 【直达:xx】 渲染可点击链接
    function addBotMsg(text) {
        var body = document.getElementById('fc-body');
        var div = document.createElement('div');
        div.className = 'fc-msg bot';
        div.innerHTML = renderBotMessage(text);
        body.appendChild(div);
        body.scrollTop = body.scrollHeight;
        return div;
    }

    function setBusy(busy) {
        var send = document.getElementById('fc-send');
        var text = document.getElementById('fc-text');
        send.disabled = busy;
        text.disabled = busy;
        if (busy) text.setAttribute('placeholder', '客服思考中…'); else text.setAttribute('placeholder', '请输入您的问题…（回车发送）');
    }

    function send(q) {
        var text = document.getElementById('fc-text');
        text.value = q;
        doSend();
    }

    function doSend() {
        var text = document.getElementById('fc-text');
        var q = (text.value || '').trim();
        if (!q) return;
        if (q.length > CONFIG.maxQuestionLen) {
            addMsg('问题太长了，请精简到 ' + CONFIG.maxQuestionLen + ' 字以内。', 'err');
            return;
        }
        // 显示用户消息 + 清空输入
        addMsg(q, 'user');
        text.value = '';
        setBusy(true);
        showQuick && hideQuick();

        // 提示"正在输入"
        var typing = addMsg('…', 'bot');
        typing.id = 'fc-typing';

        var params = new URLSearchParams();
        params.append('question', q);
        // 显式带上 CSRF token：独立页面（未加载 base.js 的 fetch 补丁）也能通过校验
        if (csrfMeta) {
            params.append('_csrf_token', csrfMeta.getAttribute('content'));
        }

        fetch(CONFIG.apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: params.toString()
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var tip = document.getElementById('fc-typing');
            if (tip) tip.remove();
            if (data.success) {
                addBotMsg(data.message || '（空回复）');
            } else {
                addMsg(data.message || '客服暂时开小差了，请稍后再试。', 'err');
            }
        })
        .catch(function () {
            var tip = document.getElementById('fc-typing');
            if (tip) tip.remove();
            addMsg('网络异常，请稍后再试。', 'err');
        })
        .finally(function () {
            setBusy(false);
        });
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', build);
    } else {
        build();
    }
})();
