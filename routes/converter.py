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
from utils import (
    validate_file_content, get_client_ip, check_rate_limit,
    validate_pdf_page_count, validate_image_dimensions,
)
from utils.logger import get_logger

converter_bp = Blueprint('converter', __name__)
logger = get_logger(__name__)

# 模式配置
MODE_LIST = [
    'word转pdf', 'pdf转word', '图片转pdf', 'pdf转图片',
    'csv转excel', 'excel转csv', 'PDF OCR识别', '图片OCR识别',
    '图片转ppt', 'pdf合并', 'md转pdf', 'excel转pdf', 'ppt转pdf', 'html转pdf',
    'pdf加密', 'pdf解密',
    '文件压缩', '文件解压', '压缩包解密',
    'pdf转ppt', 'ppt转word', 'pdf转html', 'md转html', '图片格式互转',
    'pdf压缩', 'pdf分割', 'pdf转excel', '图片压缩', '文字转语音'
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
    '文件压缩': 'files',
    '文件解压': 'file',
    '压缩包解密': 'file',
    'pdf转ppt': 'file',
    'ppt转word': 'file',
    'pdf转html': 'file',
    'md转html': 'file',
    '图片格式互转': 'file',
    'pdf压缩': 'file',
    'pdf分割': 'file',
    'pdf转excel': 'file',
    '图片压缩': 'file',
    '文字转语音': 'file',
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
    '文件压缩': None,
    '文件解压': '.zip,.tar.gz,.tgz,.tar,.7z',
    '压缩包解密': '.zip,.7z',
    'pdf转ppt': '.pdf',
    'ppt转word': '.pptx,.ppt',
    'pdf转html': '.pdf',
    'md转html': '.md',
    '图片格式互转': '.jpg,.jpeg,.png,.webp,.bmp,.gif,.tiff',
    'pdf压缩': '.pdf',
    'pdf分割': '.pdf',
    'pdf转excel': '.pdf',
    '图片压缩': '.jpg,.jpeg,.png,.webp,.bmp,.gif,.tiff',
    '文字转语音': '.txt',
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
    '文件压缩': '.zip',
    '文件解压': '.zip',
    '压缩包解密': '.zip',
    'pdf转ppt': '.pptx',
    'ppt转word': '.docx',
    'pdf转html': '.html',
    'md转html': '.html',
    '图片格式互转': None,
    'pdf压缩': '.pdf',
    'pdf分割': '.pdf',
    'pdf转excel': '.xlsx',
    '图片压缩': None,
    '文字转语音': '.mp3',
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
    'pdf转ppt': 'pdf_to_ppt',
    'ppt转word': 'ppt_to_word',
    'pdf转html': 'pdf_to_html',
    'md转html': 'md_to_html',
    '图片格式互转': 'image_convert',
    'pdf压缩': 'pdf_compress',
    'pdf分割': 'pdf_split',
    'pdf转excel': 'pdf_to_excel',
    '图片压缩': 'image_compress',
    '文字转语音': 'txt_to_speech',
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
        allowed_exts = {'docx', 'pdf', 'jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp',
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
    压缩模式接受任意文件，跳过内容校验。
    Returns: 错误消息字符串，None 表示通过。
    """
    if '.' not in filename:
        return '文件缺少扩展名'

    ext = filename.rsplit('.', 1)[1].lower()

    # 压缩/解压/去密模式接受任意文件，跳过内容校验
    if mode in ('文件压缩', '文件解压', '压缩包解密'):
        return None

    # 内容验证
    is_valid, err_msg = validate_file_content(filepath, ext)
    if not is_valid:
        # 删除恶意文件
        try:
            os.remove(filepath)
        except Exception:
            pass
        return f'文件安全校验失败：{err_msg}'

    # ===== DoS 防护：PDF 页数限制 =====
    # 渲染/OCR 超大 PDF 会耗尽 CPU/内存，限制最大页数
    if ext == 'pdf':
        pdf_ok, page_count = validate_pdf_page_count(filepath)
        if not pdf_ok:
            try:
                os.remove(filepath)
            except Exception:
                pass
            return f'PDF 页数过多（{page_count} 页），超过最大允许 {Config.PDF_MAX_PAGES} 页'

    # ===== DoS 防护：图片像素限制 =====
    # 超大图片（如 10000x10000）解码会 OOM，限制宽*高
    if ext in ('jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp'):
        img_ok, dim = validate_image_dimensions(filepath)
        if not img_ok:
            try:
                os.remove(filepath)
            except Exception:
                pass
            if dim:
                return f'图片尺寸过大（{dim[0]}x{dim[1]} 像素），请压缩后再上传'
            return '无法读取图片尺寸，已拒绝'

    return None


def allowed_file(filename, mode):
    """检查文件扩展名是否允许"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed_exts = MODE_EXTENSIONS.get(mode)
    if allowed_exts is None:
        # 压缩模式允许所有文件类型
        if mode == '文件压缩':
            return True
        return ext in ['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff']
    allowed_list = [e.strip().lstrip('.') for e in allowed_exts.split(',')]
    return ext in allowed_list


# ============================================================
# 路由
# ============================================================

@converter_bp.route('/')
def index():
    # ---- 登录用户：正常展示 ----
    if 'username' in session:
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
            is_guest=False,
            guest_remaining=0,
            login_type=session.get('login_type', 'times'),
            announcements=announcements
        )

    # ---- 游客：允许访问主页，限制可体验次数 ----
    session['is_guest'] = True
    session.setdefault('guest_used_times', 0)

    ann_success, announcements = DatabaseManager.get_active_announcements(5)
    if not ann_success:
        announcements = []

    guest_remaining = max(Config.GUEST_MAX_TIMES - session.get('guest_used_times', 0), 0)

    return render_template(
        'index.html',
        modes=MODE_LIST,
        user=None,
        is_guest=True,
        guest_remaining=guest_remaining,
        login_type='guest',
        announcements=announcements
    )


@converter_bp.route('/convert', methods=['POST'])
def convert():
    mode = request.form.get('mode', '')
    if mode not in MODE_LIST:
        logger.warning("无效的转换模式 | user=%s mode=%s", session.get('username'), repr(mode))
        return jsonify({'success': False, 'message': '无效的转换模式'})

    # ---- 判断身份：登录用户 / 游客 ----
    is_guest = 'username' not in session
    if is_guest:
        session['is_guest'] = True
        session.setdefault('guest_used_times', 0)

        # ===== 游客防滥用（IP 维度限流）=====
        # 游客次数存在 session cookie，可被无痕浏览/清 cookie 绕过，
        # 因此额外基于真实 IP 做限流，换浏览器也无法绕过。
        client_ip = get_client_ip() or request.remote_addr
        # 每小时窗口限流
        allowed_hourly, _ = check_rate_limit(
            f'guest_hourly:{client_ip}', Config.GUEST_IP_HOURLY_LIMIT, 3600
        )
        if not allowed_hourly:
            logger.warning("游客转换触发小时级限流 | ip=%s", client_ip)
            return jsonify({
                'success': False,
                'message': f'当前网络在 1 小时内使用游客转换过于频繁，请稍后再试或登录解锁',
                'need_login': False
            })
        # 每天（24小时滑动窗口）限流
        allowed_daily, _ = check_rate_limit(
            f'guest_daily:{client_ip}', Config.GUEST_IP_DAILY_LIMIT, 24 * 3600
        )
        if not allowed_daily:
            logger.warning("游客转换触发每日限流 | ip=%s", client_ip)
            return jsonify({
                'success': False,
                'message': f'当前网络今天的游客转换次数已达上限，请明天再试或登录解锁',
                'need_login': False
            })

        # 游客 session 次数校验：用完则提示登录
        if session.get('guest_used_times', 0) >= Config.GUEST_MAX_TIMES:
            logger.info("游客体验次数已用完 | ip=%s", client_ip)
            return jsonify({
                'success': False,
                'message': f'游客只能体验 {Config.GUEST_MAX_TIMES} 次，登录即可解锁更多权益',
                'need_login': True
            })
        user = None
        login_type = 'guest'
    else:
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

    # 统一标识用于日志
    _uname = 'guest' if is_guest else session['username']
    # 真实客户端 IP（用于日志溯源 / 游客防滥用）
    _client_ip = get_client_ip() or request.remote_addr or ''

    task_id = uuid.uuid4().hex
    input_type = MODE_INPUT_TYPE.get(mode, 'file')

    # OCR 模式：支持选择输出格式（txt / md / docx）
    output_format = 'txt'
    if mode in ('PDF OCR识别', '图片OCR识别'):
        output_format = request.form.get('output_format', 'txt').lower()
        if output_format not in ('txt', 'md', 'docx'):
            output_format = 'txt'

    logger.info("开始转换 | user=%s mode=%s task_id=%s", _uname, mode, task_id)

    # 将 task_id 绑定到当前会话，用于下载时校验文件归属（防 IDOR 越权下载）
    owned = session.get('owned_tasks') or []
    if task_id not in owned:
        owned.append(task_id)
        # 仅保留最近 50 个，避免会话无限膨胀
        session['owned_tasks'] = owned[-50:]
        session.modified = True

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

        # ---- 重复文件检测 ----
        if not request.form.get('confirmed'):
            last_info = session.get('last_file_info')
            if (last_info and input_type == 'file' and original_filenames
                    and not session.get('skip_duplicate_check')):
                current_name = original_filenames[0]
                current_size = os.path.getsize(input_paths[0]) if input_paths else 0
                if (current_name == last_info.get('name')
                        and current_size == last_info.get('size')):
                    return jsonify({
                        'duplicate_warning': True,
                        'message': '检测到与上次转换文件相同，为避免浪费次数，请确认是否继续转换'
                    })

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
                base_name = secure_filename(base_name)
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
                    logger.error("文件处理失败 | mode=%s file=%s err=%s", mode, orig_name, conv_err)
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
        elif mode == '文件压缩':
            password = request.form.get('password', '').strip() or None
            archive_format = request.form.get('archive_format', 'zip')
            if archive_format not in ('zip', 'tar.gz', '7z'):
                return jsonify({'success': False, 'message': '不支持的压缩格式'})
            if password and archive_format == 'tar.gz':
                return jsonify({'success': False, 'message': 'TAR.GZ 格式不支持密码加密，请选择 ZIP 或 7Z'})
            if password and len(password) < 4:
                return jsonify({'success': False, 'message': '加密密码长度不能少于 4 位'})

            # 用第一个文件名作为压缩包命名基础
            base_name = os.path.splitext(original_filenames[0])[0] if original_filenames else '文件'
            base_name = secure_filename(base_name)
            output_ext = '.tar.gz' if archive_format == 'tar.gz' else f'.{archive_format}'
            output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}_压缩包{output_ext}')

            if archive_format == 'zip':
                result = Function.compress_zip(input_paths, output_path, password, original_filenames)
            elif archive_format == 'tar.gz':
                result = Function.compress_targz(input_paths, output_path, original_filenames)
            elif archive_format == '7z':
                result = Function.compress_7z(input_paths, output_path, password, original_filenames)
            result_message = '压缩成功'

        elif mode == '文件解压':
            password = request.form.get('password', '').strip() or None

            # 未提供密码时检查是否加密
            if not password and Function.is_archive_encrypted(input_paths[0]):
                return jsonify({
                    'need_password': True,
                    'message': '检测到该压缩文件加密，请输入密码'
                })

            # 执行解压
            output_dir = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_解压文件')
            os.makedirs(output_dir, exist_ok=True)
            result = Function.decompress_archive(input_paths[0], output_dir, password)

            if result:
                # 收集解压出的文件列表，为每个文件生成下载 URL
                extracted_files = []
                for root, _dirs, files in os.walk(output_dir):
                    for f in files:
                        rel_path = os.path.relpath(os.path.join(root, f), output_dir)
                        # 下载路径：解压目录名/相对路径
                        dl_path = f'{os.path.basename(output_dir)}/{rel_path}'.replace('\\', '/')
                        dl_url = url_for('converter.download', filename=dl_path, name=f)
                        extracted_files.append({
                            'path': rel_path,
                            'name': f,
                            'download_url': dl_url
                        })

                # 打包为 ZIP 供下载
                zip_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_解压文件.zip')
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _dirs, files in os.walk(output_dir):
                        for f in files:
                            file_path = os.path.join(root, f)
                            arcname = os.path.relpath(file_path, output_dir)
                            zipf.write(file_path, arcname)
                output_path = zip_path
                # 用变量传递 extracted_files 到结果处理
                _extracted_files = extracted_files
                result_message = f'解压成功，共 {len(extracted_files)} 个文件'
            else:
                # 如果带密码仍失败，可能是密码错误
                if password:
                    return jsonify({'success': False, 'message': '解压失败，密码错误或文件损坏'})

        elif mode == '压缩包解密':
            password = request.form.get('password', '').strip()
            if not password:
                return jsonify({'success': False, 'message': '请输入压缩包密码'})
            if len(password) < 1:
                return jsonify({'success': False, 'message': '请输入密码'})

            output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_已解密.zip')
            result = Function.decrypt_archive(input_paths[0], output_path, password)
            result_message = '已去除密码保护'

        elif mode == '图片格式互转':
            target_fmt = request.form.get('target_format', 'png').strip().lower()
            valid_fmts = ('jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif', 'tiff')
            if target_fmt not in valid_fmts:
                return jsonify({'success': False, 'message': f'不支持的目标格式，可选：{", ".join(valid_fmts)}'})
            output_ext = '.jpg' if target_fmt == 'jpeg' else f'.{target_fmt}'

            output_paths = []
            failed_files = []
            for i, input_path in enumerate(input_paths):
                orig_name = original_filenames[i] if i < len(original_filenames) else os.path.basename(input_path)
                base_name, _ = os.path.splitext(orig_name)
                base_name = secure_filename(base_name)
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}_转{target_fmt.upper()}{output_ext}')

                try:
                    single_result = Function.image_convert(input_path, output_path, target_fmt)
                    if single_result and os.path.exists(output_path):
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    logger.error("图片格式互转失败 | file=%s err=%s", orig_name, conv_err)
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

        elif mode == 'pdf压缩':
            quality = request.form.get('quality', 'medium').strip().lower()
            if quality not in ('low', 'medium', 'high'):
                return jsonify({'success': False, 'message': '无效的压缩等级，可选：low/medium/high'})

            output_paths = []
            failed_files = []
            for i, input_path in enumerate(input_paths):
                orig_name = original_filenames[i] if i < len(original_filenames) else os.path.basename(input_path)
                base_name, _ = os.path.splitext(orig_name)
                base_name = secure_filename(base_name)
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}_压缩.pdf')

                try:
                    single_result = Function.pdf_compress(input_path, output_path, quality)
                    if single_result and os.path.exists(output_path):
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    logger.error("PDF压缩失败 | file=%s err=%s", orig_name, conv_err)
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
                    result_message = '压缩成功'

        elif mode == 'pdf分割':
            page_range = request.form.get('page_range', '').strip()
            if not page_range:
                return jsonify({'success': False, 'message': '请输入页码范围，如 1-3,5,7-10'})

            output_paths = []
            failed_files = []
            for i, input_path in enumerate(input_paths):
                orig_name = original_filenames[i] if i < len(original_filenames) else os.path.basename(input_path)
                base_name, _ = os.path.splitext(orig_name)
                base_name = secure_filename(base_name)
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}_提取.pdf')

                try:
                    split_result = Function.pdf_split(input_path, output_path, page_range)
                    if split_result and os.path.exists(output_path):
                        total_p, extracted_p = split_result
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    logger.error("PDF分割失败 | file=%s err=%s", orig_name, conv_err)
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
                    result_message = '提取成功'

        elif mode == '图片压缩':
            img_quality = request.form.get('img_quality', '75')
            try:
                img_quality = int(img_quality)
                if not 1 <= img_quality <= 100:
                    raise ValueError
            except ValueError:
                return jsonify({'success': False, 'message': '压缩质量参数无效，请输入 1-100 的整数'})

            output_paths = []
            failed_files = []
            for i, input_path in enumerate(input_paths):
                orig_name = original_filenames[i] if i < len(original_filenames) else os.path.basename(input_path)
                base_name, ext = os.path.splitext(orig_name)
                base_name = secure_filename(base_name)
                ext = secure_filename(ext)
                # 保持原格式或转为 jpg
                out_ext = ext if ext.lower() in ('.jpg', '.jpeg', '.png', '.webp') else '.jpg'
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}_压缩{out_ext}')

                try:
                    single_result = Function.image_compress(input_path, output_path, img_quality)
                    if single_result and os.path.exists(output_path):
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    logger.error("图片压缩失败 | file=%s err=%s", orig_name, conv_err)
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
                    result_message = '压缩成功'

        elif mode == '文字转语音':
            voice = request.form.get('voice', 'zh-CN-XiaoxiaoNeural').strip()
            rate = request.form.get('rate', '+0%').strip()

            output_paths = []
            failed_files = []
            for i, input_path in enumerate(input_paths):
                orig_name = original_filenames[i] if i < len(original_filenames) else os.path.basename(input_path)
                base_name, _ = os.path.splitext(orig_name)
                base_name = secure_filename(base_name)
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}.mp3')
                try:
                    single_result = Function.txt_to_speech(input_path, output_path, voice=voice, rate=rate)
                    if single_result and os.path.exists(output_path):
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    logger.error("文字转语音失败 | file=%s err=%s", orig_name, conv_err)
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
            # OCR 模式输出扩展名跟随所选格式
            if mode in ('PDF OCR识别', '图片OCR识别'):
                out_ext = f'.{output_format}'
            else:
                out_ext = MODE_OUTPUT_EXT.get(mode, '.pdf')
            output_path = os.path.join(
                Config.OUTPUT_FOLDER,
                f'{task_id}_{dir_name}{out_ext}'
            )
            # 注意：directory 模式目前仅支持 图片转pdf / 图片转ppt，均为 2 参函数。
            # 若未来扩展支持 directory 输入的 OCR 模式，需在下方按需传入第 3 参 output_format。
            if mode in ('PDF OCR识别', '图片OCR识别'):
                result = getattr(Function, MODE_TO_FUNCTION[mode])(
                    input_paths[0], output_path, output_format
                )
            else:
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
                base_name = secure_filename(base_name)
                # OCR 模式输出扩展名跟随所选格式
                if mode in ('PDF OCR识别', '图片OCR识别'):
                    out_ext = f'.{output_format}'
                else:
                    out_ext = MODE_OUTPUT_EXT.get(mode, '')
                output_path = os.path.join(Config.OUTPUT_FOLDER, f'{task_id}_{base_name}{out_ext}')

                try:
                    if mode in ('PDF OCR识别', '图片OCR识别'):
                        single_result = getattr(Function, func_name)(input_path, output_path, output_format)
                    else:
                        single_result = getattr(Function, func_name)(input_path, output_path)
                    if single_result and os.path.exists(output_path):
                        output_paths.append(output_path)
                    else:
                        failed_files.append(orig_name)
                except Exception as conv_err:
                    logger.error("转换文件失败 | file=%s err=%s", orig_name, conv_err)
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
            # 记录成功日志（使用原始文件名，而非哈希后的保存路径）
            filename_list = ', '.join(original_filenames) if original_filenames else ', '.join([os.path.basename(p) for p in input_paths])
            DatabaseManager.log_conversion(
                _uname, mode, filename_list, True, '转换成功',
                output_path=output_path, ip_address=_client_ip
            )
            logger.info("转换成功 | user=%s mode=%s files=%s", _uname, mode, filename_list)

            # 保存本次转换的文件信息（用于下次重复检测）
            if original_filenames and input_paths:
                session['last_file_info'] = {
                    'name': original_filenames[0],
                    'size': os.path.getsize(input_paths[0])
                }
            # 如果用户勾选了"本次不再提示"，记录到 session
            if request.form.get('dont_ask_again'):
                session['skip_duplicate_check'] = True

            deduction_failed = False
            remaining_times = None

            if is_guest:
                # 游客：用 session 累计体验次数，不扣数据库次数
                session['guest_used_times'] = session.get('guest_used_times', 0) + 1
                remaining_times = max(Config.GUEST_MAX_TIMES - session['guest_used_times'], 0)
            elif login_type == 'times':
                success, msg = DatabaseManager.decrease_user_times(
                    session['username'], 1
                )
                if not success:
                    logger.error("扣减次数失败 | user=%s msg=%s", session['username'], msg)
                    deduction_failed = True
                else:
                    match = re.search(r'当前剩余 (\d+) 次', msg)
                    if match:
                        remaining_times = int(match.group(1))

            if not is_guest:
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

            # 次数扣减失败时，在前端提示用户
            if deduction_failed:
                result_message += '（注意：次数扣减异常，请联系管理员）'

            resp = {
                'success': True,
                'message': result_message,
                'download_url': url_for(
                    'converter.download', filename=output_basename, name=display_name
                ),
                'display_name': display_name,
                'remaining_times': remaining_times
            }

            # 解压模式额外返回文件列表
            if mode == '文件解压' and result:
                resp['extracted_files'] = _extracted_files
                resp['file_count'] = len(_extracted_files)

            return jsonify(resp)
        else:
            filename_list = ', '.join(original_filenames) if original_filenames else ', '.join([os.path.basename(p) for p in input_paths])
            DatabaseManager.log_conversion(
                _uname, mode, filename_list, False, '转换失败',
                ip_address=_client_ip
            )
            logger.warning("转换失败 | user=%s mode=%s files=%s", _uname, mode, filename_list)

            # 根据模式和上下文给出特定错误提示
            has_password = bool(request.form.get('password', '').strip())
            error_msgs = {
                '文件压缩': '压缩失败，请重试',
                '文件解压': '解压失败，文件可能已损坏' if not has_password else '解压失败，密码错误或文件损坏',
                '压缩包解密': '密码错误，请重新输入',
                'pdf加密': '加密失败，请检查文件是否已加密或损坏',
                'pdf解密': '密码错误，请重新输入',
                'word转pdf': 'Word 转 PDF 失败，请检查文件格式',
                'pdf转word': 'PDF 转 Word 失败，请检查文件是否受保护',
                '图片转pdf': '图片转 PDF 失败，请检查图片格式',
                'pdf转图片': 'PDF 转图片失败，请检查文件是否损坏',
                'csv转excel': 'CSV 转 Excel 失败，请检查文件编码',
                'excel转csv': 'Excel 转 CSV 失败，请检查文件格式',
                'PDF OCR识别': 'OCR 识别失败，请检查 PDF 是否可读',
                '图片OCR识别': 'OCR 识别失败，请检查图片清晰度',
                '图片转ppt': '图片转 PPT 失败，请检查图片格式',
                'pdf合并': 'PDF 合并失败，请检查文件是否损坏或加密',
                'md转pdf': 'Markdown 转 PDF 失败，请检查文件格式',
                'excel转pdf': 'Excel 转 PDF 失败，请检查文件格式',
                'ppt转pdf': 'PPT 转 PDF 失败，请检查文件格式',
                'html转pdf': 'HTML 转 PDF 失败，请检查文件格式',
                'pdf转ppt': 'PDF 转 PPT 失败，请检查文件是否损坏',
                'ppt转word': 'PPT 转 Word 失败，请检查文件格式',
                'pdf转html': 'PDF 转 HTML 失败，请检查文件是否损坏',
                'md转html': 'Markdown 转 HTML 失败，请检查文件格式',
                '图片格式互转': '图片格式转换失败，请检查图片是否损坏',
                'pdf压缩': 'PDF 压缩失败，请检查文件是否损坏',
                'pdf分割': 'PDF 分割失败，请检查页码范围是否正确',
                'pdf转excel': 'PDF 转 Excel 失败，文件中可能没有可提取的表格',
                '图片压缩': '图片压缩失败，请检查图片是否损坏',
                '文字转语音': '文字转语音失败，请检查文本内容或网络连接',
            }
            return jsonify({'success': False, 'message': error_msgs.get(mode, '转换失败，请检查文件格式或联系管理员')})

    except Exception as e:
        # 记录异常日志（详细信息写入服务端日志，前端只返回通用错误）
        mode_safe = request.form.get('mode', '未知')
        logger.error("转换异常 | user=%s mode=%s err=%s exc=%s", _uname, mode_safe, e, type(e).__name__)
        DatabaseManager.log_conversion(
            _uname, mode_safe, '', False,
            f'系统异常: {type(e).__name__}',  # 只记录异常类型，不记录详细信息
            ip_address=_client_ip
        )
        return jsonify({'success': False, 'message': '服务器处理出错，请稍后重试或联系管理员'})


@converter_bp.route('/download/<path:filename>')
def download(filename):
    """下载转换后的文件（支持子路径，如 taskid_解压文件/sub/file.txt）

    安全：
    1. 必须登录或游客（会话已种）；
    2. 路径严格收敛在 OUTPUT_FOLDER 内（send_from_directory + commonpath 防穿越/兄弟目录误放行）；
    3. task_id 归属校验——只能下载本会话产生的转换结果，防 IDOR 越权。
    """
    if 'username' not in session and not session.get('is_guest'):
        return redirect(url_for('auth.login'))

    # 1) 路径严格收敛，禁止 ../ 穿越与兄弟目录（如 outputs_bak）误放行
    output_folder = os.path.abspath(Config.OUTPUT_FOLDER)
    target = os.path.abspath(os.path.join(output_folder, filename))
    try:
        if os.path.commonpath([output_folder, target]) != output_folder:
            return jsonify({'success': False, 'message': '无效的文件路径'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': '无效的文件路径'}), 400

    if not os.path.exists(target):
        return jsonify({'success': False, 'message': '文件不存在或已过期'}), 404

    # 2) task_id 归属校验：防 IDOR 越权下载
    top_name = filename.split('/', 1)[0]
    task_id = top_name.split('_', 1)[0] if '_' in top_name else top_name
    owned = session.get('owned_tasks') or []

    if task_id in owned:
        # 本会话产生（刚转换完），直接放行
        pass
    elif 'username' in session:
        # 登录用户：以数据库为准，校验该输出文件确属当前用户。
        # 历史记录里的文件由数据库持久化，session 的 owned_tasks 只保留最近 50 个
        # 且重新登录后即清空，因此必须回查数据库避免误判正常用户为越权。
        username = session['username']
        if not DatabaseManager.is_output_owned_by_user(username, target):
            client_ip = get_client_ip() or request.remote_addr or ''
            logger.warning("下载越权被拒绝 | user=%s task_id=%s ip=%s file=%s",
                           username, task_id, client_ip, filename)
            return jsonify({'success': False, 'message': '无权访问该文件'}), 403
    else:
        # 游客且非本会话产生，拒绝下载
        client_ip = get_client_ip() or request.remote_addr or ''
        logger.warning("下载越权被拒绝 | user=guest task_id=%s ip=%s file=%s",
                       task_id, client_ip, filename)
        return jsonify({'success': False, 'message': '无权访问该文件'}), 403

    # 用 name 参数作为下载显示的文件名（去掉哈希前缀）
    display_name = request.args.get('name') or os.path.basename(filename)
    return send_file(target, as_attachment=True, download_name=display_name)


@converter_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    """联系作者页面"""
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    username = session['username']

    if request.method == 'POST':
        # 频率限制：同一 IP 60 秒内最多提交 3 条留言，防止刷屏
        allowed, _remaining = check_rate_limit(
            'contact:' + (get_client_ip() or 'unknown'),
            max_requests=3,
            window_seconds=60
        )
        if not allowed:
            return jsonify({'success': False, 'message': '提交过于频繁，请稍后再试'})

        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not subject or not message:
            return jsonify({'success': False, 'message': '请填写主题和内容'})
        if len(subject) > 100:
            return jsonify({'success': False, 'message': '主题不能超过 100 个字符'})
        if len(message) > 2000:
            return jsonify({'success': False, 'message': '内容不能超过 2000 个字符'})

        success, msg = DatabaseManager.submit_contact_message(
            subject=subject,
            message=message,
            username=username,
            name=session.get('username', ''),
            email=''
        )
        if success:
            logger.info("联系消息已提交 | user=%s subject=%s", username, subject)
        return jsonify({'success': success, 'message': msg})

    session['contact_visit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    success, my_messages, total = DatabaseManager.get_messages_by_username(username)
    if not success:
        my_messages = []
        total = 0

    return render_template('contact.html', my_messages=my_messages, total=total)


@converter_bp.route('/contact/reply', methods=['POST'])
def contact_reply():
    """用户回复管理员的回复"""
    if 'username' not in session:
        return jsonify({'success': False, 'message': '请先登录'})

    username = session['username']
    msg_id = request.form.get('id', type=int)
    reply_text = request.form.get('reply', '').strip()

    # 频率限制：同一 IP 30 秒内最多回复 5 次
    allowed, _remaining = check_rate_limit(
        'contact_reply:' + (get_client_ip() or 'unknown'),
        max_requests=5,
        window_seconds=30
    )
    if not allowed:
        return jsonify({'success': False, 'message': '操作过于频繁，请稍后再试'})

    if not msg_id or not reply_text:
        return jsonify({'success': False, 'message': '缺少必要参数'})
    if len(reply_text) > 1000:
        return jsonify({'success': False, 'message': '回复内容不能超过 1000 个字符'})

    # 验证该消息属于当前用户
    conn = DatabaseManager.get_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM contact_messages WHERE id = %s AND username = %s",
            (msg_id, username)
        )
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': '无权操作该消息'})
    except Exception as e:
        logger.error("验证消息权限失败 | msg_id=%s user=%s err=%s", msg_id, username, e)
        return jsonify({'success': False, 'message': '操作失败，请稍后重试'})
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            DatabaseManager.return_connection(conn)

    success, msg = DatabaseManager.add_contact_reply(msg_id, reply_text, 'user')
    if success:
        logger.info("用户回复消息 | user=%s msg_id=%s", username, msg_id)
    return jsonify({'success': success, 'message': msg})


@converter_bp.route('/api/user_unread_replies')
def user_unread_replies():
    """获取用户未读回复数"""
    if 'username' not in session:
        return jsonify({'count': 0})

    username = session['username']
    visit_time = session.get('contact_visit_time')

    count = DatabaseManager.get_unread_reply_count(username, visit_time)
    return jsonify({'count': count})


@converter_bp.route('/dashboard')
def dashboard():
    """用户仪表盘页面"""
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    username = session['username']

    # 获取统计数据
    stats_success, stats, by_mode = DatabaseManager.get_user_dashboard_stats(username)
    trend_success, trend = DatabaseManager.get_conversion_trend(days=7, username=username)
    all_modes = DatabaseManager.get_all_modes()

    # 获取用户信息
    user = DatabaseManager.get_user_by_username(username)

    return render_template(
        'dashboard.html',
        user=user,
        stats=stats if stats_success else {'total': 0, 'success_count': 0, 'fail_count': 0},
        by_mode=by_mode if stats_success else [],
        trend=trend if trend_success else [],
        all_modes=all_modes
    )


@converter_bp.route('/api/dashboard_stats')
def api_dashboard_stats():
    """API: 获取用户仪表盘统计数据（支持模式筛选）"""
    if 'username' not in session:
        return jsonify({'success': False, 'message': '请先登录'})

    username = session['username']
    mode_filter = request.args.get('mode', '').strip() or None
    days = request.args.get('days', 7, type=int)

    stats_success, stats, by_mode = DatabaseManager.get_user_dashboard_stats(
        username, mode_filter=mode_filter
    )
    trend_success, trend = DatabaseManager.get_conversion_trend(
        days=days, username=username
    )

    return jsonify({
        'success': stats_success and trend_success,
        'stats': stats,
        'by_mode': by_mode,
        'trend': trend
    })


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
