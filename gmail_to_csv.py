from __future__ import print_function
import os.path
import pandas as pd
import re
import sys
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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

def main():
    # Get maxResults from CLI arg
    max_results_arg = None
    if len(sys.argv) > 1:
        if sys.argv[1].lower() == "all":
            max_results_arg = None  # Fetch all available (may take time)
        else:
            try:
                max_results_arg = int(sys.argv[1])
            except ValueError:
                max_results_arg = 10
    else:
        max_results_arg = 10

    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'GmailAPI_Credentials/credentials.json', SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # List messages
    results = service.users().messages().list(
        userId='me', maxResults=max_results_arg
    ).execute()
    messages = results.get('messages', [])

    email_data = []
    for msg in messages:
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

        # Convert email date to local datetime
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

    df = pd.DataFrame(email_data)

    # Create filename
    now_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"EmailsInfo/GeneratedEmails_{now_str}.csv"

    df.to_csv(filename, index=False, encoding='utf-8')
    print(f"✅ Saved {filename} with {len(email_data)} emails.")

if __name__ == '__main__':
    main()
