import smtplib
from email.mime.text import MIMEText
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


def send_verify_code(to_email: str, code: str) -> bool:
    """
    同步发送邮箱验证码，返回 True/False 表示实际发送结果。
    """
    if not Config.MAIL_USER or not Config.MAIL_PASSWORD:
        logger.warning("未配置 SMTP，跳过发送")
        return False

    try:
        msg = MIMEText(
            f'<div style="max-width:480px;margin:0 auto;font-family:Arial,sans-serif;">'
            f'<h2 style="color:#667eea;">文件转换工具 · 验证码</h2>'
            f'<p>您的验证码是：</p>'
            f'<div style="background:#f0f4ff;padding:16px;border-radius:8px;text-align:center;'
            f'font-size:28px;font-weight:700;letter-spacing:6px;color:#4f46e5;">{code}</div>'
            f'<p style="color:#9ca3af;font-size:13px;margin-top:12px;">验证码 5 分钟内有效，请勿泄露。</p>'
            f'</div>',
            'html', 'utf-8'
        )
        msg['From'] = Config.MAIL_USER
        msg['To'] = to_email
        msg['Subject'] = f'验证码 {code} - 文件转换工具'

        if Config.MAIL_USE_SSL:
            server = smtplib.SMTP_SSL(Config.MAIL_HOST, Config.MAIL_PORT, timeout=10)
        else:
            server = smtplib.SMTP(Config.MAIL_HOST, Config.MAIL_PORT, timeout=10)
            server.starttls()

        server.login(Config.MAIL_USER, Config.MAIL_PASSWORD)
        server.sendmail(Config.MAIL_USER, [to_email], msg.as_string())
        server.quit()
        logger.info("验证码已发送至 %s", to_email)
        return True
    except Exception as e:
        logger.error("邮件发送失败: %s", e)
        return False
