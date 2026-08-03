/**
 * converter.js -- 文件转换页面逻辑
 * 模式选择、文件上传/预览、转换请求、拖拽排序
 */

$(function () {
    var _prevInputType = null;
    window._pendingFiles = [];
    window._lastFormData = null;

    // 从 meta 标签读取服务端变量
    var _loginType = (document.querySelector('meta[name="login-type"]') || {}).getAttribute('content') || '';
    var _convertUrl = (document.getElementById('convertForm') || {}).getAttribute('data-convert-url') || '';
    var _isGuest = (document.querySelector('meta[name="is-guest"]') || {}).getAttribute('content') === 'true';
    var _guestRemaining = parseInt((document.querySelector('meta[name="guest-remaining"]') || {}).getAttribute('content')) || 0;

    // ===== 更新游客剩余次数提示 =====
    function updateGuestStat(remaining) {
        remaining = Math.max(parseInt(remaining) || 0, 0);
        _guestRemaining = remaining;
        $('#guestRemainNum').text(remaining);
        var $bar = $('#guestRemainBar');
        if ($bar.length) {
            $bar.toggleClass('warn', remaining <= 0);
        }
    }

    // ===== 更新左下角剩余次数 =====
    function updateSidebarStat(remaining) {
        if (_isGuest) {
            updateGuestStat(remaining);
            return;
        }
        var $num = $('#sidebarRemaining');
        var $stat = $('#blStat');
        if ($num.length) {
            $num.text(remaining);
            if (remaining <= 5) {
                $stat.addClass('warn');
            } else {
                $stat.removeClass('warn');
            }
        }
        if (_loginType === 'times') {
            if (remaining <= 0) {
                $('#convertBtn').prop('disabled', true);
            }
        }
    }

    // 初始化检查
    (function () {
        if (_isGuest) {
            updateGuestStat(_guestRemaining);
            return;
        }
        var $num = $('#sidebarRemaining');
        if ($num.length) {
            var initial = parseInt($num.text()) || 0;
            if (initial <= 5 && initial >= 0) $('#blStat').addClass('warn');
            if (initial <= 0) $('#convertBtn').prop('disabled', true);
        }
    })();

    // ===== 图片质量滑块 =====
    $('#imgQualitySlider').on('input', function () {
        $('#imgQualityVal').text(this.value);
    });

    // ===== TTS 语速滑块 =====
    $('#ttsRateSlider').on('input', function () {
        var val = parseInt(this.value);
        $('#ttsRateVal').text((val >= 0 ? '+' : '') + val + '%');
    });

    // ===== 公告关闭按钮 =====
    $(document).on('click', '.close-ann', function () {
        this.parentElement.remove();
    });

    // ===== 公告自动消失（管理员可配置时长，秒）=====
    $('.announce-bar[data-auto-hide]').each(function () {
        var $bar = $(this);
        var seconds = parseInt($bar.data('auto-hide'), 10) || 0;
        if (seconds > 0) {
            setTimeout(function () {
                $bar.fadeOut(300, function () { $(this).remove(); });
            }, seconds * 1000);
        }
    });

    // ===== 检查模式 =====
    function checkModeSelected() {
        if ($('input[name="mode"]:checked').length === 0) {
            showToast('请先选择转换模式');
            return false;
        }
        return true;
    }

    // ===== 选择文件按钮 =====
    $('#selectFileBtn').on('click', function () {
        if (!checkModeSelected()) return;
        var inputType = $('input[name="mode"]:checked').data('input-type');
        if (inputType === 'file') {
            $('#fileInput').click();
        } else {
            $('#filesInput').click();
        }
    });

    $('#dropZone').on('click', function (e) {
        if (e.target === this || $(e.target).closest('#selectFileBtn').length === 0) {
            if (!checkModeSelected()) return;
            $('#selectFileBtn').trigger('click');
        }
    });

    // ===== 模式切换 =====
    $(document).on('change', '.mode-radio', function () {
        var inputType = $(this).data('input-type');
        var mode = $(this).val();
        var hasOldFiles = window._pendingFiles.length > 0;

        var hints = {
            'file': '可一次选择多个文件，批量转换自动打包下载',
            'files': '按住 Ctrl 可选择多个 PDF 文件',
            'directory': '选择文件夹中的所有图片文件'
        };
        var modeHints = {
            '文件压缩': '选择要压缩的文件（支持 ZIP/TAR.GZ/7Z）',
            '文件解压': '上传压缩包（支持 ZIP/TAR.GZ/7Z）',
            '压缩包解密': '上传加密的压缩包（ZIP 或 7Z 格式）'
        };
        $('#fileHint').text(modeHints[mode] || hints[inputType] || '请选择合适的文件格式');

        var btnTexts = {
            '文件压缩': '开始压缩',
            '文件解压': '开始解压',
            '压缩包解密': '开始解密',
            'pdf加密': '开始加密',
            'pdf解密': '开始解密',
            'pdf合并': '开始合并',
            'pdf压缩': '开始压缩',
            'pdf分割': '开始提取',
            '图片压缩': '开始压缩',
            '文字转语音': '开始转换'
        };
        $('#convertBtn').html('<i class="fas fa-magic"></i> ' + (btnTexts[mode] || '开始转换'));

        // 密码相关
        if (mode === 'pdf加密' || mode === 'pdf解密') {
            $('#passwordArea').show();
            if (mode === 'pdf加密') {
                $('#passwordHint').text('密码长度不少于 4 位，加密后的文件需密码才能打开');
            } else {
                $('#passwordHint').text('输入加密时设置的密码，解密后文件将不再受保护');
            }
        } else if ($('#passwordArea').is(':visible') && mode !== '文件压缩' && mode !== '压缩包解密') {
            $('#passwordArea').hide();
            $('#passwordInput').val('');
        }

        // 压缩模式
        if (mode === '文件压缩') {
            $('#formatArea').show();
            $('#formatHint').text('ZIP 和 7Z 支持密码加密');
            $('#passwordArea').show();
            $('#passwordHint').text('可选：设置密码保护压缩包（ZIP/7Z 支持）');
            $('#pwdStrength').hide();
        } else if ($('#formatArea').is(':visible')) {
            $('#formatArea').hide();
        }

        if (mode === '压缩包解密') {
            $('#passwordArea').show();
            $('#passwordHint').text('输入该压缩包的密码，去除密码保护');
            $('#pwdStrength').hide();
        }

        // 图片格式互转
        if (mode === '图片格式互转') {
            $('#imageFormatArea').show();
            $('#imageFormatHint').text('将图片转换为指定格式');
        } else if ($('#imageFormatArea').is(':visible')) {
            $('#imageFormatArea').hide();
        }

        // OCR 输出格式
        if (mode === 'PDF OCR识别' || mode === '图片OCR识别') {
            $('#ocrFormatArea').show();
        } else if ($('#ocrFormatArea').is(':visible')) {
            $('#ocrFormatArea').hide();
        }

        // PDF 压缩
        if (mode === 'pdf压缩') {
            $('#pdfCompressArea').show();
        } else if ($('#pdfCompressArea').is(':visible')) {
            $('#pdfCompressArea').hide();
        }

        // 图片压缩
        if (mode === '图片压缩') {
            $('#imgCompressArea').show();
        } else if ($('#imgCompressArea').is(':visible')) {
            $('#imgCompressArea').hide();
        }

        // PDF 分割
        if (mode === 'pdf分割') {
            $('#pageRangeArea').show();
        } else if ($('#pageRangeArea').is(':visible')) {
            $('#pageRangeArea').hide();
        }

        // 文字转语音
        if (mode === '文字转语音') {
            $('#ttsParamsArea').show();
        } else if ($('#ttsParamsArea').is(':visible')) {
            $('#ttsParamsArea').hide();
        }

        // 模式变更文件需重新选
        var sameInput = (_prevInputType === inputType) ||
            (_prevInputType === 'files' && inputType === 'directory') ||
            (_prevInputType === 'directory' && inputType === 'files');
        if (hasOldFiles && !sameInput) {
            showToast('已更换模式，请重新选择文件');
            window._pendingFiles = [];
        }
        _prevInputType = inputType;
        updateFileList();
    });

    // ===== 文件选择 =====
    var FILE_LIMITS = { 'pdf合并': 50, '图片转pdf': 100, '图片转ppt': 100 };
    function onFilesSelected(inputEl) {
        if (!inputEl || !inputEl.files || inputEl.files.length === 0) return;
        var mode = $('input[name="mode"]:checked').val();
        var maxFiles = FILE_LIMITS[mode] || 10;
        for (var i = 0; i < inputEl.files.length; i++) {
            if (window._pendingFiles.length >= maxFiles) {
                showToast('最多上传 ' + maxFiles + ' 个文件，超出的已忽略');
                break;
            }
            window._pendingFiles.push(inputEl.files[i]);
        }
        var dt = new DataTransfer();
        inputEl.files = dt.files;
        updateFileList();
    }
    $('#fileInput').on('change', function () { onFilesSelected(this); });
    $('#filesInput').on('change', function () { onFilesSelected(this); });

    // ===== 密码切换 =====
    $('#passwordToggle').on('click', function () {
        var input = $('#passwordInput');
        var icon = $(this).find('i');
        if (input.attr('type') === 'password') {
            input.attr('type', 'text');
            icon.removeClass('fa-eye').addClass('fa-eye-slash');
        } else {
            input.attr('type', 'password');
            icon.removeClass('fa-eye-slash').addClass('fa-eye');
        }
    });

    // ===== 清空文件 =====
    $('#clearFilesBtn').on('click', function () {
        window._pendingFiles = [];
        updateFileList();
    });

    // ===== 密码强度 =====
    var pwdStrengthTimer = null;
    $('#passwordInput').on('input', function () {
        clearTimeout(pwdStrengthTimer);
        pwdStrengthTimer = setTimeout(updatePasswordStrength, 150);
    });
    function updatePasswordStrength() {
        var pwd = $('#passwordInput').val();
        var $area = $('#pwdStrength');
        var $bar = $('#pwdStrengthBar');
        var $text = $('#pwdStrengthText');
        if (!pwd) { $area.hide(); return; }
        $area.show();
        var score = 0;
        if (pwd.length >= 4) score += 1;
        if (pwd.length >= 6) score += 1;
        if (pwd.length >= 8) score += 1;
        if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score += 1;
        if (/\d/.test(pwd)) score += 1;
        if (/[^a-zA-Z0-9]/.test(pwd)) score += 1;
        var pct, color, label;
        if (score <= 2) { pct = 25; color = '#ef4444'; label = '弱'; }
        else if (score <= 3) { pct = 55; color = '#f59e0b'; label = '中'; }
        else if (score <= 4) { pct = 80; color = '#10b981'; label = '强'; }
        else { pct = 100; color = '#059669'; label = '很强'; }
        $bar.css({ width: pct + '%', background: color });
        $text.html('<span style="color:' + color + ';font-weight:600;">' + label + '</span> — 建议使用大小写字母+数字+符号组合');
    }

    // ===== 文件预览 =====
    window.previewFile = function (index) {
        var file = window._pendingFiles[index];
        if (!file) return;
        var url = URL.createObjectURL(file);
        var ext = file.name.split('.').pop().toLowerCase();
        var isImage = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].indexOf(ext) >= 0;
        var isPdf = ext === 'pdf';
        if (!isImage && !isPdf) { showToast('暂不支持预览此格式'); URL.revokeObjectURL(url); return; }

        var contentHtml = '';
        if (isImage) {
            contentHtml = '<div class="preview-body" id="previewBody">' +
                '<img id="previewImg" class="preview-zoom-img" src="' + url + '" alt="' + escapeHtml(file.name) + '">' +
                '<div class="preview-zoom-hint" id="zoomHint">滚轮缩放 · 拖拽平移</div></div>';
        } else {
            contentHtml = '<div class="preview-body" id="previewBody"><iframe src="' + url + '"></iframe></div>';
        }
        var toolbar = isImage
            ? '<div class="preview-toolbar">' +
                '<button onclick="previewZoomOut()" title="缩小"><i class="fas fa-search-minus"></i></button>' +
                '<span class="zoom-level" id="zoomLevel">100%</span>' +
                '<button onclick="previewZoomIn()" title="放大"><i class="fas fa-search-plus"></i></button>' +
                '<button onclick="previewZoomReset()" title="适应窗口"><i class="fas fa-expand"></i></button>' +
              '</div>'
            : '';
        var $modal = $(
            '<div class="preview-overlay" id="previewOverlay">' +
            '<div class="preview-container">' +
            '<div class="preview-header">' +
            '<span class="preview-title"><i class="fas fa-file"></i> ' + escapeHtml(file.name) + '</span>' +
            toolbar +
            '<button class="preview-close" onclick="closePreview()"><i class="fas fa-times"></i></button>' +
            '</div>' + contentHtml +
            '</div></div>'
        );
        $('body').append($modal);
        if (isImage) {
            window._previewZoom = 1;
            var $body = $('#previewBody');
            var wheelTimer = null;
            $body.on('wheel', function (e) {
                e.preventDefault();
                if (wheelTimer) return;
                wheelTimer = setTimeout(function () { wheelTimer = null; }, 30);
                var delta = e.originalEvent.deltaY > 0 ? -0.15 : 0.15;
                previewZoomUpdate(window._previewZoom + delta);
            });
            $('#zoomHint').addClass('show');
            setTimeout(function () { $('#zoomHint').removeClass('show'); }, 2000);
        }
        $modal.on('click', function (e) { if (e.target === this) closePreview(); });
        $(document).on('keydown.preview', function (e) {
            if (e.key === 'Escape') closePreview();
            if (isImage && (e.key === '+' || e.key === '=')) { e.preventDefault(); previewZoomIn(); }
            if (isImage && e.key === '-') { e.preventDefault(); previewZoomOut(); }
            if (isImage && e.key === '0') { e.preventDefault(); previewZoomReset(); }
        });
        setTimeout(function () { $modal.addClass('show'); }, 10);
        window._previewUrl = url;
    };
    window.previewZoomIn = function () { previewZoomUpdate((window._previewZoom || 1) + 0.2); };
    window.previewZoomOut = function () { previewZoomUpdate((window._previewZoom || 1) - 0.2); };
    window.previewZoomReset = function () { previewZoomUpdate(1); };
    function previewZoomUpdate(newZoom) {
        newZoom = Math.max(0.1, Math.min(5, newZoom));
        window._previewZoom = newZoom;
        var $img = $('#previewImg');
        if ($img.length) {
            $img.css('transform', 'scale(' + newZoom + ')');
            $('#zoomLevel').text(Math.round(newZoom * 100) + '%');
        }
    }
    window.closePreview = function () {
        $('.preview-overlay').removeClass('show');
        $(document).off('keydown.preview');
        setTimeout(function () { $('.preview-overlay').remove(); if (window._previewUrl) URL.revokeObjectURL(window._previewUrl); }, 200);
    };

    // ===== 更新文件列表 =====
    function updateFileList() {
        var $list = $('#fileList');
        var $items = $('#fileListItems');
        var $btn = $('#convertBtn');
        if (window._pendingFiles.length > 0) {
            $list.addClass('show');
            $('#clearFilesBtn').show();
            $items.empty();
            var iconMap = {
                'pdf': 'fa-file-pdf', 'doc': 'fa-file-word', 'docx': 'fa-file-word',
                'xls': 'fa-file-excel', 'xlsx': 'fa-file-excel', 'csv': 'fa-file-csv',
                'jpg': 'fa-file-image', 'jpeg': 'fa-file-image', 'png': 'fa-file-image',
                'ppt': 'fa-file-powerpoint', 'pptx': 'fa-file-powerpoint',
                'txt': 'fa-file-alt', 'md': 'fa-markdown',
                'html': 'fa-code', 'htm': 'fa-code'
            };
            var colorMap = {
                'pdf': '#dc2626', 'doc': '#2563eb', 'docx': '#2563eb',
                'xls': '#16a34a', 'xlsx': '#16a34a', 'csv': '#0891b2',
                'jpg': '#ea580c', 'jpeg': '#ea580c', 'png': '#ea580c',
                'ppt': '#dc2626', 'pptx': '#dc2626', 'txt': '#6b7280',
                'md': '#0891b2', 'html': '#2563eb', 'htm': '#2563eb'
            };
            var mode = $('input[name="mode"]:checked').val();
            var isMergeMode = (mode === 'pdf合并');
            for (var i = 0; i < window._pendingFiles.length; i++) {
                var ext = window._pendingFiles[i].name.split('.').pop().toLowerCase();
                var icon = iconMap[ext] || 'fa-file';
                var color = colorMap[ext] || '#94a3b8';
                var canPreview = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'pdf'].indexOf(ext) >= 0;
                $items.append(
                    '<div class="file-item" draggable="' + isMergeMode + '" data-index="' + i + '">' +
                    (isMergeMode ? '<span class="fi-drag"><i class="fas fa-grip-vertical"></i></span>' : '') +
                    '<i class="fas ' + icon + '" style="color:' + color + ';"></i>' +
                    '<span class="fi-name">' + window._pendingFiles[i].name + '</span>' +
                    '<span class="fi-size">' + (window._pendingFiles[i].size / 1024).toFixed(1) + ' KB</span>' +
                    (canPreview ? '<span class="fi-preview" onclick="previewFile(' + i + ')" title="预览"><i class="fas fa-eye"></i></span>' : '') +
                    '<span class="fi-remove" title="删除" onclick="removeFileFromList(' + i + ')"><i class="fas fa-times-circle"></i></span>' +
                    '</div>'
                );
            }
            if (isMergeMode) initDragSort();
            $('#fileCount').text(window._pendingFiles.length + ' 个文件');
            $btn.prop('disabled', false);
        } else {
            $list.removeClass('show');
            $('#clearFilesBtn').hide();
            $('#fileCount').text('0 个文件');
            $btn.prop('disabled', true);
        }
    }

    window.removeFileFromList = function (index) {
        window._pendingFiles.splice(index, 1);
        updateFileList();
    };

    // ===== 拖拽排序（PDF合并）=====
    function initDragSort() {
        var items = document.querySelectorAll('#fileListItems .file-item');
        var dragSrc = null;
        items.forEach(function (item) {
            item.addEventListener('dragstart', function (e) {
                dragSrc = this;
                this.style.opacity = '0.4';
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', '');
            });
            item.addEventListener('dragend', function () {
                this.style.opacity = '1';
                dragSrc = null;
            });
            item.addEventListener('dragover', function (e) {
                e.preventDefault();
                this.style.borderBottom = '2px solid #667eea';
            });
            item.addEventListener('dragleave', function () {
                this.style.borderBottom = '';
            });
            item.addEventListener('drop', function (e) {
                e.preventDefault();
                this.style.borderBottom = '';
                var target = this;
                if (!dragSrc || dragSrc === target) return;
                var srcIdx = parseInt(dragSrc.getAttribute('data-index'));
                var dstIdx = parseInt(target.getAttribute('data-index'));
                var file = window._pendingFiles.splice(srcIdx, 1)[0];
                var insertAt = (srcIdx < dstIdx) ? dstIdx - 1 : dstIdx;
                window._pendingFiles.splice(insertAt, 0, file);
                var parent = document.getElementById('fileListItems');
                if (srcIdx < dstIdx) {
                    parent.insertBefore(dragSrc, target.nextSibling);
                } else {
                    parent.insertBefore(dragSrc, target);
                }
                var allItems = parent.querySelectorAll('.file-item');
                for (var j = 0; j < allItems.length; j++) {
                    allItems[j].setAttribute('data-index', j);
                }
            });
        });
    }

    // ===== 核心：AJAX 提交任务 =====
    function doConvert(formData) {
        var $res = $('#resultArea');
        var $fill = $('#progressFill');
        var $msg = $('#resultMessage');
        var $dl = $('#downloadBtn');
        var $btn = $('#convertBtn');

        $res.addClass('show');
        $fill.css('width', '5%');
        $msg.hide().removeClass('success error');
        $dl.removeClass('show');
        $btn.prop('disabled', true);

        $('html, body').animate({ scrollTop: $res.offset().top - 100 }, 400);

        $.ajax({
            url: _convertUrl,
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            xhr: function () {
                var xhr = new XMLHttpRequest();
                xhr.upload.addEventListener('progress', function (e) {
                    if (e.lengthComputable) {
                        $fill.css('width', Math.round(e.loaded / e.total * 50) + '%');
                    }
                });
                return xhr;
            },
            success: function (response) {
                if (response.duplicate_warning) {
                    $btn.prop('disabled', false);
                    $res.removeClass('show');
                    showDuplicateModal(response.message);
                    return;
                }
                if (response.need_password) {
                    $btn.prop('disabled', false);
                    $res.removeClass('show');
                    $('#passwordModalMsg').text(response.message || '检测到该压缩文件加密，请输入密码');
                    $('#passwordModalInput').val('');
                    $('#passwordModal').fadeIn(150);
                    return;
                }
                if (response.need_login) {
                    $btn.prop('disabled', false);
                    $res.removeClass('show');
                    showLoginPrompt(response.message || '游客已用完体验次数，请登录解锁更多权益');
                    return;
                }
                handleConvertResponse(response, $fill, $msg, $dl);
            },
            error: function () {
                $fill.css('width', '100%').css('background', '#ef4444');
                $msg.addClass('error').html('<i class="fas fa-times-circle"></i> 网络错误，请重试').show();
            },
            complete: function () {
                $btn.prop('disabled', false);
            }
        });
    }

    // ===== 处理转换响应 =====
    function handleConvertResponse(response, $fill, $msg, $dl) {
        var pct = 50;
        var iv = setInterval(function () {
            pct += Math.random() * 12;
            if (pct >= 95) { pct = 95; clearInterval(iv); }
            $fill.css('width', pct + '%');
        }, 250);
        setTimeout(function () {
            clearInterval(iv);
            $fill.css('width', '100%');
            if (response.success) {
                $msg.addClass('success').html('<i class="fas fa-check-circle"></i> ' + response.message).show();
                if (response.download_url) {
                    $dl.attr('href', response.download_url).addClass('show');
                    if (response.display_name) {
                        $dl.html('<i class="fas fa-download"></i> ' + response.display_name);
                    }
                }
                if (response.extracted_files && response.extracted_files.length > 0) {
                    renderExtractedFiles(response.extracted_files);
                }
                if (response.remaining_times !== undefined && response.remaining_times !== null) {
                    updateSidebarStat(response.remaining_times);
                }
            } else {
                $msg.addClass('error').html('<i class="fas fa-exclamation-circle"></i> ' + response.message).show();
            }
        }, 600);
    }

    // ===== 渲染解压文件列表 =====
    function renderExtractedFiles(files) {
        var $extArea = $('#extractedFilesArea');
        var $extList = $('#extractedFilesList');
        $extList.empty();
        files.forEach(function (f) {
            var icon = 'fa-file';
            var name = f.name || f.path;
            var ext = name.split('.').pop().toLowerCase();
            if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].indexOf(ext) >= 0) icon = 'fa-file-image';
            else if (ext === 'pdf') icon = 'fa-file-pdf';
            else if (['doc', 'docx'].indexOf(ext) >= 0) icon = 'fa-file-word';
            else if (['xls', 'xlsx'].indexOf(ext) >= 0) icon = 'fa-file-excel';
            else if (['zip', 'rar', '7z', 'tar', 'gz'].indexOf(ext) >= 0) icon = 'fa-file-archive';
            $extList.append(
                '<div style="display:flex;align-items:center;gap:6px;padding:2px 0;">' +
                '<i class="fas ' + icon + '" style="color:var(--text-muted);width:14px;text-align:center;"></i>' +
                '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + escapeHtml(f.path) + '</span>' +
                (f.download_url ? '<a href="' + f.download_url + '" style="color:#667eea;font-size:11px;text-decoration:none;white-space:nowrap;"><i class="fas fa-download"></i> 下载</a>' : '') +
                '</div>'
            );
        });
        $extArea.show();
    }

    // ===== 开始转换 =====
    $('#convertBtn').on('click', function () {
        $('#extractedFilesArea').hide();
        var mode = $('input[name="mode"]:checked').val();
        if (!mode) { showToast('请先选择转换模式'); return; }
        // 游客已用完体验次数：点击直接引导登录
        if (_isGuest && _guestRemaining <= 0) {
            showLoginPrompt('游客体验次数已用完，登录即可解锁更多权益');
            return;
        }

        var inputType = $('input[name="mode"]:checked').data('input-type');
        var formData = new FormData();
        formData.append('mode', mode);

        if (mode === 'pdf加密' || mode === 'pdf解密') {
            var pwd = $('#passwordInput').val().trim();
            if (!pwd) { showToast('请输入密码'); return; }
            if (mode === 'pdf加密' && pwd.length < 4) { showToast('加密密码长度不能少于 4 位'); return; }
            formData.append('password', pwd);
        }
        if (mode === '文件压缩') {
            formData.append('archive_format', $('#formatSelect').val());
            var pwdP = $('#passwordInput').val().trim();
            if (pwdP) {
                if (pwdP.length < 4) { showToast('加密密码长度不能少于 4 位'); return; }
                if ($('#formatSelect').val() === 'tar.gz') { showToast('TAR.GZ 不支持加密，请选择 ZIP 或 7Z'); return; }
                formData.append('password', pwdP);
            }
        }
        if (mode === '压缩包解密') {
            var pwdD = $('#passwordInput').val().trim();
            if (!pwdD) { showToast('请输入压缩包密码'); return; }
            formData.append('password', pwdD);
        }
        if (mode === '图片格式互转') {
            formData.append('target_format', $('#imageFormatSelect').val());
        }
        if (mode === 'PDF OCR识别' || mode === '图片OCR识别') {
            formData.append('output_format', $('#ocrFormatSelect').val());
        }
        if (mode === 'pdf压缩') {
            formData.append('quality', $('#pdfCompressSelect').val());
        }
        if (mode === '图片压缩') {
            formData.append('img_quality', $('#imgQualitySlider').val());
        }
        if (mode === 'pdf分割') {
            var pageRange = $('#pageRangeInput').val().trim();
            if (!pageRange) { showToast('请输入页码范围，如 1-3,5,7-10'); return; }
            formData.append('page_range', pageRange);
        }
        if (mode === '文字转语音') {
            formData.append('voice', $('#ttsVoiceSelect').val());
            formData.append('rate', ($('#ttsRateSlider').val() >= 0 ? '+' : '') + $('#ttsRateSlider').val() + '%');
        }

        var fieldName = (inputType === 'file') ? 'file' : 'files';
        for (var i = 0; i < window._pendingFiles.length; i++) {
            formData.append(fieldName, window._pendingFiles[i]);
        }

        window._lastFormData = formData;
        doConvert(formData);
    });

    // ===== 游客登录引导弹窗 =====
    function showLoginPrompt(msg) {
        if ($('#loginPromptModal').length) {
            $('#loginPromptModal').remove();
        }
        var $modal = $(
            '<div class="modal-overlay" id="loginPromptModal">' +
            '<div class="modal-box">' +
            '<div class="modal-header">' +
            '<i class="fas fa-crown" style="color:#f59e0b;font-size:20px;"></i>' +
            '<span>登录解锁更多权益</span>' +
            '</div>' +
            '<div class="modal-body">' +
            '<p style="margin-bottom:10px;"><i class="fas fa-exclamation-circle" style="color:#f59e0b;margin-right:6px;"></i>' + escapeHtml(msg || '游客已用完体验次数') + '</p>' +
            '<ul style="padding-left:20px;font-size:13px;line-height:2;color:var(--text-secondary);">' +
            '<li>无限次使用全部 28 种转换功能</li>' +
            '<li>查看转换记录与数据分析仪表盘</li>' +
            '<li>在线联系作者，享受更多服务</li>' +
            '</ul>' +
            '</div>' +
            '<div class="modal-footer">' +
            '<div class="modal-btns">' +
            '<button class="modal-btn cancel" id="loginPromptCancel">继续浏览</button>' +
            '<a class="modal-btn confirm" style="text-decoration:none;color:#fff;" href="/login">去登录</a>' +
            '</div>' +
            '</div>' +
            '</div></div>'
        );
        $('body').append($modal);
        $modal.fadeIn(150);
        $('#loginPromptCancel').on('click', function () { $modal.fadeOut(150, function () { $modal.remove(); }); });
        $(document).on('click', '#loginPromptModal', function (e) { if (e.target === this) { $modal.fadeOut(150, function () { $modal.remove(); }); } });
    }

    // ===== 重复文件确认弹窗 =====
    window.showDuplicateModal = function (msg) {
        $('#duplicateModalMsg').text(msg || '检测到与上次转换文件相同，为避免浪费次数，请确认是否继续转换');
        $('#duplicateModal').fadeIn(150);
    };
    $('#duplicateConfirm').on('click', function () {
        var dontAsk = $('#dontAskCheck').is(':checked');
        if (dontAsk) window._lastFormData.append('dont_ask_again', '1');
        window._lastFormData.append('confirmed', '1');
        $('#duplicateModal').fadeOut(100);
        doConvert(window._lastFormData);
    });
    $('#duplicateCancel').on('click', function () { $('#duplicateModal').fadeOut(100); });
    $(document).on('click', '#duplicateModal', function (e) { if (e.target === this) $('#duplicateModal').fadeOut(100); });

    // ===== 密码弹窗 =====
    $('#passwordModalConfirm').on('click', function () {
        var pwd = $('#passwordModalInput').val().trim();
        if (!pwd) { showToast('请输入密码'); return; }
        $('#passwordModal').fadeOut(100);
        window._lastFormData.append('password', pwd);
        window._lastFormData.append('confirmed', '1');
        $('#extractedFilesArea').hide();
        doConvert(window._lastFormData);
    });
    $('#passwordModalCancel').on('click', function () { $('#passwordModal').fadeOut(100); });
    $(document).on('click', '#passwordModal', function (e) { if (e.target === this) $('#passwordModal').fadeOut(100); });

    // ===== Toast =====
    function showToast(msg) {
        var $t = $('<div class="custom-toast">' +
            '<i class="fas fa-exclamation-triangle"></i> ' + msg + '</div>');
        $('body').append($t);
        setTimeout(function () { $t.fadeOut(300, function () { $t.remove(); }); }, 3000);
    }

    // ===== 拖拽上传 =====
    var dropZone = document.getElementById('dropZone');
    ['dragover', 'dragenter'].forEach(function (evt) {
        dropZone.addEventListener(evt, function (e) { e.preventDefault(); dropZone.classList.add('drag-over'); });
    });
    ['dragleave', 'drop'].forEach(function (evt) {
        dropZone.addEventListener(evt, function (e) { e.preventDefault(); dropZone.classList.remove('drag-over'); });
    });
    dropZone.addEventListener('drop', function (e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (!checkModeSelected()) return;
        var files = e.dataTransfer.files;
        if (!files || files.length === 0) return;
        for (var i = 0; i < files.length; i++) {
            window._pendingFiles.push(files[i]);
        }
        updateFileList();
    });
});
