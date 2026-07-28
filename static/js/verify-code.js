/**
 * verify-code.js -- 验证码发送（注册 + 忘记密码共用）
 * 依赖：元素 #sendCodeBtn, #email, #codeHint, 以及 data-verify-url 属性
 */
$(function () {
    var $btn = $('#sendCodeBtn');
    var $hint = $('#codeHint');
    var verifyUrl = $btn.data('verify-url') || '';
    var timer = null;
    var countdown = 0;

    $btn.on('click', function () {
        var email = $('#email').val().trim();
        if (!email || email.indexOf('@') < 0) {
            alert('请先输入有效的邮箱地址');
            $('#email').focus();
            return;
        }
        if (timer) return;

        $btn.prop('disabled', true).text('发送中...');
        $hint.text('');

        $.post(verifyUrl, { email: email }, function (res) {
            if (res.success) {
                $hint.text(res.message);
                countdown = 60;
                timer = setInterval(function () {
                    countdown--;
                    if (countdown <= 0) {
                        clearInterval(timer);
                        timer = null;
                        $btn.prop('disabled', false).text('重新获取');
                        $hint.text('');
                    } else {
                        $btn.text(countdown + 's 后重发');
                    }
                }, 1000);
            } else {
                $hint.text(res.message);
                $btn.prop('disabled', false).text('获取验证码');
            }
        }, 'json').fail(function () {
            $hint.text('发送失败，请稍后重试');
            $btn.prop('disabled', false).text('获取验证码');
        });
    });
});
