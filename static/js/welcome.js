/**
 * 欢迎页交互：粒子连线背景
 * 性能要点：
 *   1. 速度按「像素/秒」计算，不依赖帧率，保证低帧率下也能看到运动
 *   2. 连线按透明度分 4 档批量绘制，每帧只有 4 次 stroke（而不是上千次）
 *   3. 所有粒子合并在一个 path 里一次 fill
 *   4. 绘制上限 60fps（高刷屏不做无谓重绘），标签页切后台时暂停
 */
(function () {
    'use strict';

    var canvas = document.getElementById('wvParticles');
    if (!canvas || !canvas.getContext) { return; }

    var ctx = canvas.getContext('2d');

    var reduceMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var TAU = Math.PI * 2;
    var MIN_DELTA = 0.015;      // 约 66fps 的绘制节流阈值
    var BASE_SPEED = 26;        // 粒子基础速度 px/s（视觉上明显可见）
    var LINK_LEVELS = 4;
    var LINK_ALPHA = ['0.05', '0.10', '0.16', '0.22'];
    var LINK_ALPHA_DARK = ['0.035', '0.07', '0.11', '0.15'];

    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    var particles = [];
    var width = 0;
    var height = 0;
    var linkDist = 120;
    var linkDist2 = linkDist * linkDist;
    var running = false;
    var rafId = null;
    var lastTime = 0;
    var acc = 0;

    // 每条连线的扁平坐标 [x1,y1,x2,y2]，按透明度分档，复用数组避免频繁分配
    var buckets = [[], [], [], []];

    // 鼠标位置（用于连线与轻微吸引）
    var pointer = { x: -9999, y: -9999, active: false };

    function particleCount() {
        var n = Math.round((width * height) / 26000);
        n = Math.max(22, Math.min(n, 72));
        return reduceMotion ? Math.round(n * 0.6) : n;
    }

    function initParticles() {
        var count = particleCount();
        particles = [];
        for (var i = 0; i < count; i++) {
            var angle = Math.random() * TAU;
            var speed = BASE_SPEED * (0.45 + Math.random() * 0.9);
            particles.push({
                x: Math.random() * width,
                y: Math.random() * height,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                r: Math.random() * 1.6 + 1
            });
        }
    }

    function resize() {
        width = canvas.clientWidth;
        height = canvas.clientHeight;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        linkDist = Math.max(95, Math.min(Math.min(width, height) * 0.17, 155));
        linkDist2 = linkDist * linkDist;

        initParticles();
    }

    function drawFrame(dt) {
        var n = particles.length;
        var i, j, p, q, dx, dy, d2, d, t, k;
        var arr, m;

        ctx.clearRect(0, 0, width, height);

        /* ---------- 1. 运动 ---------- */
        for (i = 0; i < n; i++) {
            p = particles[i];
            p.x += p.vx * dt;
            p.y += p.vy * dt;

            // 鼠标附近轻微吸引
            if (pointer.active) {
                dx = pointer.x - p.x;
                dy = pointer.y - p.y;
                d2 = dx * dx + dy * dy;
                if (d2 < 22500 && d2 > 4) {       // 半径 150
                    d = Math.sqrt(d2);
                    p.x += (dx / d) * 26 * dt;
                    p.y += (dy / d) * 26 * dt;
                }
            }

            // 边界反弹（留出半径余量，避免贴边抖动）
            if (p.x < p.r) { p.x = p.r; p.vx = Math.abs(p.vx); }
            else if (p.x > width - p.r) { p.x = width - p.r; p.vx = -Math.abs(p.vx); }
            if (p.y < p.r) { p.y = p.r; p.vy = Math.abs(p.vy); }
            else if (p.y > height - p.r) { p.y = height - p.r; p.vy = -Math.abs(p.vy); }
        }

        /* ---------- 2. 连线（分档批量） ---------- */
        for (k = 0; k < LINK_LEVELS; k++) { buckets[k].length = 0; }

        for (i = 0; i < n; i++) {
            p = particles[i];
            for (j = i + 1; j < n; j++) {
                q = particles[j];
                dx = p.x - q.x;
                dy = p.y - q.y;
                d2 = dx * dx + dy * dy;
                if (d2 < linkDist2) {
                    d = Math.sqrt(d2);
                    t = 1 - d / linkDist;                       // 0 ~ 1
                    k = (t * LINK_LEVELS) | 0;
                    if (k > LINK_LEVELS - 1) { k = LINK_LEVELS - 1; }
                    arr = buckets[k];
                    arr.push(p.x, p.y, q.x, q.y);
                }
            }
        }

        var alpha = reduceMotion ? LINK_ALPHA_DARK : LINK_ALPHA;
        ctx.lineWidth = 1;
        for (k = 0; k < LINK_LEVELS; k++) {
            arr = buckets[k];
            if (!arr.length) { continue; }
            ctx.beginPath();
            for (m = 0; m < arr.length; m += 4) {
                ctx.moveTo(arr[m], arr[m + 1]);
                ctx.lineTo(arr[m + 2], arr[m + 3]);
            }
            ctx.strokeStyle = 'rgba(140, 170, 255, ' + alpha[k] + ')';
            ctx.stroke();
        }

        /* ---------- 3. 圆点（合并为一个 path） ---------- */
        ctx.beginPath();
        for (i = 0; i < n; i++) {
            p = particles[i];
            ctx.moveTo(p.x + p.r, p.y);
            ctx.arc(p.x, p.y, p.r, 0, TAU);
        }
        ctx.fillStyle = 'rgba(185, 208, 255, .8)';
        ctx.fill();
    }

    function loop(now) {
        if (!running) { return; }
        rafId = window.requestAnimationFrame(loop);

        if (!lastTime) { lastTime = now; return; }

        var delta = (now - lastTime) / 1000;
        lastTime = now;
        if (delta > 0.25) { delta = 0.25; }     // 后台切回时的跳变保护

        acc += delta;
        if (acc < MIN_DELTA) { return; }        // 绘制上限 60fps

        var dt = acc;
        acc = 0;
        drawFrame(dt);
    }

    function start() {
        if (running) { return; }
        running = true;
        lastTime = 0;
        acc = 0;
        rafId = window.requestAnimationFrame(loop);
    }

    function stop() {
        running = false;
        if (rafId !== null) {
            window.cancelAnimationFrame(rafId);
            rafId = null;
        }
    }

    var resizeTimer = null;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(resize, 180);
    });

    window.addEventListener('mousemove', function (e) {
        pointer.x = e.clientX;
        pointer.y = e.clientY;
        pointer.active = true;
    }, { passive: true });

    window.addEventListener('mouseout', function (e) {
        if (!e.relatedTarget) {
            pointer.x = -9999;
            pointer.y = -9999;
            pointer.active = false;
        }
    });

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) { stop(); } else { start(); }
    });

    resize();
    start();
})();
