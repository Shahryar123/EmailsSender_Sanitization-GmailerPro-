from __future__ import print_function
import os.path
import re
import sys
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pandas as pd

# Gmail API scope (read-only access)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def parse_from_field(from_field):
    """Splits the From field into Name and Email."""
    match = re.match(r'(?:"?([^"]*)"?\s)?<?(.+@[^>]+)>?', from_field)
    if match:
        name = match.group(1) or ""
        email = match.group(2) or ""
        return name.strip(), email.strip()
    return from_field, ""


def build_gmail_query(arg_list):
    """Build Gmail API query based on arguments."""
    if len(arg_list) > 0 and arg_list[0].lower() == "date":
        try:
            from_date = datetime.strptime(arg_list[1], "%Y-%m-%d").strftime("%Y/%m/%d")
            to_date = datetime.strptime(arg_list[2], "%Y-%m-%d").strftime("%Y/%m/%d")
            print(f"📌 From Date: {from_date}")
            print(f"📌 To Date: {to_date}")

            return f"after:{from_date} before:{to_date}"
        except Exception as e:
            print(f"❌ Invalid date format. Use YYYY-MM-DD. Error: {e}")
            sys.exit(1)
    return ""  # no query means all emails

def main():
    query = ""
    max_results_arg = None
    # Default account number
    account_number = "1"

    # Parse CLI args
    if len(sys.argv) > 1:
        if sys.argv[1].lower() == "all":
            max_results_arg = None
            if len(sys.argv) > 2:
                account_number = sys.argv[2]
        elif sys.argv[1].lower() == "date":
            query = build_gmail_query(sys.argv[1:4])
            max_results_arg = None
            if len(sys.argv) > 4:
                account_number = sys.argv[4]
        else:
            try:
                max_results_arg = int(sys.argv[1])
            except ValueError:
                max_results_arg = 10
            if len(sys.argv) > 2:
                account_number = sys.argv[2]
    else:
        max_results_arg = 10

    print(f"Using account {account_number} with max_results={max_results_arg}")

    # Auth
    credentials_file = f'GmailAPI_Credentials/credentials_{account_number}.json'
    token_file = f'token_{account_number}.json'
    creds = None

    try:
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)

    try:
        service = build('gmail', 'v1', credentials=creds)
    except Exception as e:
        print(f"❌ Failed to build Gmail service: {e}")
        sys.exit(1)

   # Fetch labels once
    labels_resp = service.users().labels().list(userId="me").execute()
    labels = [lbl["id"] for lbl in labels_resp.get("labels", [])]

    has_primary = "CATEGORY_PRIMARY" in labels  # Workspace won't have this

    if has_primary:
        # Personal Gmail → search only Primary
        if query:
            search_query = f"category:primary {query}"
        else:
            search_query = "category:primary"
            print(f"📌 Gmail API Query (Primary only): {search_query}")

    else:
        # Workspace Gmail → fallback to plain Inbox (remove only category:primary, keep the rest)
        if query:
            search_query = query.replace("category:primary", "").strip()
        else:
            search_query = ""  # if nothing provided, leave empty
        
        print(f"⚠️ CATEGORY_PRIMARY not found → using Inbox with query: {search_query}")

    # Run query
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results_arg,
        labelIds=["INBOX"],   # Force only Inbox mails
        q=search_query
    ).execute()

    messages = results.get('messages', [])
    print(f"📌 Retrieved {len(messages)} messages")

    email_data = []
    for msg in messages:
        try:
            msg_id = msg['id']
            msg_detail = service.users().messages().get(
                userId='me',
                id=msg_id,
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = msg_detail['payload']['headers']
            from_field = next((h['value'] for h in headers if h['name'] == 'From'), "")
            subject_field = next((h['value'] for h in headers if h['name'] == 'Subject'), "")
            date_field = next((h['value'] for h in headers if h['name'] == 'Date'), "")

            from_name, from_email = parse_from_field(from_field)

            try:
                email_datetime = datetime.strptime(date_field, '%a, %d %b %Y %H:%M:%S %z')
                email_datetime_str = email_datetime.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                email_datetime_str = date_field

            email_data.append({
                'ID': msg_id,
                'From Name': from_name,
                'From Email': from_email,
                'Subject': subject_field,
                'DateTime Received': email_datetime_str
            })
        except Exception as e:
            print(f"❌ Failed to parse message {msg}: {e}")

    # Save CSV
    try:
        df = pd.DataFrame(email_data)
        now_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f"EmailsInfo/GeneratedEmails_{now_str}.csv"
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"✅ Saved {filename} with {len(email_data)} emails.")
    except Exception as e:
        print(f"❌ Failed to save CSV: {e}")

if __name__ == '__main__':
    main()
