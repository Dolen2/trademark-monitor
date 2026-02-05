"""
Alert system for trademark monitoring.
Sends notifications via email and Slack when potential conflicts are found.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AlertSystem:
    """
    Handles sending alerts through multiple channels:
    - Email (SMTP)
    - Slack (Webhook)
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the alert system.

        Args:
            config: Alert configuration dictionary
        """
        self.config = config or {}
        self.email_config = self.config.get('email', {})
        self.slack_config = self.config.get('slack', {})

    def send_conflict_alert(self, conflicts: List[Dict[str, Any]],
                           summary: Dict[str, Any] = None) -> Dict[str, bool]:
        """
        Send alerts for detected conflicts.

        Args:
            conflicts: List of conflict dictionaries
            summary: Optional summary of monitoring run

        Returns:
            Dictionary with success status for each channel
        """
        results = {'email': False, 'slack': False}

        if not conflicts:
            logger.info("No conflicts to alert")
            return results

        if self.email_config.get('enabled', False):
            results['email'] = self._send_email_alert(conflicts, summary)

        if self.slack_config.get('enabled', False):
            results['slack'] = self._send_slack_alert(conflicts, summary)

        return results

    # ==================== Email Alerts ====================

    def _send_email_alert(self, conflicts: List[Dict[str, Any]],
                         summary: Dict[str, Any] = None) -> bool:
        """Send email alert for conflicts."""
        try:
            # Build email content
            subject = f"⚠️ Trademark Alert: {len(conflicts)} Potential Conflict(s) Detected"
            html_body = self._build_email_html(conflicts, summary)
            text_body = self._build_email_text(conflicts, summary)

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_config.get('from_address', 'trademark-monitor@relatent.com')
            msg['To'] = ', '.join(self.email_config.get('to_addresses', []))

            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            # Send email
            smtp_server = self.email_config.get('smtp_server', 'smtp.gmail.com')
            smtp_port = self.email_config.get('smtp_port', 587)

            context = ssl.create_default_context()

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls(context=context)

                username = self.email_config.get('username')
                password = self.email_config.get('password')

                if username and password:
                    server.login(username, password)

                server.send_message(msg)

            logger.info(f"Email alert sent successfully to {msg['To']}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    def _build_email_html(self, conflicts: List[Dict[str, Any]],
                         summary: Dict[str, Any] = None) -> str:
        """Build HTML email body."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background-color: #dc3545; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .conflict {{ background-color: #f8f9fa; border-left: 4px solid #dc3545;
                            margin: 15px 0; padding: 15px; }}
                .conflict h3 {{ margin: 0 0 10px 0; color: #dc3545; }}
                .score {{ font-size: 24px; font-weight: bold; color: #dc3545; }}
                .details {{ margin: 10px 0; }}
                .details dt {{ font-weight: bold; display: inline; }}
                .details dd {{ display: inline; margin: 0 15px 0 5px; }}
                .link {{ color: #007bff; text-decoration: none; }}
                .footer {{ background-color: #f8f9fa; padding: 15px; margin-top: 20px;
                          font-size: 12px; color: #666; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f8f9fa; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>⚠️ Trademark Conflict Alert</h1>
                <p>{len(conflicts)} potential conflict(s) detected</p>
            </div>
            <div class="content">
        """

        if summary:
            html += f"""
                <h2>Monitoring Summary</h2>
                <p>
                    Files processed: {summary.get('files_processed', 'N/A')} |
                    Filings reviewed: {summary.get('filings_processed', 'N/A')} |
                    Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}
                </p>
            """

        html += "<h2>Detected Conflicts</h2>"

        for i, conflict in enumerate(conflicts, 1):
            serial = conflict.get('serial_number', 'Unknown')
            mark = conflict.get('mark_text', 'Unknown')
            score = conflict.get('similarity_score', 0)
            matched = conflict.get('matched_trademark', 'Unknown')
            classes = conflict.get('classes', [])
            gs = conflict.get('goods_services', 'N/A')
            applicant = conflict.get('applicant_name', 'Unknown')
            filing_date = conflict.get('filing_date', 'Unknown')
            reasons = conflict.get('similarity_reasons', {})

            tsdr_link = f"https://tsdr.uspto.gov/#caseNumber={serial}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"

            html += f"""
                <div class="conflict">
                    <h3>#{i}: {mark}</h3>
                    <p class="score">Similarity Score: {score:.1f}%</p>
                    <p>Matched against: <strong>{matched}</strong></p>

                    <table>
                        <tr>
                            <th>Serial Number</th>
                            <td><a href="{tsdr_link}" class="link">{serial}</a></td>
                        </tr>
                        <tr>
                            <th>Filing Date</th>
                            <td>{filing_date}</td>
                        </tr>
                        <tr>
                            <th>Classes</th>
                            <td>{', '.join(map(str, classes))}</td>
                        </tr>
                        <tr>
                            <th>Applicant</th>
                            <td>{applicant}</td>
                        </tr>
                        <tr>
                            <th>Goods/Services</th>
                            <td>{gs[:200]}{'...' if len(gs) > 200 else ''}</td>
                        </tr>
                    </table>

                    <p><strong>Why flagged:</strong></p>
                    <ul>
            """

            # Add reasons
            mark_reasons = reasons.get('mark_similarity', {})
            class_reasons = reasons.get('class_relevance', [])

            for key, value in mark_reasons.items():
                html += f"<li>{value}</li>"

            for reason in class_reasons:
                html += f"<li>{reason}</li>"

            html += f"""
                    </ul>
                    <p><a href="{tsdr_link}" class="link">View on USPTO TSDR →</a></p>
                </div>
            """

        html += """
                <div class="footer">
                    <p>This alert was generated by the Relatent Trademark Monitor.</p>
                    <p>Our Marks: TOPO (Classes 9, 42) | TOPOLOGY (Classes 9, 42)</p>
                    <p>
                        <strong>Recommended Actions:</strong><br>
                        1. Review each flagged mark on USPTO TSDR<br>
                        2. Assess actual likelihood of confusion<br>
                        3. If concerning, consult with legal counsel about opposition
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _build_email_text(self, conflicts: List[Dict[str, Any]],
                         summary: Dict[str, Any] = None) -> str:
        """Build plain text email body."""
        text = f"""
TRADEMARK CONFLICT ALERT
========================
{len(conflicts)} potential conflict(s) detected
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

"""
        if summary:
            text += f"""
MONITORING SUMMARY
------------------
Files processed: {summary.get('files_processed', 'N/A')}
Filings reviewed: {summary.get('filings_processed', 'N/A')}

"""

        text += "DETECTED CONFLICTS\n" + "-" * 50 + "\n\n"

        for i, conflict in enumerate(conflicts, 1):
            serial = conflict.get('serial_number', 'Unknown')
            mark = conflict.get('mark_text', 'Unknown')
            score = conflict.get('similarity_score', 0)
            matched = conflict.get('matched_trademark', 'Unknown')
            classes = conflict.get('classes', [])
            gs = conflict.get('goods_services', 'N/A')
            applicant = conflict.get('applicant_name', 'Unknown')
            filing_date = conflict.get('filing_date', 'Unknown')

            tsdr_link = f"https://tsdr.uspto.gov/#caseNumber={serial}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"

            text += f"""
#{i}: {mark}
Similarity Score: {score:.1f}%
Matched against: {matched}

Serial Number: {serial}
Filing Date: {filing_date}
Classes: {', '.join(map(str, classes))}
Applicant: {applicant}
Goods/Services: {gs[:200]}{'...' if len(gs) > 200 else ''}

USPTO TSDR Link: {tsdr_link}

{'-' * 50}
"""

        text += """

RECOMMENDED ACTIONS:
1. Review each flagged mark on USPTO TSDR
2. Assess actual likelihood of confusion
3. If concerning, consult with legal counsel about opposition

--
Generated by Relatent Trademark Monitor
Our Marks: TOPO (Classes 9, 42) | TOPOLOGY (Classes 9, 42)
"""

        return text

    # ==================== Slack Alerts ====================

    def _send_slack_alert(self, conflicts: List[Dict[str, Any]],
                         summary: Dict[str, Any] = None) -> bool:
        """Send Slack webhook alert for conflicts."""
        try:
            webhook_url = self.slack_config.get('webhook_url')
            if not webhook_url:
                logger.warning("Slack webhook URL not configured")
                return False

            # Build Slack message
            message = self._build_slack_message(conflicts, summary)

            # Send to Slack
            response = requests.post(
                webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            if response.status_code == 200:
                logger.info("Slack alert sent successfully")
                return True
            else:
                logger.error(f"Slack API error: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False

    def _build_slack_message(self, conflicts: List[Dict[str, Any]],
                            summary: Dict[str, Any] = None) -> Dict[str, Any]:
        """Build Slack message payload."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"⚠️ Trademark Alert: {len(conflicts)} Potential Conflict(s)",
                    "emoji": True
                }
            },
            {"type": "divider"}
        ]

        if summary:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Monitoring Summary*\nFiles: {summary.get('files_processed', 'N/A')} | Filings: {summary.get('filings_processed', 'N/A')} | Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                }
            })
            blocks.append({"type": "divider"})

        # Add each conflict (limit to first 5 for Slack)
        for i, conflict in enumerate(conflicts[:5], 1):
            serial = conflict.get('serial_number', 'Unknown')
            mark = conflict.get('mark_text', 'Unknown')
            score = conflict.get('similarity_score', 0)
            matched = conflict.get('matched_trademark', 'Unknown')
            classes = conflict.get('classes', [])
            applicant = conflict.get('applicant_name', 'Unknown')

            tsdr_link = f"https://tsdr.uspto.gov/#caseNumber={serial}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"

            # Determine emoji based on score
            if score >= 85:
                emoji = "🔴"
            elif score >= 75:
                emoji = "🟠"
            else:
                emoji = "🟡"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{mark}* (Score: {score:.0f}%)\nMatched: `{matched}` | Classes: {', '.join(map(str, classes))}\nApplicant: {applicant}"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View on TSDR",
                        "emoji": True
                    },
                    "url": tsdr_link,
                    "action_id": f"button-{serial}"
                }
            })

        if len(conflicts) > 5:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"_...and {len(conflicts) - 5} more conflicts. Check email for full details._"
                }
            })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "📋 *Next Steps:* Review on TSDR → Assess confusion risk → Consult legal if needed"
                }
            ]
        })

        return {"blocks": blocks}

    # ==================== Test Methods ====================

    def test_email(self) -> bool:
        """Send a test email."""
        test_conflict = [{
            'serial_number': '99999999',
            'mark_text': 'TESTMARK',
            'similarity_score': 75.5,
            'matched_trademark': 'TOPO',
            'classes': [9, 42],
            'goods_services': 'Test goods and services for software',
            'applicant_name': 'Test Company LLC',
            'filing_date': datetime.now().strftime('%Y-%m-%d'),
            'similarity_reasons': {
                'mark_similarity': {'test': 'This is a test alert'},
                'class_relevance': ['Class 9 matches our filing']
            }
        }]
        return self._send_email_alert(test_conflict, {'files_processed': 1, 'filings_processed': 100})

    def test_slack(self) -> bool:
        """Send a test Slack message."""
        test_conflict = [{
            'serial_number': '99999999',
            'mark_text': 'TESTMARK',
            'similarity_score': 75.5,
            'matched_trademark': 'TOPO',
            'classes': [9, 42],
            'goods_services': 'Test goods and services',
            'applicant_name': 'Test Company LLC',
            'filing_date': datetime.now().strftime('%Y-%m-%d'),
        }]
        return self._send_slack_alert(test_conflict, {'files_processed': 1, 'filings_processed': 100})


if __name__ == "__main__":
    # Test the alert system
    logging.basicConfig(level=logging.INFO)

    # Create test config
    config = {
        'email': {
            'enabled': False,  # Set to True with real credentials to test
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'your-email@gmail.com',
            'password': 'your-app-password',
            'from_address': 'trademark-monitor@relatent.com',
            'to_addresses': ['alerts@relatent.com']
        },
        'slack': {
            'enabled': False,  # Set to True with real webhook to test
            'webhook_url': 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        }
    }

    alert_system = AlertSystem(config)

    # Generate test HTML (for preview)
    test_conflicts = [
        {
            'serial_number': '99634200',
            'mark_text': 'TOPOWORLD',
            'similarity_score': 82.5,
            'matched_trademark': 'TOPO',
            'classes': [9, 42],
            'goods_services': 'Computer software for mapping and social networking',
            'applicant_name': 'Sample Tech Inc.',
            'filing_date': '2026-02-01',
            'similarity_reasons': {
                'mark_similarity': {'starts_with': "Starts with 'TOPO'"},
                'class_relevance': ['Matching classes: [9, 42]', "Keywords found: ['software', 'social', 'networking']"]
            }
        }
    ]

    html = alert_system._build_email_html(test_conflicts, {'files_processed': 5, 'filings_processed': 500})

    # Save preview
    with open('/tmp/email_preview.html', 'w') as f:
        f.write(html)
    print("Email preview saved to /tmp/email_preview.html")
