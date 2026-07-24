import random
import time
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database.db_manager import DatabaseManager
from utils.mail import send_verify_code
from config import Config

auth_bp = Blueprint('auth', __name__)


def generate_verify_code():
    """生成 6 位数字验证码"""
    return ''.join(str(random.randint(0, 9)) for _ in range(6))


@auth_bp.route('/send_verify_code', methods=['POST'])
def api_send_verify_code():
    """发送邮箱验证码（AJAX）"""
    email = request.form.get('email', '').strip()
    if not email or '@' not in email:
        return jsonify({'success': False, 'message': '请输入有效的邮箱'})

    # 禁止重复发送
    last_send = session.get('verify_code_send_time', 0)
    now = int(time.time())
    if now - last_send < Config.VERIFY_CODE_RESEND_INTERVAL:
        remain = Config.VERIFY_CODE_RESEND_INTERVAL - (now - last_send)
        return jsonify({'success': False, 'message': f'请 {remain} 秒后再试'})

    code = generate_verify_code()
    session['verify_code'] = code
    session['verify_code_email'] = email
    session['verify_code_time'] = now
    session['verify_code_send_time'] = now

    send_verify_code(email, code)
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

        success, user, msg = DatabaseManager.authenticate_user(
            username, password, login_type
        )
        if success:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            session['login_type'] = login_type
            session['remaining_times'] = user.get('remaining_times', 0)
            session['expiration_date'] = str(user['expiration_date'])
            from datetime import datetime
            session['contact_visit_time'] = datetime.now().isoformat()
            flash(msg, 'success')
            return redirect(url_for('converter.index'))
        else:
            flash(msg, 'error')

    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # 回填表单数据（密码不回填）
    form_data = {'username': '', 'email': '', 'verify_code': ''}

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        verify_code_input = request.form.get('verify_code', '').strip()

        # 保留非密码字段用于回显
        form_data = {'username': username, 'email': email, 'verify_code': verify_code_input}

        if not username or not password:
            flash('用户名和密码不能为空', 'error')
            return render_template('register.html', form=form_data)
        if not email:
            flash('请输入邮箱', 'error')
            return render_template('register.html', form=form_data)
        if password != confirm_password:
            flash('两次输入的密码不一致', 'error')
            return render_template('register.html', form=form_data)

        # 邮箱验证码校验
        saved_code = session.get('verify_code')
        saved_email = session.get('verify_code_email')
        code_time = session.get('verify_code_time', 0)
        now = int(time.time())

        if not saved_code:
            flash('请先获取邮箱验证码', 'error')
            return render_template('register.html', form=form_data)
        if email != saved_email:
            flash('邮箱与验证码不匹配，请重新获取', 'error')
            return render_template('register.html', form=form_data)
        if now - code_time > Config.VERIFY_CODE_EXPIRE:
            flash('验证码已过期，请重新获取', 'error')
            session.pop('verify_code', None)
            session.pop('verify_code_email', None)
            session.pop('verify_code_time', None)
            return render_template('register.html', form=form_data)
        if verify_code_input != saved_code:
            flash('验证码错误', 'error')
            return render_template('register.html', form=form_data)

        # 验证通过，清除 session 中的验证码
        session.pop('verify_code', None)
        session.pop('verify_code_email', None)
        session.pop('verify_code_time', None)
        session.pop('verify_code_send_time', None)

        success, msg = DatabaseManager.register_user(username, email, password)
        if success:
            flash('注册成功，请登录', 'success')
            return redirect(url_for('auth.login'))
        else:
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

        # 验证码校验
        saved_code = session.get('verify_code')
        saved_email = session.get('verify_code_email')
        code_time = session.get('verify_code_time', 0)
        now = int(time.time())

        if not saved_code:
            flash('请先获取邮箱验证码', 'error')
            return render_template('forgot_password.html', form={'email': email})
        if email != saved_email:
            flash('邮箱与验证码不匹配，请重新获取', 'error')
            return render_template('forgot_password.html', form={'email': email})
        if now - code_time > 300:
            flash('验证码已过期，请重新获取', 'error')
            session.pop('verify_code', None)
            session.pop('verify_code_email', None)
            session.pop('verify_code_time', None)
            return render_template('forgot_password.html', form={'email': email})
        if verify_code_input != saved_code:
            flash('验证码错误', 'error')
            return render_template('forgot_password.html', form={'email': email})

        # 清除验证码
        session.pop('verify_code', None)
        session.pop('verify_code_email', None)
        session.pop('verify_code_time', None)
        session.pop('verify_code_send_time', None)

        success, msg = DatabaseManager.reset_password(email, new_password)
        if success:
            flash('密码重置成功，请登录', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash(msg, 'error')
            return render_template('forgot_password.html', form={'email': email})

    return render_template('forgot_password.html', form={'email': ''})


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'success')
    return redirect(url_for('auth.login'))
