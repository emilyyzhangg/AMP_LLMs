"""
Email notifications for annotation job completion.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# Email Configuration
# =============================================================================

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_FROM = os.getenv("SMTP_FROM", "Luke@amphoraxe.ca")
SMTP_PASS = os.getenv("SMTP_PASS", "")

# Public URL for download links
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://llm.amphoraxe.ca")


def is_email_configured() -> bool:
    """Check if email is properly configured."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


def send_email(to: str, subject: str, body_html: str, body_text: Optional[str] = None) -> bool:
    """
    Send an email. Returns True if successful, False otherwise.
    Fails silently if email is not configured.
    """
    if not is_email_configured():
        logger.warning(f"[EMAIL] Not configured. Would send to {to}: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to

        # Plain text fallback
        if body_text:
            msg.attach(MIMEText(body_text, "plain"))

        # HTML body
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to, msg.as_string())

        logger.info(f"[EMAIL] Sent to {to}: {subject}")
        return True

    except Exception as e:
        logger.error(f"[EMAIL] Failed to send to {to}: {e}")
        return False


def send_annotation_complete_email(
    to_email: str,
    job_id: str,
    original_filename: str,
    total_trials: int,
    successful: int,
    failed: int,
    processing_time_seconds: float,
    model: str
) -> bool:
    """
    Send notification email when annotation job completes.

    Args:
        to_email: Recipient email address
        job_id: The job ID for download link
        original_filename: Original uploaded CSV filename
        total_trials: Total number of trials processed
        successful: Number of successful annotations
        failed: Number of failed annotations
        processing_time_seconds: Total processing time
        model: LLM model used

    Returns:
        True if email sent successfully, False otherwise
    """
    download_url = f"{PUBLIC_BASE_URL}/chat/download/{job_id}"

    # Format processing time
    if processing_time_seconds >= 60:
        time_str = f"{processing_time_seconds / 60:.1f} minutes"
    else:
        time_str = f"{processing_time_seconds:.1f} seconds"

    # Status indicator
    if failed == 0:
        status_emoji = "✅"
        status_text = "All annotations completed successfully!"
    elif successful > 0:
        status_emoji = "⚠️"
        status_text = f"Completed with {failed} error(s)"
    else:
        status_emoji = "❌"
        status_text = "Annotation failed"

    subject = f"{status_emoji} Annotation Complete: {original_filename}"

    body_html = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <h2 style="color: #1BEB49; margin-top: 0;">
                {status_emoji} Annotation Complete
            </h2>

            <p>Your clinical trial annotation job has finished processing.</p>

            <table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Input File</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>{original_filename}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Total Trials</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>{total_trials}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Successful</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong style="color: #16a34a;">{successful}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Failed</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong style="color: {'#dc2626' if failed > 0 else '#666'};">{failed}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Processing Time</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>{time_str}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Model</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>{model}</strong></td>
                </tr>
            </table>

            <p style="margin-top: 25px;">
                <a href="{download_url}"
                   style="display: inline-block; padding: 14px 28px; background: #1BEB49; color: #000; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    📥 Download Results
                </a>
            </p>

            <p style="color: #888; font-size: 13px; margin-top: 30px;">
                This download link will expire in 3 hours.<br>
                Job ID: {job_id}
            </p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

            <p style="color: #888; font-size: 12px;">
                — AMP LLM Annotation Service<br>
                <a href="{PUBLIC_BASE_URL}" style="color: #1BEB49;">llm.amphoraxe.ca</a>
            </p>
        </div>
    </body>
    </html>
    """

    body_text = f"""
Annotation Complete
==================

{status_text}

Input File: {original_filename}
Total Trials: {total_trials}
Successful: {successful}
Failed: {failed}
Processing Time: {time_str}
Model: {model}

Download your results:
{download_url}

This download link will expire in 3 hours.
Job ID: {job_id}

— AMP LLM Annotation Service
"""

    return send_email(to_email, subject, body_html, body_text)


def send_annotation_failed_email(
    to_email: str,
    job_id: str,
    original_filename: str,
    error_message: str
) -> bool:
    """
    Send notification email when annotation job fails.
    """
    subject = f"❌ Annotation Failed: {original_filename}"

    body_html = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <h2 style="color: #dc2626; margin-top: 0;">
                ❌ Annotation Failed
            </h2>

            <p>Unfortunately, your annotation job encountered an error.</p>

            <table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Input File</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>{original_filename}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; color: #666;">Job ID</td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee;"><code>{job_id}</code></td>
                </tr>
            </table>

            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 15px; margin: 20px 0;">
                <strong style="color: #dc2626;">Error:</strong>
                <p style="margin: 10px 0 0 0; color: #7f1d1d;">{error_message}</p>
            </div>

            <p>Please try again or contact support if the issue persists.</p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

            <p style="color: #888; font-size: 12px;">
                — AMP LLM Annotation Service<br>
                <a href="{PUBLIC_BASE_URL}" style="color: #1BEB49;">llm.amphoraxe.ca</a>
            </p>
        </div>
    </body>
    </html>
    """

    body_text = f"""
Annotation Failed
=================

Unfortunately, your annotation job encountered an error.

Input File: {original_filename}
Job ID: {job_id}

Error: {error_message}

Please try again or contact support if the issue persists.

— AMP LLM Annotation Service
"""

    return send_email(to_email, subject, body_html, body_text)
