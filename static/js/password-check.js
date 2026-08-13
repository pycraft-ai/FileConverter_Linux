/**
 * password-check.js -- 注册页实时密码强度校验
 * 依赖：元素 #password, #pwCheck（内含 .pw-item[data-rule] 项）
 * 与后端 routes/auth.py#validate_password_strength 规则保持一致
 */
$(function () {
    var $pw = $('#password');
    var $pwCheck = $('#pwCheck');
    if (!$pw.length || !$pwCheck.length) return;

    var MIN_LENGTH = 8;

    // 更新单条规则的显示状态
    function setRuleState(rule, passed) {
        var $item = $pwCheck.find('.pw-item[data-rule="' + rule + '"]');
        if (!$item.length) return;
        $item.toggleClass('ok', passed);
        $item.toggleClass('no', !passed);
        $item.find('i').removeClass('fa-circle fa-check-circle fa-times-circle')
            .addClass(passed ? 'fa-check-circle' : 'fa-times-circle');
    }

    function validate() {
        var val = $pw.val();
        if (val.length === 0) {
            // 为空时恢复默认样式
            $pwCheck.find('.pw-item').removeClass('ok no');
            $pwCheck.find('i').removeClass('fa-check-circle fa-times-circle').addClass('fa-circle');
            return;
        }
        setRuleState('length', val.length >= MIN_LENGTH);
        setRuleState('upper', /[A-Z]/.test(val));
        setRuleState('lower', /[a-z]/.test(val));
        setRuleState('digit', /\d/.test(val));
    }

    $pw.on('input', validate);

    // 页面初始若有值（提交失败回填），立即校验一次
    if ($pw.val().length > 0) validate();
});
