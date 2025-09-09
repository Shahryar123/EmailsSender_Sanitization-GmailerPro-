from __future__ import print_function

from datetime import datetime, time
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from google_auth_oauthlib.flow import Flow
from email.utils import parsedate_to_datetime
import json , logging, os.path, re, sys, pandas as pd, time, threading
from azure_storage import container_client
import io
import os
import imaplib, email

# Gmail API scope (read-only access)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
# Azure Key Vault setup
KEY_VAULT_URL = "https://akv-test-ca.vault.azure.net/"

credential = DefaultAzureCredential()
kv_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(message)s")
# Cache for Gmail services (avoid authenticating every time)
_gmail_service_cache = {}
_creds_cache = {}           # cache credentials JSON per account
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds

# Titan IMAP configuration
TITAN_IMAP = "imap.titan.email"
TITAN_PORT = 993

def parse_from_field(from_field):
    """Splits the From field into Name and Email."""
    match = re.match(r'(?:"?([^"]*)"?\s)?<?(.+@[^>]+)>?', from_field)
    if match:
        name = match.group(1) or ""
        email = match.group(2) or ""
        return name.strip(), email.strip()
    return from_field, ""

def build_gmail_query(arg_list,generated):
    """Build Gmail API query based on arguments."""
    if len(arg_list) > 0 and arg_list[0].lower() == "date":
        try:
            from_date = datetime.strptime(arg_list[1], "%Y-%m-%d").strftime("%Y/%m/%d")
            to_date = datetime.strptime(arg_list[2], "%Y-%m-%d").strftime("%Y/%m/%d")
            print(f"From Date: {from_date}")
            print(f"To Date: {to_date}")

            if(generated):

                if from_date and to_date:
                    # Convert YYYY/MM/DD -> DD/MM/YYYY
                    from_formatted = "/".join(reversed(from_date.split("/")))
                    to_formatted = "/".join(reversed(to_date.split("/")))
                    return f"{from_formatted}_to_{to_formatted}"
                
            return f"after:{from_date} before:{to_date}"
        
        except Exception as e:
            print(f"Invalid date format. Use YYYY-MM-DD. Error: {e}")
            sys.exit(1)
    return ""  # no query means all emails

def Get_AccountName(account_number):
    ACCOUNT_MAP = {
    "1": "Sales@longislandequipment",
    "2": "Iqtechconsultancy",
    "3": "Iqtechsupport",
    "4": "Muhammadshahryar135",
    "5": "Info@iqtechsolutions"
    }
    dates = build_gmail_query(sys.argv[1:4], True)
    if dates:
        account_name = ACCOUNT_MAP.get(account_number, "UnknownAccount") + f"_{dates.replace(':','-').replace('/','-').replace(' ','_')}"
        logging.info(f"Account name without date: {account_name}")

    else:
        account_name = ACCOUNT_MAP.get(account_number, "UnknownAccount") + datetime.now().strftime("_%d-%m-%Y_%H:%M:%S")
        logging.info(f"Account name without date: {account_name}")
    return account_name

def _load_token_from_kv(account_number):
    """Fetch token once from Key Vault."""
    token_secret = kv_client.get_secret(f"TOKEN-ACC-{account_number}")
    return json.loads(token_secret.value)

def _save_token_to_kv_async(account_number, creds):
    """Save refreshed token to Key Vault (fire-and-forget)."""
    def _save():
        try:
            kv_client.set_secret(f"TOKEN-ACC-{account_number}", creds.to_json())
            logging.info(f"[KV] Secret updated for account {account_number}")
        except Exception as e:
            logging.warning(f"[KV] Failed to update secret for {account_number}: {e}")

    threading.Thread(target=_save, daemon=True).start()

def get_titan_emails(username, password, max_results=None, from_date=None, to_date=None):
    """Fetch emails from Titan using IMAP with optional date filtering."""
    email_data = []
    try:
        mail = imaplib.IMAP4_SSL(TITAN_IMAP, TITAN_PORT)
        mail.login(username, password)
        mail.select("inbox")

        # --- Build search query ---
        search_criteria = ["ALL"]

        if from_date:
            # IMAP date format = DD-Mon-YYYY
            search_criteria = [f'SINCE {from_date.strftime("%d-%b-%Y")}']
        if to_date:
            search_criteria.append(f'BEFORE {to_date.strftime("%d-%b-%Y")}')

        search_str = " ".join(search_criteria)
        logging.info(f"Titan IMAP search query: {search_str}")

        # --- Run search ---
        status, messages = mail.search(None, search_str)
        if status != "OK":
            logging.error("Failed to search Titan inbox")
            return []

        mail_ids = messages[0].split()
        if max_results:
            mail_ids = mail_ids[-max_results:]

        for num in reversed(mail_ids):
            status, msg_data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])
            from_field = msg.get("From", "")
            subject_field = msg.get("Subject", "")
            date_field = msg.get("Date", "")

            from_name, from_email = parse_from_field(from_field)

            email_data.append({
                "ID": num.decode(),
                "From Name": from_name,
                "From Email": from_email,
                "Subject": subject_field,
                "DateTime Received": date_field
            })

        mail.logout()
        logging.info(f"Retrieved {len(email_data)} Titan emails")

    except Exception as e:
        logging.error(f"Failed to fetch Titan emails: {e}", exc_info=True)

    return email_data


def get_gmail_service(account_number):
    """Retrieve Gmail service with memory cache and resilient Key Vault usage."""
    global _gmail_service_cache, _creds_cache

    # ✅ If Gmail API service already cached, return it
    if account_number in _creds_cache and account_number in _gmail_service_cache:
        logging.info(f"Using cached credentials and service for account {account_number}")
        return _gmail_service_cache[account_number]


    # ✅ Load creds from cache or Key Vault
    if account_number not in _creds_cache:
        logging.info(f"Loading credentials for account {account_number} from Key Vault")
        _creds_cache[account_number] = _load_token_from_kv(account_number)

    creds = Credentials.from_authorized_user_info(_creds_cache[account_number], SCOPES)

    # ✅ Handle refresh if expired
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            logging.warning(f"Credentials expired for account {account_number}, refreshing...")
            try:
                creds.refresh(Request())
                # Update in-memory cache immediately
                _creds_cache[account_number] = json.loads(creds.to_json())

                # Best-effort save to Key Vault (async, non-blocking)
                _save_token_to_kv_async(account_number, creds)
                logging.info(f"Refresh successful for account {account_number}")
            except Exception as e:
                raise RuntimeError("Gmail Account Token Expired")
            
 
        else:
            logging.error(f"No refresh_token for account {account_number}, re-auth required")
            raise RuntimeError("No refresh_token available")

    # ✅ Build Gmail API client
    service = build("gmail", "v1", credentials=creds)
    _gmail_service_cache[account_number] = service
    logging.info(f"Gmail API service ready for account {account_number}")

    return service


def save_emails_to_csv(email_data, account_name):
    try:
        df = pd.DataFrame(email_data)        

        # File name in blob storage
        filename = f"{account_name}.csv"

        # Convert DataFrame to CSV in memory
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, encoding="utf-8")

        # Upload to Azure Blob
        blob_client = container_client.get_blob_client(filename)
        blob_client.upload_blob(csv_buffer.getvalue(), overwrite=True)

        logging.info(f"✅ Uploaded CSV to Blob: {filename} with {len(email_data)} emails")
        return blob_client.url  # Return blob URL if you want to show it in UI

    except Exception as e:
        logging.error(f"❌ Failed to upload CSV: {e}", exc_info=True)
        return None
    
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
            query = build_gmail_query(sys.argv[1:4],False)
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

    logging.info(f"Using account {account_number} with max_results={max_results_arg}")
    if(account_number == "5"):
        if sys.argv[1].lower() == "date":
            from_date = datetime.strptime(sys.argv[2], "%Y-%m-%d")
            to_date = datetime.strptime(sys.argv[3], "%Y-%m-%d")
            print(f"From Date: {from_date}")
            print(f"To Date: {to_date}")
        titan_user = os.getenv("CPANEL_USER", "info@iqtechsolutions.co.uk")
        titan_pass = os.getenv("CPANEL_PASSWORD", "P2ssword16!")
        logging.info(f"Fetching Titan Emails from account {titan_user}")
        email_data = get_titan_emails(titan_user, titan_pass, max_results_arg, from_date if 'from_date' in locals() else None, to_date if 'to_date' in locals() else None)
        account_name = Get_AccountName(account_number)
    else:
        # ✅ Build Gmail API service
        try:
            service = get_gmail_service(account_number)
            logging.info("Gmail service built successfully")
        except Exception as ex:
            logging.error(f"Failed to build Gmail service: {ex}", exc_info=True)
            return

        # Fetch labels once
        try:
            labels_resp = service.users().labels().list(userId="me").execute()
            labels = [lbl["id"] for lbl in labels_resp.get("labels", [])]
            logging.info(f"Fetched {len(labels)} labels for account {account_number}")
        except Exception as e:
            logging.error(f"Failed to fetch labels: {e}", exc_info=True)
            return

        has_primary = "CATEGORY_PRIMARY" in labels

        if has_primary:
            search_query = f"category:primary {query}" if query else "category:primary"
            logging.info(f"Gmail API Query (Primary only): {search_query}")
        else:
            search_query = query.replace("category:primary", "").strip() if query else ""
            logging.warning(f"CATEGORY_PRIMARY not found → using Inbox with query: {search_query}")

        # Run query
        all_messages = []
        page_token = None

        try:
            while True:
                results = service.users().messages().list(
                    userId="me",
                    maxResults=max_results_arg,
                    labelIds=["INBOX"],
                    q=search_query,
                    pageToken=page_token
                ).execute()

                messages = results.get('messages', [])
                all_messages.extend(messages)
                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            logging.info(f"Retrieved {len(all_messages)} messages")
        except Exception as e:
            logging.error(f"Failed to fetch messages: {e}", exc_info=True)
            return

        if not all_messages:
            print("No messages found")  # This will be captured by stdout
            logging.warning("No messages found")
            sys.exit(0)  # or exit with a specific code if you want

        # Process emails
        email_data = []
        PARSE_DATES = False
        start_time = time.time()

        for msg in all_messages:
            try:
                msg_id = msg['id']
                msg_detail = service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date'],
                    fields="id,payload/headers"
                ).execute()

                headers = msg_detail['payload']['headers']
                from_field = next((h['value'] for h in headers if h['name'] == 'From'), "")
                subject_field = next((h['value'] for h in headers if h['name'] == 'Subject'), "")
                date_field = next((h['value'] for h in headers if h['name'] == 'Date'), "")

                from_name, from_email = parse_from_field(from_field)
                email_datetime_str = date_field if not PARSE_DATES else parsedate_to_datetime(date_field).strftime('%Y-%m-%d %H:%M:%S')

                email_data.append({
                    'ID': msg_id,
                    'From Name': from_name,
                    'From Email': from_email,
                    'Subject': subject_field,
                    'DateTime Received': email_datetime_str
                })
            except Exception as e:
                logging.error(f"Failed to parse message {msg}", exc_info=True)

        end_time = time.time()
        logging.info(f"Processed {len(email_data)} emails in {end_time - start_time:.2f} seconds")

        account_name = Get_AccountName(account_number)
         
    url = save_emails_to_csv(email_data, account_name)

if __name__ == '__main__':
    main()
