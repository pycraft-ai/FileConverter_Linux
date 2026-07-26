import os
import re
import uuid
import zipfile
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, session, redirect, \
    url_for, flash, send_file
from werkzeug.utils import secure_filename

from config import Config
from converter.converter_engine import Function
from database.db_manager import DatabaseManager
from utils import validate_file_content

converter_bp = Blueprint('converter', __name__)

# 模式配置
MODE_LIST = [
    'word转pdf', 'pdf转word', '图片转pdf', 'pdf转图片',
    'csv转excel', 'excel转csv', 'PDF OCR识别', '图片OCR识别',
    '图片转ppt', 'pdf合并', 'md转pdf', 'excel转pdf', 'ppt转pdf', 'html转pdf',
    'pdf加密', 'pdf解密'
]

MODE_INPUT_TYPE = {
    'word转pdf': 'file',
    'pdf转word': 'file',
    '图片转pdf': 'directory',
    'pdf转图片': 'file',
    'csv转excel': 'file',
    'excel转csv': 'file',
    'PDF OCR识别': 'file',
    '图片OCR识别': 'file',
    '图片转ppt': 'directory',
    'pdf合并': 'files',
    'md转pdf': 'file',
    'excel转pdf': 'file',
    'ppt转pdf': 'file',
    'html转pdf': 'file',
    'pdf加密': 'file',
    'pdf解密': 'file',
}

MODE_EXTENSIONS = {
    'word转pdf': '.docx',
    'pdf转word': '.pdf',
    '图片转pdf': None,
    'pdf转图片': '.pdf',
    'csv转excel': '.csv',
    'excel转csv': '.xlsx,.xls',
    'PDF OCR识别': '.pdf',
    '图片OCR识别': '.jpg,.jpeg,.png',
    '图片转ppt': None,
    'pdf合并': '.pdf',
    'md转pdf': '.md',
    'excel转pdf': '.xlsx,.xls',
    'ppt转pdf': '.pptx,.ppt',
    'html转pdf': '.html,.htm',
    'pdf加密': '.pdf',
    'pdf解密': '.pdf',
}

MODE_OUTPUT_EXT = {
    'word转pdf': '.pdf',
    'pdf转word': '.docx',
    '图片转pdf': '.pdf',
    'pdf转图片': None,
    'csv转excel': '.xlsx',
    'excel转csv': '.csv',
    'PDF OCR识别': '.txt',
    '图片OCR识别': '.txt',
    '图片转ppt': '.pptx',
    'pdf合并': '.pdf',
    'md转pdf': '.pdf',
    'excel转pdf': '.pdf',
    'ppt转pdf': '.pdf',
    'html转pdf': '.pdf',
    'pdf加密': '.enc.pdf',
    'pdf解密': '.dec.pdf',
}

MODE_TO_FUNCTION = {
    'word转pdf': 'word_to_pdf',
    'pdf转word': 'pdf_to_word',
    '图片转pdf': 'image_to_pdf',
    'pdf转图片': 'pdf_to_image',
    'csv转excel': 'csv_to_excel',
    'excel转csv': 'excel_to_csv',
    'PDF OCR识别': 'pdf_ocr',
    '图片OCR识别': 'image_ocr',
    '图片转ppt': 'img_to_ppt',
    'pdf合并': 'merge_pdf',
    'md转pdf': 'md_to_pdf',
    'excel转pdf': 'excel_to_pdf',
    'ppt转pdf': 'ppt_to_pdf',
    'html转pdf': 'html_to_pdf',
    'pdf加密': 'pdf_encrypt',
    'pdf解密': 'pdf_decrypt',
}

# 各模式最大文件数
MODE_MAX_FILES = {
    'pdf合并': 50,
    '图片转pdf': 100,
    '图片转ppt': 100,
}


# ============================================================
# 统一上传校验
# ============================================================

def _validate_uploaded_file(file, mode: str) -> str | None:
    """
    统一校验上传文件：扩展名 + 大小 + 双重扩展名检测。
    Returns: 错误消息字符串，None 表示通过。
    """
    # 类型校验
    if not file or file.filename == '':
        return '请选择有效的文件'

    if not allowed_file(file.filename, mode):
        return f'不支持的文件格式，请上传 {MODE_EXTENSIONS.get(mode)} 格式的文件'

    # 双重扩展名攻击检测（如 file.pdf.exe）
    name_without_ext, dot, ext = file.filename.rpartition('.')
    if '.' in name_without_ext:
        inner_ext = name_without_ext.rsplit('.', 1)[1].lower()
        allowed_exts = {'docx', 'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff',
                        'csv', 'xlsx', 'xls', 'pptx', 'ppt', 'txt', 'md', 'html', 'htm'}
        if inner_ext in allowed_exts and inner_ext != ext.lower():
            return '检测到文件扩展名伪装，已拒绝'

    # 大小校验
    try:
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
    except Exception:
        return '无法读取文件大小'

    if file_size > Config.UPLOAD_MAX_SIZE * 1024 * 1024:
        return f'文件 "{file.filename}" 大小超过限制（最大 {Config.UPLOAD_MAX_SIZE}MB）'

    return None


def _validate_saved_file(filepath: str, filename: str, mode: str) -> str | None:
    """
    文件保存后的内容校验：幻数 + 恶意内容扫描。
    Returns: 错误消息字符串，None 表示通过。
    """
    if '.' not in filename:
        return '文件缺少扩展名'

    ext = filename.rsplit('.', 1)[1].lower()

    # 内容验证
    is_valid, err_msg = validate_file_content(filepath, ext)
    if not is_valid:
        # 删除恶意文件
        try:
            os.remove(filepath)
        except Exception:
            pass
        return f'文件安全校验失败：{err_msg}'

    return None


def allowed_file(filename, mode):
    """检查文件扩展名是否允许"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed_exts = MODE_EXTENSIONS.get(mode)
    if allowed_exts is None:
        return ext in ['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff']
    allowed_list = [e.strip().lstrip('.') for e in allowed_exts.split(',')]
    return ext in allowed_list


# ============================================================
# 路由
# ============================================================

@converter_bp.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    user = DatabaseManager.get_user_by_username(session['username'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    if user.get('is_block'):
        session.clear()
        flash('您的账户已被封禁', 'error')
        return redirect(url_for('auth.login'))

    ann_success, announcements = DatabaseManager.get_active_announcements(5)
    if not ann_success:
        announcements = []

    return render_template(
        'index.html',
        modes=MODE_LIST,
        user=user,
        login_type=session.get('login_type', 'times'),
        announcements=announcements
    )


@converter_bp.route('/convert', methods=['POST'])
def convert():
    if 'username' not in session:
        return jsonify({'success': False, 'message': '请先登录'})

    mode = request.form.get('mode', '')
    # DEBUG
    print(f"[DEBUG] mode='{mode}' repr={repr(mode)} len={len(mode)} in_list={mode in MODE_LIST}")
    if mode not in MODE_LIST:
        return jsonify({'success': False, 'message': '无效的转换模式'})

    user = DatabaseManager.get_user_by_username(session['username'])
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'})
    if user['is_block']:
        return jsonify({'success': False, 'message': '账户已被封禁'})

    login_type = session.get('login_type', 'times')
    if login_type == 'time':
        if datetime.now() > user['expiration_date']:
            return jsonify({'success': False, 'message': '账户已过期'})
    elif login_type == 'times':
        if user['remaining_times'] <= 0:
            return jsonify({'success': False, 'message': '剩余次数不足'})

    task_id = uuid.uuid4().hex
    input_type = MODE_INPUT_TYPE.get(mode, 'file')

    try:
        input_paths = []
        original_filenames = []
        max_files = MODE_MAX_FILES.get(mode, 10)

        if input_type == 'file':
            files = request.files.getlist('file')
            if not files or len(files) == 0:
                return jsonify({'success': False, 'message': '请选择文件'})

            if len(files) > max_files:
                return jsonify({'success': False, 'message': f'最多同时上传 {max_files} 个文件'})

            for i, file in enumerate(files):
                err = _validate_uploaded_file(file, mode)
                if err:
                    return jsonify({'success': False, 'message': err})

                original_filename = file.filename
                ext = os.path.splitext(original_filename)[1] if '.' in original_filename else ''
                filename = f'{task_id}_{i}{ext}'
                save_path = os.path.join(Config.UPLOAD_FOLDER, filename)
                file.save(save_path)

                # 文件保存后内容安全校验
                err = _validate_saved_file(save_path, original_filename, mode)
                if err:
                    return jsonify({'success': False, 'message': err})

                input_paths.append(save_path)
                original_filenames.append(original_filename)

            if len(input_paths) == 0:
                return jsonify({'success': False, 'message': '没有有效的文件'})

        elif input_type == 'files':
            files = request.files.getlist('files')
            if not files or len(files) == 0:
                return jsonify({'success': False, 'message': '请选择文件'})

            pdf_max = MODE_MAX_FILES.get(mode, 50)
            if len(files) > pdf_max:
                return jsonify({'success': False, 'message': f'最多合并 {pdf_max} 个文件'})

            for i, file in enumerate(files):
                err = _validate_uploaded_file(file, mode)
                if err:
                    return jsonify({'success': False, 'message': err})

                original_filename = file.filename
                ext = os.path.splitext(original_filename)[1] if '.' in original_filename else ''
                filename = f'{task_id}_{i}{ext}'
                save_path = os.path.join(Config.UPLOAD_FOLDER, filename)
                file.save(save_path)

                # 文件保存后内容安全校验
                err = _validate_saved_file(save_path, original_filename, mode)
                if err:
                    return jsonify({'success': False, 'message': err})

                input_paths.append(save_path)
                original_filenames.append(original_filename)

        elif input_type == 'directory':
            files = request.files.getlist('files')
            if not files or len(files) == 0:
                return jsonify({'success': False, 'message': '请选择文件'})

            img_max = MODE_MAX_FILES.get(mode, 100)
            if len(files) > img_max:
                return jsonify({'success': False, 'message': f'最多上传 {img_max} 张图片'})

            dir_path = os.path.join(Config.UPLOAD_FOLDER, task_id)
            os.makedirs(dir_path, exist_ok=True)
            file_count = 0
            for i, file in enumerate(files):
                if file and file.filename != '':
                    if not allowed_file(file.filename, mode):
                        continue
                    # 统一大小检查
                    try:
                        file.seek(0, 2)
                        file_size = file.tell()
                        file.seek(0)
                        if file_size > Config.UPLOAD_MAX_SIZE * 1024 * 1024:
                            continue  # 跳过大文件
                    except Exception:
                        continue

                    original_filename = file.filename
                    ext = os.path.splitext(original_filename)[1] if '.' in original_filename else ''
                    filename = f'{i}{ext}'
                    save_full_path = os.path.join(dir_path, filename)
                    file.save(save_full_path)

                    # 文件保存后内容安全校验
                    err = _validate_saved_file(save_full_path, original_filename, mode)
                    if err:
                        try:
                            os.remove(save_full_path)
                        except Exception:
                            pass
                        continue  # 跳过恶意文件

                    file_count += 1

            if file_count == 0:
                return jsonify({'success': False, 'message': '没有有效的图片文件'})
            input_paths = [dir_path]

        # ---- 执行转换 ----
        result_message = '转换成功'

        if mode == 'pdf合并':
            first_name = os.path.splitext(original_filenames[0])[0] if original_filenames else 'merged'
            output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{first_name}_合并.pdf')
            result = Function.merge_pdf(input_paths, output_path)
        elif mode == 'pdf转图片':
            output_dir = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_images')
            os.makedirs(output_dir, exist_ok=True)
            result = Function.pdf_to_image(input_paths[0], output_dir)
            if result:
                image_files = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
                if not image_files:
                    return jsonify({'success': False, 'message': 'PDF转换失败，未生成图片'})

                img_base = os.path.splitext(original_filenames[0])[0] if original_filenames else 'pdf'
                zip_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{img_base}_图片.zip')
                try:
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for img_file in image_files:
                            zipf.write(os.path.join(output_dir, img_file), img_file)
                    if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
                        return jsonify({'success': False, 'message': '文件打包失败，请重试'})
                    output_path = zip_path
                except Exception:
                    return jsonify({'success': False, 'message': '文件打包失败，请重试'})
        elif mode in ('pdf加密', 'pdf解密'):
            password = request.form.get('password', '').strip()
            if not password:
                return jsonify({'success': False, 'message': '请输入密码'})
            if mode == 'pdf加密' and len(password) < 4:
                return jsonify({'success': False, 'message': '加密密码长度不能少于4位'})

            output_paths = []
            failed_files = []
            suffix = '加密' if mode == 'pdf加密' else '解密'
            for i, input_path in enumerate(input_paths):
                orig_name = original_filenames[i] if i < len(original_filenames) else os.path.basename(input_path)
                base_name, _ = os.path.splitext(orig_name)
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}_{suffix}.pdf')

                try:
                    if mode == 'pdf加密':
                        single_result = Function.pdf_encrypt(input_path, output_path, password)
                    else:
                        single_result = Function.pdf_decrypt(input_path, output_path, password)

                    if single_result and os.path.exists(output_path):
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    print(f"{mode} 文件 {orig_name} 失败: {conv_err}")
                    failed_files.append(orig_name)

            if not output_paths:
                result = False
            else:
                result = True
                if len(output_paths) == 1:
                    output_path = output_paths[0]
                else:
                    zip_name = f'{task_id}_转换结果.zip'
                    zip_path = os.path.join(Config.OUTPUT_FOLDER, zip_name)
                    try:
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for out_path in output_paths:
                                zipf.write(out_path, os.path.basename(out_path))
                        output_path = zip_path
                    except Exception:
                        return jsonify({'success': False, 'message': '文件打包失败，请重试'})

                if failed_files:
                    result_message = f'成功 {len(output_paths)} 个，失败: {", ".join(failed_files)}'
                else:
                    result_message = '转换成功'
        elif input_type == 'directory':
            dir_name = os.path.basename(input_paths[0]) if input_paths else task_id
            output_path = os.path.join(
                Config.OUTPUT_FOLDER,
                f'{task_id}_{dir_name}{MODE_OUTPUT_EXT.get(mode, ".pdf")}'
            )
            result = getattr(Function, MODE_TO_FUNCTION[mode])(
                input_paths[0], output_path
            )
        else:
            func_name = MODE_TO_FUNCTION.get(mode)
            if not func_name:
                return jsonify({'success': False, 'message': '无效的转换模式'})

            output_paths = []
            failed_files = []

            for i, input_path in enumerate(input_paths):
                orig_name = original_filenames[i] if i < len(original_filenames) else os.path.basename(input_path)
                base_name, _ = os.path.splitext(orig_name)
                out_ext = MODE_OUTPUT_EXT.get(mode, '')
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}{out_ext}')

                try:
                    single_result = getattr(Function, func_name)(input_path, output_path)
                    if single_result and os.path.exists(output_path):
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    print(f"转换文件 {orig_name} 失败: {conv_err}")
                    failed_files.append(orig_name)

            if not output_paths:
                result = False
            else:
                result = True
                if len(output_paths) == 1:
                    output_path = output_paths[0]
                else:
                    zip_name = f'{task_id}_转换结果.zip'
                    zip_path = os.path.join(Config.OUTPUT_FOLDER, zip_name)
                    try:
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for out_path in output_paths:
                                zipf.write(out_path, os.path.basename(out_path))
                        output_path = zip_path
                    except Exception:
                        return jsonify({'success': False, 'message': '文件打包失败，请重试'})

                if failed_files:
                    result_message = f'成功 {len(output_paths)} 个，失败: {", ".join(failed_files)}'
                else:
                    result_message = '转换成功'

        if result:
            # 记录成功日志
            filename_list = ', '.join([os.path.basename(p) for p in input_paths])
            DatabaseManager.log_conversion(
                session['username'], mode, filename_list, True, '转换成功',
                output_path=output_path
            )

            remaining_times = None
            if login_type == 'times':
                success, msg = DatabaseManager.decrease_user_times(
                    session['username'], 1
                )
                if not success:
                    print(f"扣减次数失败: {msg}")
                else:
                    match = re.search(r'当前剩余 (\d+) 次', msg)
                    if match:
                        remaining_times = int(match.group(1))

            updated_user = DatabaseManager.get_user_by_username(session['username'])
            if updated_user:
                current_remaining = updated_user.get('remaining_times', 0)
                session['remaining_times'] = current_remaining
                if remaining_times is None:
                    remaining_times = current_remaining
            else:
                session['remaining_times'] = remaining_times or session.get('remaining_times', 0)

            output_basename = os.path.basename(output_path)
            # 去除 task_id_ 前缀得到显示名
            display_name = output_basename
            task_prefix = f'{task_id}_'
            if output_basename.startswith(task_prefix):
                display_name = output_basename[len(task_prefix):]

            return jsonify({
                'success': True,
                'message': result_message,
                'download_url': url_for(
                    'converter.download', filename=output_basename, name=display_name
                ),
                'display_name': display_name,
                'remaining_times': remaining_times
            })
        else:
            filename_list = ', '.join([os.path.basename(p) for p in input_paths])
            DatabaseManager.log_conversion(
                session['username'], mode, filename_list, False, '转换失败'
            )
            return jsonify({'success': False, 'message': '转换失败，请检查文件格式或联系管理员'})

    except Exception as e:
        # 记录异常日志（详细信息写入服务端日志，前端只返回通用错误）
        mode_safe = request.form.get('mode', '未知')
        print(f"[Convert Error] user={session.get('username')} mode={mode_safe} err={e}")
        DatabaseManager.log_conversion(
            session.get('username', '未知'), mode_safe, '', False,
            f'系统异常: {type(e).__name__}'  # 只记录异常类型，不记录详细信息
        )
        return jsonify({'success': False, 'message': '服务器处理出错，请稍后重试或联系管理员'})


@converter_bp.route('/download/<filename>')
def download(filename):
    """下载转换后的文件"""
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    # 安全检查：防止路径穿越
    safe_path = os.path.normpath(
        os.path.join(Config.OUTPUT_FOLDER, filename)
    )
    if not safe_path.startswith(os.path.normpath(Config.OUTPUT_FOLDER)):
        return jsonify({'success': False, 'message': '无效的文件路径'})

    if not os.path.exists(safe_path):
        return jsonify({'success': False, 'message': '文件不存在或已过期'})

    # 用 name 参数作为下载显示的文件名（去掉哈希前缀）
    display_name = request.args.get('name') or filename
    return send_file(safe_path, as_attachment=True, download_name=display_name)


@converter_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    """联系作者页面"""
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    username = session['username']

    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not subject or not message:
            return jsonify({'success': False, 'message': '请填写主题和内容'})

        success, msg = DatabaseManager.submit_contact_message(
            subject=subject,
            message=message,
            username=username,
            name=session.get('username', ''),
            email=''
        )
        return jsonify({'success': success, 'message': msg})

    session['contact_visit_time'] = datetime.now().isoformat()

    success, my_messages, total = DatabaseManager.get_messages_by_username(username)
    if not success:
        my_messages = []
        total = 0

    return render_template('contact.html', my_messages=my_messages, total=total)


@converter_bp.route('/api/user_unread_replies')
def user_unread_replies():
    """获取用户未读回复数"""
    if 'username' not in session:
        return jsonify({'count': 0})

    username = session['username']
    visit_time = session.get('contact_visit_time')

    count = DatabaseManager.get_unread_reply_count(username, visit_time)
    return jsonify({'count': count})


@converter_bp.route('/my_logs')
def my_logs():
    """当前用户的转换记录"""
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    username = session['username']
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    offset = (page - 1) * per_page

    success, logs, total = DatabaseManager.get_user_logs(username, per_page, offset)
    if not success:
        logs = []
        total = 0

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return render_template(
        'my_logs.html',
        logs=logs,
        page=page,
        total_pages=total_pages,
        total=total
    )
