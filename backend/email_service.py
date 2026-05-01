"""
Email service: send trading signal reports via SMTP.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from backend.config import (
    SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
    EMAIL_FROM, EMAIL_TO
)

logger = logging.getLogger(__name__)


def format_signal_html(signal):
    """Format a single signal as HTML table row."""
    strategy = signal.get("recommended_strategy", {})
    signal_type = signal.get("signal_type", "unknown").upper()
    color = "red" if signal_type == "OVERBOUGHT" else "green"
    
    return f"""
    <tr style="border-bottom: 1px solid #ddd;">
        <td style="padding: 12px; text-align: center;">
            <strong>{signal.get('symbol')}</strong>
        </td>
        <td style="padding: 12px; text-align: center;">
            <span style="background-color: {color}; color: white; padding: 5px 10px; border-radius: 3px;">
                {signal_type}
            </span>
        </td>
        <td style="padding: 12px; text-align: right;">${signal.get('current_price', 'N/A')}</td>
        <td style="padding: 12px; text-align: center;">{signal.get('rsi', 'N/A'):.2f}</td>
        <td style="padding: 12px; text-align: center;">{signal.get('ma20', 'N/A'):.2f}</td>
        <td style="padding: 12px; text-align: center;">{signal.get('ma200', 'N/A'):.2f}</td>
        <td style="padding: 12px; text-align: center;">
            {strategy.get('type', 'N/A').replace('_', ' ').title()}
        </td>
        <td style="padding: 12px; text-align: right;">
            ${strategy.get('net_premium_collected') or strategy.get('premium_collected', 'N/A')}
        </td>
        <td style="padding: 12px; text-align: center;">
            {signal.get('confidence', 'N/A').title()}
        </td>
    </tr>
    """


def create_email_body(signals):
    """Create HTML email body with all signals."""
    if not signals:
        return "<p>No trading signals generated.</p>"
    
    signal_rows = "".join([format_signal_html(s) for s in signals])
    
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            .timestamp {{ color: #7f8c8d; font-size: 12px; margin: 10px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th {{ background-color: #3498db; color: white; padding: 12px; text-align: left; }}
            .summary {{ background-color: #ecf0f1; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            .footer {{ font-size: 12px; color: #95a5a6; margin-top: 30px; border-top: 1px solid #bdc3c7; padding-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Trading Signal Report</h1>
            <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}</div>
            
            <div class="summary">
                <strong>Total Signals:</strong> {len(signals)} <br>
                <strong>Overbought:</strong> {len([s for s in signals if s.get('signal_type') == 'overbought'])} <br>
                <strong>Oversold:</strong> {len([s for s in signals if s.get('signal_type') == 'oversold'])}
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Signal</th>
                        <th>Price</th>
                        <th>RSI</th>
                        <th>MA20</th>
                        <th>MA200</th>
                        <th>Strategy</th>
                        <th>Income</th>
                        <th>Confidence</th>
                    </tr>
                </thead>
                <tbody>
                    {signal_rows}
                </tbody>
            </table>
            
            <div class="summary">
                <p><strong>📌 Disclaimer:</strong></p>
                <p>These signals are generated algorithmically and for informational purposes only. 
                   Not financial advice. Always consult a professional advisor before trading. 
                   Past performance does not guarantee future results. Options trading involves substantial risk.</p>
            </div>
            
            <div class="footer">
                <p>Trading Signal Agent | Hourly Analysis (7x daily)</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_body


def send_signal_report(signals):
    """
    Send trading signals report via email.
    signals: list of signal dicts
    """
    if not signals:
        logger.info("No signals to report, skipping email")
        return False
    
    try:
        # Create email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🚨 Trading Signals: {', '.join([s['symbol'] for s in signals])} ({len(signals)} signals)"
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(EMAIL_TO)
        
        # Create HTML body
        html_body = create_email_body(signals)
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        
        # Send email
        logger.info("Connecting to SMTP server %s:%d", SMTP_SERVER, SMTP_PORT)
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info("Email sent successfully to %s with %d signals", EMAIL_TO, len(signals))
        return True
    
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed. Check credentials in .env")
        return False
    except smtplib.SMTPException as e:
        logger.error("SMTP error: %s", str(e))
        return False
    except Exception as e:
        logger.error("Failed to send email: %s", str(e), exc_info=True)
        return False


def send_test_email():
    """Send a test email to verify SMTP configuration."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Test Email - Trading Signal Agent"
        msg['From'] = EMAIL_FROM
        msg['To'] = ", ".join(EMAIL_TO)
        
        test_body = """
        <html>
        <body>
            <h1>✅ Test Email Successful</h1>
            <p>SMTP configuration is working correctly.</p>
            <p>The trading signal agent is ready to send reports.</p>
        </body>
        </html>
        """
        
        html_part = MIMEText(test_body, 'html')
        msg.attach(html_part)
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info("Test email sent successfully")
        return True
    
    except Exception as e:
        logger.error("Failed to send test email: %s", str(e), exc_info=True)
        return False
