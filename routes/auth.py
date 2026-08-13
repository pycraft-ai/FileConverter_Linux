import random
import time
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database.db_manager import DatabaseManager
from utils.mail import send_verify_code
from utils import check_rate_limit, get_client_ip, validate_verify_code
from utils.logger import get_logger
from config import Config

auth_bp = Blueprint('auth', __name__)
logger = get_logger(__name__)


def generate_verify_code():
    """生成 6 位数字验证码"""
    return ''.join(str(random.randint(0, 9)) for _ in range(6))


def validate_password_strength(password: str):
    """
    校验密码强度。
    Returns: (is_valid: bool, error_message: str)
    """
    if len(password) < Config.PASSWORD_MIN_LENGTH:
        return False, f'密码长度不能少于 {Config.PASSWORD_MIN_LENGTH} 位'
    # 复杂度校验：大小写字母 + 数字（公网环境必须开启）
    if not any(c.isupper() for c in password):
        return False, '密码必须包含至少一个大写字母'
    if not any(c.islower() for c in password):
        return False, '密码必须包含至少一个小写字母'
    if not any(c.isdigit() for c in password):
        return False, '密码必须包含至少一个数字'
    return True, ''


@auth_bp.route('/send_verify_code', methods=['POST'])
def api_send_verify_code():
    """发送邮箱验证码（AJAX）——带 IP 限流"""
    email = request.form.get('email', '').strip()
    if not email or '@' not in email:
        return jsonify({'success': False, 'message': '请输入有效的邮箱'})

    # 1. session 级别防重复发送（短窗口）
    last_send = session.get('verify_code_send_time', 0)
    now = int(time.time())
    if now - last_send < Config.VERIFY_CODE_RESEND_INTERVAL:
        remain = Config.VERIFY_CODE_RESEND_INTERVAL - (now - last_send)
        return jsonify({'success': False, 'message': f'请 {remain} 秒后再试'})

    # 2. IP 级别限流（防止换 session 绕过）
    client_ip = get_client_ip()
    allowed, remaining = check_rate_limit(
        f'verify_code:{client_ip}',
        Config.VERIFY_CODE_IP_LIMIT,
        Config.VERIFY_CODE_IP_WINDOW
    )
    if not allowed:
        return jsonify({
            'success': False,
            'message': f'验证码发送过于频繁，请 {Config.VERIFY_CODE_IP_WINDOW // 60} 分钟后再试'
        })

    # 3. 同一邮箱也做限流
    email_key = f'verify_code_email:{email.lower()}'
    allowed, _ = check_rate_limit(email_key, 3, Config.VERIFY_CODE_IP_WINDOW)
    if not allowed:
        return jsonify({'success': False, 'message': '该邮箱验证码发送过于频繁，请稍后再试'})

    code = generate_verify_code()

    # 先尝试发送，成功后再保存到 session
    send_success = send_verify_code(email, code)
    if not send_success:
        logger.warning("验证码发送失败 | email=%s ip=%s", email, client_ip)
        return jsonify({'success': False, 'message': '邮件发送失败，请确认邮箱地址或稍后重试'})

    # 发送成功后才将验证码存入 session
    session['verify_code'] = code
    session['verify_code_email'] = email
    session['verify_code_time'] = now
    session['verify_code_send_time'] = now
    # 重新发送时重置尝试计数（新验证码给新的尝试机会）
    session['verify_code_attempts'] = 0

    return jsonify({'success': True, 'message': '验证码已发送，请查收'})


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        login_type = request.form.get('login_type', 'times')

        if not username or not password:
            flash('用户名和密码不能为空', 'error')
            return render_template('login.html')

        client_ip = get_client_ip()

        # 限流检查：IP + 用户名维度
        ip_key = f'login:{client_ip}'
        allowed, _ = check_rate_limit(ip_key, Config.LOGIN_RATE_LIMIT, Config.LOGIN_RATE_WINDOW)
        if not allowed:
            DatabaseManager.log_login_attempt(username, client_ip, False)
            flash('登录尝试过于频繁，请 5 分钟后再试', 'error')
            return render_template('login.html')

        # 检查数据库中的登录失败次数
        fail_count = DatabaseManager.get_login_failures(
            username, client_ip, Config.LOGIN_RATE_WINDOW
        )
        if fail_count >= Config.LOGIN_RATE_LIMIT * 2:
            DatabaseManager.log_login_attempt(username, client_ip, False)
            flash('登录失败次数过多，请 15 分钟后再试', 'error')
            return render_template('login.html')

        success, user, msg = DatabaseManager.authenticate_user(
            username, password, login_type
        )

        # 记录登录尝试
        DatabaseManager.log_login_attempt(username, client_ip, success)

        if success:
            # 登录成功 → 刷新 session（防 session fixation）
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            session['login_type'] = login_type
            session['remaining_times'] = user.get('remaining_times', 0)
            session['expiration_date'] = str(user['expiration_date'])
            from datetime import datetime
            session['contact_visit_time'] = datetime.now().isoformat()
            logger.info("用户登录成功 | user=%s admin=%s ip=%s", user['username'], user['is_admin'], client_ip)
            flash(msg, 'success')
            return redirect(url_for('converter.index'))
        else:
            logger.warning("用户登录失败 | user=%s ip=%s reason=%s", username, client_ip, msg)
            flash(msg, 'error')

    # 渲染登录页后清除自动填充数据，避免密码长期留在 session 中
    template = render_template('login.html')
    session.pop('prefill_username', None)
    session.pop('prefill_password', None)
    return template


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form_data = {'username': '', 'email': '', 'verify_code': '', 'password': '', 'confirm_password': ''}

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        verify_code_input = request.form.get('verify_code', '').strip()

        form_data = {
            'username': username, 'email': email, 'verify_code': verify_code_input,
            'password': password, 'confirm_password': confirm_password
        }

        # 基础校验
        if not username or not password:
            flash('用户名和密码不能为空', 'error')
            return render_template('register.html', form=form_data)
        if not email:
            flash('请输入邮箱', 'error')
            return render_template('register.html', form=form_data)
        if password != confirm_password:
            flash('两次输入的密码不一致', 'error')
            return render_template('register.html', form=form_data)

        # 密码强度校验
        is_strong, pw_msg = validate_password_strength(password)
        if not is_strong:
            flash(pw_msg, 'error')
            return render_template('register.html', form=form_data)

        # 邮箱验证码校验（带尝试次数限制 + 锁定，防暴力破解）
        saved_code = session.get('verify_code')
        code_ok, code_msg = validate_verify_code(verify_code_input, saved_code, email)
        if not code_ok:
            flash(code_msg, 'error')
            return render_template('register.html', form=form_data)

        success, msg = DatabaseManager.register_user(username, email, password)
        if success:
            logger.info("用户注册成功 | user=%s email=%s", username, email)
            # 将账号密码存入 session，用于登录页自动填充（登录成功后即清除）
            session['prefill_username'] = username
            session['prefill_password'] = password
            flash('注册成功，请登录', 'success')
            return redirect(url_for('auth.login'))
        else:
            logger.warning("用户注册失败 | user=%s email=%s reason=%s", username, email, msg)
            flash(msg, 'error')
            return render_template('register.html', form=form_data)

    return render_template('register.html', form=form_data)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        verify_code_input = request.form.get('verify_code', '').strip()

        if not email or not new_password:
            flash('请填写邮箱和新密码', 'error')
            return render_template('forgot_password.html', form={'email': email})
        if new_password != confirm_password:
            flash('两次输入的密码不一致', 'error')
            return render_template('forgot_password.html', form={'email': email})

        # 密码强度校验
        is_strong, pw_msg = validate_password_strength(new_password)
        if not is_strong:
            flash(pw_msg, 'error')
            return render_template('forgot_password.html', form={'email': email})

        # 验证码校验（带尝试次数限制 + 锁定，防暴力破解）
        saved_code = session.get('verify_code')
        code_ok, code_msg = validate_verify_code(verify_code_input, saved_code, email)
        if not code_ok:
            flash(code_msg, 'error')
            return render_template('forgot_password.html', form={'email': email})

        success, msg = DatabaseManager.reset_password(email, new_password)
        if success:
            logger.info("密码重置成功 | email=%s", email)
            flash('密码重置成功，请登录', 'success')
            return redirect(url_for('auth.login'))
        else:
            logger.warning("密码重置失败 | email=%s reason=%s", email, msg)
            flash(msg, 'error')
            return render_template('forgot_password.html', form={'email': email})

    return render_template('forgot_password.html', form={'email': ''})


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'success')
    return redirect(url_for('auth.login'))
