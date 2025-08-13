def run_email_sender(template_name="Template_02.html" , allow_duplicates=False):
    import os
    import pandas as pd
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from dotenv import load_dotenv

    logs = []  # Collect messages here

    CSV_FOLDER = "EmailsInfo"
    TEMPLATE_FOLDER = "EmailTemplate"
    SENT_WELCOME_FILE = "Skipped_Emails.txt"  # File to track sent welcome emails

    load_dotenv()  # Load environment variables from .env

    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


    def send_email_smtp(sender, recipient, subject, html_content):
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(html_content, "html"))
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(sender, recipient, msg.as_string())
            # logs.append(f"✅ Sent to {recipient}")
            return True
        except Exception as e:
            logs.append(f"❌ Error sending to {recipient}: {e}")
            return False

    sent_welcome_emails = set()
    if template_name == "Template_02.html":
        if os.path.exists(SENT_WELCOME_FILE):
            with open(SENT_WELCOME_FILE, "r") as f:
                sent_welcome_emails = set(line.strip() for line in f if line.strip())

    with open(os.path.join(TEMPLATE_FOLDER, template_name), "r", encoding="utf-8") as f:
        template = f.read()

    csv_files = [f for f in os.listdir(CSV_FOLDER) if f.startswith("GeneratedEmails_") and f.endswith(".csv")]
    if not csv_files:
        logs.append("❌ No CSV files found.")
        return logs  # Return logs immediately if no CSV

    latest_csv = max(csv_files, key=lambda f: os.path.getmtime(os.path.join(CSV_FOLDER, f)))
    df = pd.read_csv(os.path.join(CSV_FOLDER, latest_csv))

    # ✅ Remove duplicates if not allowed
    if not allow_duplicates:
        df = df.drop_duplicates(subset=['From Email'])
        
    new_sent_emails = set()
    sent_count = 0  # count how many new emails sent

    for _, row in df.iterrows():
        name = row['From Name']
        email = row['From Email']

        if pd.isna(email) or '@' not in email:
            continue

        if template_name == "Template_02.html" and email in sent_welcome_emails:
            logs.append(f"Skipping {email}, Email already sent.")
            continue

        personalized_html = template.replace("{From}", name if pd.notna(name) else "")
        success = send_email_smtp(SMTP_USER, email, f"Welcome to IQTechSolutions, {name}", personalized_html)

        if success and template_name == "Template_02.html":
            new_sent_emails.add(email)
            sent_count += 1
        elif success:
            sent_count += 1

    if sent_count > 0:
        logs.append(f"✅ Successfully sent {sent_count} new email{'s' if sent_count > 1 else ''}.")
    else:
        logs.append("❌ All emails in CSV have already been sent previously.")


    if new_sent_emails:
        with open(SENT_WELCOME_FILE, "a") as f:
            for em in new_sent_emails:
                f.write(em + "\n")

    return logs  # Return all collected messages
