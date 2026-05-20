"""
mail_notify.py
SMTP メール送信ヘルパー

環境変数（.env に追加）:
  MAIL_SMTP_HOST     : SMTPサーバーホスト（例: smtp.xserver.jp）
  MAIL_SMTP_PORT     : ポート番号（587=STARTTLS, 465=SSL/TLS　デフォルト587）
  MAIL_SMTP_USER     : SMTPユーザー（送信元アドレス, 例: noreply@cardanoism.com）
  MAIL_SMTP_PASSWORD : SMTPパスワード
  MAIL_FROM_NAME     : 送信者表示名（デフォルト: Cardanoism）
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formatdate, make_msgid, formataddr

logger = logging.getLogger(__name__)

SMTP_HOST      = os.getenv("MAIL_SMTP_HOST", "")
SMTP_PORT      = int(os.getenv("MAIL_SMTP_PORT", "587"))
SMTP_USER      = os.getenv("MAIL_SMTP_USER", "")
SMTP_PASSWORD  = os.getenv("MAIL_SMTP_PASSWORD", "")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Cardanoism")
_BASE_URL      = os.getenv("CARDANOISM_URL", "https://cardanoism.com")


def send_email(to: str, subject: str, html: str, text: str = "") -> bool:
    """
    SMTPでHTMLメールを送信する。成功時 True。
    SMTP設定が未記入の場合はスキップして False を返す。
    """
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
        logger.warning("メール設定が不完全です (MAIL_SMTP_HOST / MAIL_SMTP_USER / MAIL_SMTP_PASSWORD)")
        return False
    if not to:
        logger.warning("送信先アドレスが空のためスキップ")
        return False

    # 表示名に日本語等の非 ASCII が含まれても formataddr が RFC 2047 で
    # 適切にエンコードする (charset デフォルト utf-8)。
    mail_from = formataddr((MAIL_FROM_NAME, SMTP_USER))

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8").encode()
        msg["From"]    = mail_from
        msg["To"]      = to
        # RFC 5322 必須ヘッダ + 配信レピュテーション対策。
        # Gmail / Outlook は Date / Message-ID 不在のメールを silent drop することがある。
        msg["Date"]       = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="cardanoism.com")

        if text:
            msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as srv:
                srv.login(SMTP_USER, SMTP_PASSWORD)
                srv.sendmail(SMTP_USER, [to], msg.as_bytes())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as srv:
                srv.ehlo()
                srv.starttls()
                srv.ehlo()
                srv.login(SMTP_USER, SMTP_PASSWORD)
                srv.sendmail(SMTP_USER, [to], msg.as_bytes())

        logger.info("メール送信成功 to=%s subject=%s", to, subject[:60])
        return True

    except Exception as e:
        logger.error("メール送信失敗 to=%s: %s", to, e)
        return False


# ============================================================
# HTML / テキスト テンプレートビルダー
# ============================================================

def build_html(subject: str, lines: list[str], cta_url: str = "", cta_label: str = "詳細を見る", lang: str = "ja") -> str:
    """
    シンプルなHTMLメールを生成する。
    lines: 本文として表示する文字列のリスト。
    """
    lines_html = "".join(
        f"<p style='margin:6px 0;color:#333;font-size:15px;line-height:1.7;'>{l}</p>"
        for l in lines
    )

    cta_block = ""
    if cta_url:
        cta_block = f"""
        <div style="margin:24px 0 8px;">
          <a href="{cta_url}"
             style="display:inline-block;background:#ffcf00;color:#111;text-decoration:none;
                    padding:10px 28px;border-radius:6px;font-weight:bold;font-size:14px;">
            {cta_label}
          </a>
        </div>"""

    if lang == "ja":
        footer1 = "このメールは Cardanoism の通知設定に基づいて送信されています。"
        footer2 = "通知設定の変更は"
        footer3 = "から行えます。"
    else:
        footer1 = "This email was sent based on your Cardanoism notification settings."
        footer2 = "Manage settings at"
        footer3 = ""

    settings_url = f"{_BASE_URL}/mypage?tab=notification"

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:'Helvetica Neue',Arial,'Noto Sans JP',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0"
             style="max-width:580px;width:100%;background:#fff;border-radius:10px;
                    overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.08);">
        <!-- ヘッダー -->
        <tr>
          <td style="background:#111;padding:18px 28px;">
            <span style="color:#ffcf00;font-size:18px;font-weight:bold;letter-spacing:0.5px;">
              Cardanoism
            </span>
          </td>
        </tr>
        <!-- 本文 -->
        <tr>
          <td style="padding:28px 28px 20px;">
            <h2 style="margin:0 0 16px;font-size:17px;color:#111;line-height:1.4;">{subject}</h2>
            {lines_html}
            {cta_block}
          </td>
        </tr>
        <!-- フッター -->
        <tr>
          <td style="background:#f9f9f9;padding:16px 28px;border-top:1px solid #eee;">
            <p style="margin:0 0 4px;font-size:12px;color:#999;">{footer1}</p>
            <p style="margin:0;font-size:12px;color:#999;">
              {footer2}
              <a href="{settings_url}" style="color:#999;text-decoration:underline;">{settings_url}</a>
              {footer3}
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_text(subject: str, lines: list[str], cta_url: str = "", lang: str = "ja") -> str:
    """プレーンテキストメールを生成する。"""
    parts = [subject, "=" * min(len(subject), 60), ""]
    parts.extend(lines)
    if cta_url:
        parts += ["", cta_url]
    settings_url = f"{_BASE_URL}/mypage?tab=notification"
    sep = "通知設定: " if lang == "ja" else "Notification settings: "
    parts += ["", "---", f"Cardanoism  {sep}{settings_url}"]
    return "\n".join(parts)
