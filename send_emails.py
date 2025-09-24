def run_email_sender(template_name, csv_files=None, allow_duplicates=False, account_number="1"):
    import os, pandas as pd, smtplib, io
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from dotenv import load_dotenv
    from datetime import datetime
    from azure_storage import container_client

    logs = []
    EmailsRecord = "static/EmailsRecord.csv"
    

    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = os.getenv(f"SMTP_USER_{account_number}")
    SMTP_PASSWORD = os.getenv(f"SMTP_PASSWORD_{account_number}")

    # =======================================================
    # ================== Hostinger CPanel ===================
    # =======================================================

    cpanel_user = os.getenv("CPANEL_USER", "info@iqtechsolutions.co.uk")
    cpanel_password = os.getenv("CPANEL_PASSWORD")
    server = "smtp.titan.email"
    port = 465
    use_ssl = True

    def send_email_hostinger(sender, recipient, subject, html_content):
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(html_content, "html"))
        try:
            if use_ssl:
                with smtplib.SMTP_SSL(server, port) as server_conn:
                    server_conn.login(sender, cpanel_password)
                    server_conn.sendmail(sender, recipient, msg.as_string())
            else:
                with smtplib.SMTP(server, port) as server_conn:
                    server_conn.starttls()
                    server_conn.login(sender, cpanel_password)
                    server_conn.sendmail(sender, recipient, msg.as_string())
            return True
        except Exception as e:
            logs.append(f"❌ Error sending to {recipient}: {e}")
            return False
        
    
    # ========================================================

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
            return True
        except Exception as e:
            logs.append(f"❌ Error sending to {recipient}: {e}")
            return False

    with open(template_name) as f:
        template = f.read()

    if not csv_files:
        logs.append("❌ No CSV files selected.")
        return logs

    total_sent = 0
    new_sent_emails = set()
    records_to_save = []  # collect records for batch save

    
    for csv_file in csv_files:
        try:
            # Get blob client for this file
            blob_client = container_client.get_blob_client(csv_file)

            # Check if file exists in blob
            if not blob_client.exists():
                logs.append(f"❌ CSV not found in Azure Blob Storage: {csv_file}")
                continue

            # Download blob content into memory
            download_stream = blob_client.download_blob()
            df = pd.read_csv(io.StringIO(download_stream.content_as_text()))

        except Exception as e:
            logs.append(f"❌ Error reading {csv_file} from Azure Blob: {str(e)}")
            continue

        if not allow_duplicates:
            df = df.drop_duplicates(subset=['From Email'])

        for _, row in df.iterrows():
            name = row['From Name']
            email = row['From Email']

            if pd.isna(email) or '@' not in email:
                continue

            personalized_html = template.replace("{From}", name if pd.notna(name) else "")
            if account_number == "5":  # Use Hostinger SMTP
                success = send_email_hostinger(
                    cpanel_user,
                    email,
                    f"Welcome to MailFusion, {name}",
                    personalized_html
                )
            else:
                success = send_email_smtp(
                    SMTP_USER,
                    email,
                    f"Welcome to MailFusion, {name}",
                    personalized_html
                )

            if success:
                total_sent += 1
                new_sent_emails.add(email)
                records_to_save.append([
                    email,
                    os.path.basename(template_name),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])
    # Save to EmailsRecord.csv
    if records_to_save:
        try:
            # Load existing file to get last Sr.No
            if os.path.exists(EmailsRecord):
                existing_df = pd.read_csv(EmailsRecord)
                last_srno = existing_df["Sr.No"].max() if not existing_df.empty else 0
            else:
                last_srno = 0

            new_df = pd.DataFrame(records_to_save, columns=["Email", "Template", "DateTime"])
            new_df.insert(0, "Sr.No", range(last_srno + 1, last_srno + 1 + len(new_df)))

            # Append to CSV
            new_df.to_csv(EmailsRecord, mode="a", header=not os.path.exists(EmailsRecord), index=False)
            logs.append(f"📌 Records saved to {EmailsRecord}")
        except Exception as e:
            logs.append(f"⚠️ Error saving records: {e}")

    if total_sent > 0:
        logs.append(f"✅ Successfully sent {total_sent} new email(s).")
    else:
        logs.append("❌ No new emails were sent.")

    return logs
