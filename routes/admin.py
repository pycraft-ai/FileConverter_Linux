from flask import Blueprint, render_template, request, jsonify, session, redirect, \
    url_for, flash
from database.db_manager import DatabaseManager
from utils.logger import get_logger
from config import Config

admin_bp = Blueprint('admin', __name__)
logger = get_logger(__name__)


@admin_bp.route('/admin')
def admin_panel():
    if 'username' not in session or not session.get('is_admin'):
        flash('管理员权限不足', 'error')
        return redirect(url_for('converter.index'))

    # 获取仪表盘统计
    stats_success, stats = DatabaseManager.get_admin_dashboard_stats()
    trend_success, trend = DatabaseManager.get_conversion_trend(days=7)
    storage = DatabaseManager.get_storage_stats()

    # 获取用户列表
    success, users = DatabaseManager.get_all_users()
    if success:
        for user in users:
            if user.get('expiration_date'):
                user['expiration_date'] = str(user['expiration_date'])

    return render_template(
        'admin.html',
        users=users if success else [],
        stats=stats if stats_success else None,
        trend=trend if trend_success else [],
        storage=storage
    )


@admin_bp.route('/admin/dashboard')
def admin_dashboard():
    """管理员仪表盘页面（全屏图表视图）"""
    if 'username' not in session or not session.get('is_admin'):
        flash('管理员权限不足', 'error')
        return redirect(url_for('converter.index'))

    stats_success, stats = DatabaseManager.get_admin_dashboard_stats()
    trend_success, trend = DatabaseManager.get_conversion_trend(days=7)
    modes = DatabaseManager.get_all_modes()

    return render_template(
        'admin_dashboard.html',
        stats=stats if stats_success else None,
        trend=trend if trend_success else [],
        all_modes=modes
    )


@admin_bp.route('/admin/api/dashboard_stats')
def api_dashboard_stats():
    """API: 获取仪表盘统计数据"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})

    days = request.args.get('days', 7, type=int)
    stats_success, stats = DatabaseManager.get_admin_dashboard_stats()
    trend_success, trend = DatabaseManager.get_conversion_trend(days=days)

    return jsonify({
        'success': stats_success and trend_success,
        'stats': stats,
        'trend': trend
    })


@admin_bp.route('/admin/api/storage_stats')
def api_storage_stats():
    """API: 获取存储空间统计"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})

    storage = DatabaseManager.get_storage_stats()
    return jsonify({'success': True, 'storage': storage})


@admin_bp.route('/admin/block', methods=['POST'])
def block_user():
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})

    username = request.form.get('username', '').strip()
    if not username:
        return jsonify({'success': False, 'message': '请输入用户名'})
    if username == 'admin':
        return jsonify({'success': False, 'message': '管理员账号无法被封禁'})

    success, msg = DatabaseManager.block_user(username)
    if success:
        logger.warning("管理员操作: 封禁/解封用户 | admin=%s target=%s", session['username'], username)
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/renew', methods=['POST'])
def renew_user():
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})

    username = request.form.get('username', '').strip()
    try:
        days = int(request.form.get('days', 30))
        if days <= 0:
            return jsonify({'success': False, 'message': '天数必须大于0'})
    except ValueError:
        return jsonify({'success': False, 'message': '请输入有效的天数'})

    if not username:
        return jsonify({'success': False, 'message': '请输入用户名'})

    success, msg = DatabaseManager.update_user_expiration(username, days)
    if success:
        logger.info("管理员操作: 续期用户 | admin=%s target=%s days=%s", session['username'], username, days)
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/increase_times', methods=['POST'])
def increase_times():
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})

    username = request.form.get('username', '').strip()
    try:
        times = int(request.form.get('times', 10))
        if times <= 0:
            return jsonify({'success': False, 'message': '次数必须大于0'})
    except ValueError:
        return jsonify({'success': False, 'message': '请输入有效的次数'})

    if not username:
        return jsonify({'success': False, 'message': '请输入用户名'})

    success, msg = DatabaseManager.increase_user_times(username, times)
    if success:
        logger.info("管理员操作: 增加次数 | admin=%s target=%s times=%s", session['username'], username, times)
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/logs')
def view_logs():
    """查看操作日志"""
    if 'username' not in session or not session.get('is_admin'):
        flash('管理员权限不足', 'error')
        return redirect(url_for('converter.index'))

    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    username_filter = request.args.get('username', '')
    
    offset = (page - 1) * per_page
    
    # 获取日志总数
    if username_filter:
        _, total_count = DatabaseManager.get_log_count(username_filter)
    else:
        _, total_count = DatabaseManager.get_log_count()
    
    total_pages = (total_count + per_page - 1) // per_page
    
    # 获取日志列表
    success, logs = DatabaseManager.get_conversion_logs(
        username=username_filter if username_filter else None,
        limit=per_page,
        offset=offset
    )
    
    if success:
        # 处理 datetime 对象为字符串
        for log in logs:
            if log.get('operation_time'):
                log['operation_time'] = str(log['operation_time'])
        
        return render_template(
            'logs.html',
            logs=logs,
            page=page,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            username_filter=username_filter
        )
    else:
        flash('获取日志失败', 'error')
        return render_template('logs.html', logs=[], page=1, per_page=50, total_count=0, total_pages=0, username_filter='')


@admin_bp.route('/admin/announcements')
def manage_announcements():
    """管理公告"""
    if 'username' not in session or not session.get('is_admin'):
        flash('管理员权限不足', 'error')
        return redirect(url_for('converter.index'))
    
    success, announcements = DatabaseManager.get_all_announcements()
    if not success:
        flash('获取公告列表失败', 'error')
        announcements = []
    
    return render_template('announcements_manage.html', announcements=announcements)


@admin_bp.route('/admin/announcement/create', methods=['POST'])
def create_announcement():
    """创建公告"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    announce_type = request.form.get('type', 'info')
    
    try:
        priority = int(request.form.get('priority', 0))
    except ValueError:
        priority = 0
    
    if not title or not content:
        return jsonify({'success': False, 'message': '标题和内容不能为空'})
    
    success, msg = DatabaseManager.create_announcement(
        title=title,
        content=content,
        announce_type=announce_type,
        priority=priority,
        created_by=session['username']
    )
    
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/announcement/toggle', methods=['POST'])
def toggle_announcement():
    """切换公告状态"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    try:
        announce_id = int(request.form.get('id', 0))
    except ValueError:
        return jsonify({'success': False, 'message': '无效的公告ID'})
    
    success, msg = DatabaseManager.toggle_announcement(announce_id)
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/announcement/delete', methods=['POST'])
def delete_announcement():
    """删除公告"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    try:
        announce_id = int(request.form.get('id', 0))
    except ValueError:
        return jsonify({'success': False, 'message': '无效的公告ID'})
    
    success, msg = DatabaseManager.delete_announcement(announce_id)
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/ip_analysis')
def ip_analysis():
    """IP访问分析页面"""
    if 'username' not in session or not session.get('is_admin'):
        flash('管理员权限不足', 'error')
        return redirect(url_for('converter.index'))
    
    # 获取时间范围参数
    hours = request.args.get('hours', Config.IP_ANALYSIS_DEFAULT_HOURS, type=int)
    
    # 获取统计数据
    success, data = DatabaseManager.get_ip_statistics(hours)
    
    # 获取时间线数据
    timeline_success, timeline_data = DatabaseManager.get_ip_access_timeline(hours)
    
    if success:
        return render_template(
            'ip_analysis.html',
            stats=data['stats'],
            top_ips=data['top_ips'],
            blocked_ips=data['blocked_ips'],
            timeline_data=timeline_data if timeline_success else [],
            hours=hours
        )
    else:
        flash('获取IP统计数据失败', 'error')
        return render_template('ip_analysis.html', stats=None, top_ips=[], blocked_ips=[], timeline_data=[], hours=hours)


@admin_bp.route('/admin/block_ip', methods=['POST'])
def block_ip():
    """封禁IP"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    ip_address = request.form.get('ip_address', '').strip()
    reason = request.form.get('reason', '').strip()
    expire_days = request.form.get('expire_days', '')
    
    if not ip_address:
        return jsonify({'success': False, 'message': '请输入IP地址'})
    
    try:
        expire_days = int(expire_days) if expire_days else None
        if expire_days and expire_days <= 0:
            return jsonify({'success': False, 'message': '天数必须大于0'})
    except ValueError:
        return jsonify({'success': False, 'message': '请输入有效的天数'})
    
    success, msg = DatabaseManager.block_ip(
        ip_address=ip_address,
        reason=reason,
        blocked_by=session['username'],
        expire_days=expire_days
    )
    if success:
        logger.warning("管理员操作: 封禁IP | admin=%s ip=%s reason=%s expire=%s", session['username'], ip_address, reason, expire_days)
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/unblock_ip', methods=['POST'])
def unblock_ip():
    """解封IP"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    ip_address = request.form.get('ip_address', '').strip()
    
    if not ip_address:
        return jsonify({'success': False, 'message': '请输入IP地址'})
    
    success, msg = DatabaseManager.unblock_ip(ip_address)
    if success:
        logger.info("管理员操作: 解封IP | admin=%s ip=%s", session['username'], ip_address)
    return jsonify({'success': success, 'message': msg})


@admin_bp.route('/admin/api/ip_map_data')
def api_ip_map_data():
    """API: 获取IP地图数据"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    hours = request.args.get('hours', Config.IP_ANALYSIS_DEFAULT_HOURS, type=int)
    
    # 获取已有地理位置的IP列表（不再自动获取位置，避免卡顿）
    success, ip_list = DatabaseManager.get_ip_map_data(hours)
    
    if not success:
        return jsonify({'success': False, 'message': ip_list})
    
    return jsonify({'success': True, 'data': ip_list})


@admin_bp.route('/admin/api/refresh_ip_locations', methods=['POST'])
def refresh_ip_locations():
    """API: 手动刷新IP地理位置（批量处理）"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    hours = request.form.get('hours', 24, type=int)
    limit = request.form.get('limit', 10, type=int)  # 每次最多处理10个IP，避免卡顿
    
    conn = None
    cursor = None
    try:
        # 获取没有位置信息的IP列表
        conn = DatabaseManager.get_connection()
        if not conn:
            return jsonify({'success': False, 'message': '数据库连接失败'})
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT DISTINCT ip_address FROM ip_access_logs 
            WHERE access_time >= DATE_SUB(NOW(), INTERVAL %s HOUR)
              AND (country IS NULL OR country = '' OR country = '未知')
            LIMIT %s""",
            (hours, limit)
        )
        ips_to_process = cursor.fetchall()
        
        if not ips_to_process:
            return jsonify({'success': True, 'message': '没有需要处理的IP', 'processed': 0})
        
        # 逐个处理（带请求间隔，避免API限流）
        import time
        processed = 0
        failed = 0
        for ip_record in ips_to_process:
            ip_address = ip_record['ip_address']
            location = DatabaseManager.get_ip_location(ip_address)
            if location:
                DatabaseManager.update_ip_location(
                    ip_address,
                    location['country'],
                    location['city'],
                    location['latitude'],
                    location['longitude']
                )
                processed += 1
            else:
                failed += 1
            time.sleep(Config.IP_LOCATION_REQUEST_INTERVAL)  # 请求间隔，避免API限流
        
        return jsonify({
            'success': True, 
            'message': f'处理完成：成功{processed}个，失败{failed}个',
            'processed': processed,
            'failed': failed
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'处理失败: {str(e)}'})
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            DatabaseManager.return_connection(conn)


@admin_bp.route('/admin/api/test_ip_location', methods=['POST'])
def api_test_ip_location():
    """API: 测试指定IP的地理位置"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    ip_address = request.form.get('ip', '').strip()
    if not ip_address:
        return jsonify({'success': False, 'message': '请输入IP地址'})
    
    location = DatabaseManager.get_ip_location(ip_address)
    if location:
        return jsonify({'success': True, 'data': {
            'ip_address': ip_address,
            'country': location['country'],
            'city': location['city'],
            'latitude': location['latitude'],
            'longitude': location['longitude']
        }})
    else:
        return jsonify({'success': False, 'message': f'无法获取 {ip_address} 的位置信息'})


@admin_bp.route('/admin/contacts')
def manage_contacts():
    """管理联系消息"""
    if 'username' not in session or not session.get('is_admin'):
        flash('管理员权限不足', 'error')
        return redirect(url_for('converter.index'))
    
    page = request.args.get('page', 1, type=int)
    
    success, messages, total = DatabaseManager.get_contact_messages(page=page, per_page=20)
    if not success:
        messages = []
        total = 0
    
    total_pages = (total + 19) // 20
    
    return render_template(
        'contacts_manage.html',
        messages=messages,
        page=page,
        total_pages=total_pages,
        total=total
    )


@admin_bp.route('/admin/contact/mark_read', methods=['POST'])
def mark_contact_read():
    """标记消息已读"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    msg_id = request.form.get('id', type=int)
    if msg_id:
        DatabaseManager.mark_message_read(msg_id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '无效的ID'})


@admin_bp.route('/admin/unread_count')
def unread_count():
    """获取未读消息数量（用于导航栏徽章）"""
    count = DatabaseManager.get_unread_contact_count()
    return jsonify({'count': count})


@admin_bp.route('/admin/contact/reply', methods=['POST'])
def reply_contact():
    """回复联系消息（支持多次回复）"""
    if 'username' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': '权限不足'})
    
    msg_id = request.form.get('id', type=int)
    reply_text = request.form.get('reply', '').strip()
    
    if not msg_id or not reply_text:
        return jsonify({'success': False, 'message': '缺少必要参数'})
    
    success, msg = DatabaseManager.add_contact_reply(msg_id, reply_text, 'admin')
    if success:
        logger.info("管理员回复消息 | admin=%s msg_id=%s", session['username'], msg_id)
    return jsonify({'success': success, 'message': msg})
