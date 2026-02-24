"""Email notification service using Resend.com API.

Sends HTML emails on job completion/failure. Silently skips if
RESEND_API_KEY is not configured — email should never crash a task.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _job_link(job_id: str) -> str:
    return f"{settings.app_base_url}/jobs/{job_id}"


def _csv_link(job_id: str) -> str:
    return f"{settings.api_base_url}/api/results/{job_id}/export?template=clay"


def _html_header(title: str) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
      <div style="border-bottom: 3px solid #4f46e5; padding-bottom: 12px; margin-bottom: 24px;">
        <h1 style="color: #1f2937; margin: 0; font-size: 20px;">GMaps Scraper</h1>
      </div>
      <h2 style="color: #1f2937; font-size: 18px; margin-bottom: 16px;">{title}</h2>
    """


def _html_footer() -> str:
    return """
      <div style="margin-top: 32px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 12px;">
        <p>Sent by GMaps Scraper. This is an automated notification.</p>
      </div>
    </div>
    """


def _layer_badge(status: str) -> str:
    colors = {
        "completed": "#059669",
        "running": "#2563eb",
        "failed": "#dc2626",
        "idle": "#9ca3af",
    }
    color = colors.get(status, "#9ca3af")
    return f'<span style="display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; color: white; background-color: {color};">{status}</span>'


async def send_job_completion_email(to_email: str, job_data: dict) -> None:
    """Send an email when a job completes successfully."""
    if not settings.resend_api_key:
        logger.debug("Resend API key not set — skipping email to %s", to_email)
        return

    job_id = job_data.get("job_id", "")
    keyword = job_data.get("keyword", "")
    location = job_data.get("location", "")
    total_found = job_data.get("total_found", 0)
    total_unique = job_data.get("total_unique", 0)
    layer1 = job_data.get("layer1_status", "idle")
    layer2 = job_data.get("layer2_status", "idle")
    layer3 = job_data.get("layer3_status", "idle")
    time_taken = job_data.get("time_taken", "N/A")

    html = _html_header(f"Job Completed: {keyword} in {location}")
    html += f"""
      <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
        <p style="color: #166534; margin: 0; font-weight: 600;">Your scraping job has finished successfully!</p>
      </div>
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Keyword</td><td style="padding: 8px 0; font-weight: 600;">{keyword}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Location</td><td style="padding: 8px 0; font-weight: 600;">{location}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Total Found</td><td style="padding: 8px 0; font-weight: 600;">{total_found}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Unique Leads</td><td style="padding: 8px 0; font-weight: 600;">{total_unique}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Time Taken</td><td style="padding: 8px 0; font-weight: 600;">{time_taken}</td></tr>
      </table>
      <div style="margin-bottom: 20px;">
        <p style="color: #6b7280; font-size: 14px; margin-bottom: 8px;">Layer Status:</p>
        <p>Layer 1 (Playwright): {_layer_badge(layer1)} &nbsp; Layer 2 (SerpAPI): {_layer_badge(layer2)} &nbsp; Layer 3 (Outscraper): {_layer_badge(layer3)}</p>
      </div>
      <div style="margin-bottom: 12px;">
        <a href="{_job_link(job_id)}" style="display: inline-block; padding: 10px 20px; background-color: #4f46e5; color: white; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 14px;">View Results</a>
        <a href="{_csv_link(job_id)}" style="display: inline-block; padding: 10px 20px; background-color: #f3f4f6; color: #374151; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 14px; margin-left: 8px;">Download CSV</a>
      </div>
    """
    html += _html_footer()

    await _send_email(
        to=to_email,
        subject=f"Scrape Complete: {total_unique} leads for \"{keyword}\" in {location}",
        html=html,
    )


async def send_job_failed_email(to_email: str, job_data: dict, error_message: str) -> None:
    """Send an email when a job fails."""
    if not settings.resend_api_key:
        return

    job_id = job_data.get("job_id", "")
    keyword = job_data.get("keyword", "")
    location = job_data.get("location", "")

    html = _html_header(f"Job Failed: {keyword} in {location}")
    html += f"""
      <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
        <p style="color: #991b1b; margin: 0; font-weight: 600;">Your scraping job has failed.</p>
      </div>
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Keyword</td><td style="padding: 8px 0; font-weight: 600;">{keyword}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Location</td><td style="padding: 8px 0; font-weight: 600;">{location}</td></tr>
      </table>
      <div style="background: #fef2f2; border-radius: 6px; padding: 12px; margin-bottom: 20px;">
        <p style="color: #991b1b; font-size: 13px; font-family: monospace; margin: 0; word-break: break-all;">{error_message[:500]}</p>
      </div>
      <p style="color: #6b7280; font-size: 14px;">You can retry the job from the dashboard:</p>
      <a href="{_job_link(job_id)}" style="display: inline-block; padding: 10px 20px; background-color: #4f46e5; color: white; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 14px;">View Job</a>
    """
    html += _html_footer()

    await _send_email(
        to=to_email,
        subject=f"Scrape Failed: \"{keyword}\" in {location}",
        html=html,
    )


async def send_batch_completion_email(to_email: str, batch_summary: dict) -> None:
    """Send a summary email when a batch of jobs completes."""
    if not settings.resend_api_key:
        return

    name = batch_summary.get("name", "Unnamed Batch")
    total = batch_summary.get("total_jobs", 0)
    completed = batch_summary.get("completed_jobs", 0)
    failed = batch_summary.get("failed_jobs", 0)
    total_leads = batch_summary.get("total_leads", 0)
    batch_id = batch_summary.get("batch_id", "")
    time_taken = batch_summary.get("time_taken", "N/A")

    status_color = "#059669" if failed == 0 else "#d97706"
    status_text = "All Completed" if failed == 0 else f"{completed} Completed, {failed} Failed"

    html = _html_header(f"Batch Complete: {name}")
    html += f"""
      <div style="background: {'#f0fdf4' if failed == 0 else '#fffbeb'}; border: 1px solid {'#bbf7d0' if failed == 0 else '#fde68a'}; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
        <p style="color: {status_color}; margin: 0; font-weight: 600;">{status_text}</p>
      </div>
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Batch Name</td><td style="padding: 8px 0; font-weight: 600;">{name}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Total Jobs</td><td style="padding: 8px 0; font-weight: 600;">{total}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Completed</td><td style="padding: 8px 0; font-weight: 600; color: #059669;">{completed}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Failed</td><td style="padding: 8px 0; font-weight: 600; color: {'#dc2626' if failed > 0 else '#6b7280'};">{failed}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Total Leads</td><td style="padding: 8px 0; font-weight: 600;">{total_leads}</td></tr>
        <tr><td style="padding: 8px 0; color: #6b7280; font-size: 14px;">Time Taken</td><td style="padding: 8px 0; font-weight: 600;">{time_taken}</td></tr>
      </table>
      <a href="{settings.app_base_url}/batch/{batch_id}" style="display: inline-block; padding: 10px 20px; background-color: #4f46e5; color: white; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 14px;">View Batch</a>
    """
    html += _html_footer()

    await _send_email(
        to=to_email,
        subject=f"Batch Complete: {completed}/{total} jobs — {total_leads} leads ({name})",
        html=html,
    )


async def _send_email(to: str, subject: str, html: str) -> None:
    """Send an email via Resend.com API."""
    if not settings.resend_api_key:
        return

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.notification_from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )

            if response.status_code in (200, 201):
                logger.info("Email sent to %s: %s", to, subject)
            elif response.status_code == 403:
                error_body = response.text[:300]
                if "verify a domain" in error_body.lower():
                    logger.warning(
                        "Resend domain not verified — cannot send to %s. "
                        "Verify your domain at https://resend.com/domains "
                        "to enable sending to all recipients.",
                        to,
                    )
                else:
                    logger.warning("Resend API 403 for %s: %s", to, error_body)
            else:
                logger.warning(
                    "Resend API error %d: %s",
                    response.status_code,
                    response.text[:200],
                )
    except Exception as e:
        logger.warning("Failed to send email to %s: %s", to, e)
