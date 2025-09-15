import csv
import datetime
import io
import logging
import os
from flask import Flask, jsonify, render_template, send_from_directory, request, redirect, url_for, flash, session, get_flashed_messages
import subprocess

from flask.cli import load_dotenv
from send_emails import run_email_sender
import pandas as pd
from datetime import datetime
from google_auth_oauthlib.flow import Flow
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import json
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import send_file
from azure_storage import container_client

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.secret_key = "super_secret_key"  # Required for session and flash messages
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
# print("OAUTHLIB_INSECURE_TRANSPORT =", os.environ.get("OAUTHLIB_INSECURE_TRANSPORT"))
# os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # For local testing only



# 🔹 Key Vault setup
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


# ------------------------
# Default User Credentials (for demo)
# ------------------------
# users = {"admin@gmail.com": "admin"}  


key_vault = os.getenv("KeyVault_Name", "akv-test-ca")
users = os.getenv("Users_List", "app-users")

KEY_VAULT_URL = f"https://{key_vault}.vault.azure.net/"
credential = DefaultAzureCredential()
secret_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)

def get_users_from_keyvault():
    """Fetch and return users JSON from Key Vault."""
    secret = secret_client.get_secret(users)
    return json.loads(secret.value)

def save_users_to_keyvault(users_dict):
    """Save users JSON back to Key Vault."""
    secret_client.set_secret(users, json.dumps(users_dict))
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username")
        new_password = request.form.get("newpassword")

        try:
            users = get_users_from_keyvault()
            print(f"Users fetched from Key Vault for password reset: {users}")

            # Update password (just overwrite string)
            if username in users:
                users[username] = new_password  # ✅ update dict
            else:
                flash("User not found!", "error")
                return redirect(url_for("login"))

            # Save updated JSON back to Key Vault
            secret_client.set_secret("app-users", json.dumps(users))  # ✅ fixed

            flash("Password updated successfully. Please log in.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            print("Error:", e)
            flash("Something went wrong. Try again.", "error")
            return redirect(url_for("login"))



@app.route("/register", methods=["GET", "POST"])
def register():
    email = request.form.get("email")
    password = request.form.get("password")

    users = get_users_from_keyvault()

    if email in users:
        flash("⚠️ Email already registered!", "error")
        return redirect(url_for("login"))

    # Save user (for now: store password directly, better to hash later 🔑)
    users[email] = password  
    save_users_to_keyvault(users)

    flash("✅ Account created successfully! Please log in.", "success")
    return redirect(url_for("login"))
# ------------------------
# Authentication Routes
# ------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # 🔑 Get users from Key Vault
        users = get_users_from_keyvault()
        print(f"Users fetched from Key Vault: {users}")
        if username in users and users[username] == password:
            session["user"] = username
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))

# ------------------------
# Helper: Require login
# ------------------------
def login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

# ------------------------
# Helper: Feature Flags from Key Vault or Env
# ------------------------
def get_feature_flag(name: str, default: str = "false") -> bool:
    """
    Retrieve a feature flag value.
    1. Try Key Vault secret with the given name.
    2. Fallback to environment variable.
    3. If not found, use provided default.
    Returns: Boolean
    """
    value = None
    # Initialize Key Vault client once
    credential = DefaultAzureCredential()
    kv_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
    # Try from Key Vault
    try:
        secret = kv_client.get_secret(name)
        value = secret.value if secret else None
    except Exception:
        # If not found in Key Vault, fallback to env
        value = os.getenv(name, default)

    return str(value).lower() == "true"

# ------------------------
# Main page
# ------------------------

@app.route("/", methods=["GET"])
@login_required
def index():
    # Feature flag from .env
    send_email_feature = get_feature_flag("SEND-EMAIL", "true")
    print(f"SEND-EMAIL is set to: {send_email_feature}")

    generate_csv_feature = get_feature_flag("GENERATE-CSV", "true")
    print(f"GENERATE-CSV is set to: {generate_csv_feature}")

    email_insight = get_feature_flag("EMAIL-INSIGHT", "true")
    print(f"EMAIL-INSIGHT is set to: {email_insight}")

    # Get flashed messages with categories
    flash_messages = get_flashed_messages(with_categories=True)

    # Format messages
    formatted_messages = [
        {"category": cat, "message": msg} for cat, msg in flash_messages
    ]

    return render_template(
        "index.html",
        flash_messages=formatted_messages,
        send_email_feature=send_email_feature,
        generate_csv_feature=generate_csv_feature,
        email_insight=email_insight
    )

@app.route("/set-account", methods=["POST"])
@login_required
def set_account():
    selected = request.form.get("smtp_account")
    if selected:
        session["smtp_account"] = selected
    return ("", 204)

# ======================
# Email Sending
# ======================

@app.route("/send_email", methods=["POST"])
@login_required
def send_email_api():
    data = request.get_json()
    print(f"Data received for sending email: {data}")
    template = data.get("template_name")
    csv_files = data.get("csv_files", [])   # ✅ accept multiple csvs
    allow_duplicates = data.get("allow_duplicates", False)
    account_number = data.get("smtp_account", "1")  # default to 1

    print(f"Account Number Selected in send Email: {account_number}")

    try:
        logs = run_email_sender(
            template_name=template,
            csv_files=csv_files,   # ✅ pass to sender
            allow_duplicates=allow_duplicates,
            account_number=account_number
        )

        errors = [log for log in logs if "❌" in log or "Error" in log]
        if errors:
            return jsonify({"success": False, "logs": logs})
        else:
            return jsonify({"success": True, "logs": logs})

    except Exception as e:
        return jsonify({"success": False, "logs": [f"Failed to send emails: {e}"]}), 500


# ======================
# Upload CSVs
# ======================

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file and file.filename.endswith(".csv"):
        try:
            # ✅ Check if file already exists in Blob Storage
            blob_client = container_client.get_blob_client(file.filename)
            if blob_client.exists():
                return jsonify({"status": "exists", "message": f"File '{file.filename}' already exists"}), 409

            # Read uploaded CSV into DataFrame
            df = pd.read_csv(file)

            # Convert DataFrame to CSV in memory
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding="utf-8")

            # Upload to Azure Blob Storage
            blob_client.upload_blob(csv_buffer.getvalue(), overwrite=False)

            return jsonify({"status": "success", "message": f"✅ File '{file.filename}' uploaded successfully!"})

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": "Only CSV files are allowed"}), 400

# ======================
# Generate CSV
# ======================
@app.route("/generate_csv", methods=["POST"])
@login_required
def generate_csv():
    data = request.get_json()
    # print(f"Data received for CSV generation: {data}")
    email_option = data.get("email_option")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    account_number = data.get("smtp_account", "1")  # default to 1
    print(f"Account Number Selected in generate csv: {account_number}")

    try:
        # ✅ Check if Gmail authentication works before doing CSV
        # service = get_gmail_service(account_number=account_number)

        # ✅ If service is valid, proceed with CSV generation
        try:
            if email_option == "date" and start_date and end_date:
                logging.info(f"Generating CSV for emails from {start_date} to {end_date}")  

                try:
                    result = subprocess.run(
                        ["python", "gmail_to_csv.py", "date", start_date, end_date, account_number],
                        check=True,
                        text=True  
                    )
                    
                    # Display captured output in your Flask app logs
                    if result.stdout:
                        logging.info(f"Subprocess stdout: {result.stdout}")
                    if result.stderr:
                        logging.info(f"Subprocess stderr: {result.stderr}")
                    
                    logging.info(f"Return code: {result.returncode}")

                    if result.returncode == 0:
                        # Check if no messages were found
                        output = (result.stdout or "") + (result.stderr or "")
                        logging.info(f"CSV generation subprocess Results: {output}")
                        # Check if no messages were found
                        if "No messages found" in output:
                            return jsonify({"success": False, "message": "<b>No Emails Found!</b>"})

                        elif "Gmail Account Token Expired" in output:
                            session["pending_csv_request"] = data
                            session.modified = True
                            return jsonify({"token_expired": True})

                        elif "No refresh_token available" in output:
                            return jsonify({
                                "status": "error",
                                "message": "⚠️ No refresh token found. Please log in again."
                            }), 401
                        elif result.stdout and "No messages found" in result.stdout:
                            return jsonify({"success": False, "message": f"<b>No Emails Found!</b><br>from {start_date} to {end_date}!"})
                        else:
                            return jsonify({"success": True, "message": f"CSV Generated for emails from {start_date} to {end_date}!"})
                    else:
                        logging.error(f"Subprocess failed with return code {result.returncode}")
                        logging.error(f"Error details: {result.stderr}")
                        return jsonify({"success": False, "message": "Failed to generate CSV"}), 500
                        
                except Exception as e:
                    logging.error(f"Subprocess error: {e}")
                    return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

            else:
                logging.info("Generating CSV for all emails")
                print("Starting email extraction....")
            
                try:
                    result = subprocess.run(
                        ["python", "gmail_to_csv.py", "all", account_number],
                        check=True,
                        capture_output=True,  # capture stdout and stderr
                        text=True
                    )
                    
                    # Display captured output in your Flask app logs
                    if result.stdout:
                        logging.info(f"Subprocess stdout: {result.stdout}")
                    if result.stderr:
                        logging.info(f"Subprocess stderr: {result.stderr}")
                    
                    logging.info(f"Return code: {result.returncode}")
                    
                    if result.returncode == 0:
                        output = (result.stdout or "") + (result.stderr or "")
                        logging.info(f"CSV generation subprocess Results: {output}")
                        # Check if no messages were found
                        if "No messages found" in output:
                            return jsonify({"success": False, "message": "<b>No Emails Found!</b>"})

                        elif "Gmail Account Token Expired" in output:
                            session["pending_csv_request"] = data
                            session.modified = True
                            return jsonify({"token_expired": True})
                            
                        elif "No refresh_token available" in output:
                            return jsonify({
                                "status": "error",
                                "message": "⚠️ No refresh token found. Please log in again."
                            }), 401

                        else:
                            return jsonify({"success": True, "message": "CSV with all emails generated successfully!"})
                    else:
                        logging.error(f"Subprocess failed with return code {result.returncode}")
                        logging.error(f"Error details: {result.stderr}")
                        return jsonify({"success": False, "message": "Failed to generate CSV"}), 500
                        
                except Exception as e:
                    logging.error(f"Subprocess error: {e}")
                    return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500
        except subprocess.CalledProcessError:
            return jsonify({"success": False, "message": "Failed to generate CSV file."}), 500

    except RuntimeError as e:
        # ✅ Handle missing Gmail token properly
        if "GMAIL_TOKEN_MISSING" in str(e):
            session["pending_csv_request"] = data
            session.modified = True
            print(f"Error When Token Missing: {str(e)}")
            return jsonify({"success": False, "auth_required": True, "message": "Please authenticate Gmail first."})
        else:
            return jsonify({"success": False, "message": f"Error: {str(e)}"})

# ======================
# List CSVs
# ======================
@app.route("/list_csv")
@login_required
def list_csv():
    files = []
    try:
        blob_list = container_client.list_blobs()
        for idx, blob in enumerate(blob_list, start=1):
            created_time = blob.creation_time.strftime("%Y-%m-%d %H:%M:%S") if blob.creation_time else "N/A"
            files.append({
                "sr_no": idx,
                "name": blob.name,
                "created": created_time
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(files)

# ======================
# Download CSVs
# ======================

@app.route("/download/<filename>")
@login_required
def download_file(filename):
    try:
        blob_client = container_client.get_blob_client(filename)

        # Download blob to memory
        stream = io.BytesIO()
        download_stream = blob_client.download_blob()
        stream.write(download_stream.readall())
        stream.seek(0)

        return send_file(
            stream,
            as_attachment=True,
            download_name=filename,
            mimetype="text/csv"
        )
    except Exception as e:
        return f"❌ Download failed: {str(e)}", 500

# ======================
# Delete CSVs
# ======================

@app.route("/delete/<filename>", methods=["DELETE"])
@login_required
def delete_file(filename):
    try:
        blob_client = container_client.get_blob_client(filename)
        blob_client.delete_blob()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ======================
# Template Routes Start
# ======================
@app.route("/create-template-page")
@login_required
def create_template_page():
    return render_template("CreateTemplate.html")

@app.route("/create-template", methods=["POST"])
@login_required
def create_template():
    try:
        data = request.get_json()
        template_name = data.get('name')
        template_content = data.get('content')

        if not template_name or not template_content:
            return jsonify({'success': False, 'message': 'Template name and content are required'}), 400

        sanitized_name = ''.join(c for c in template_name if c.isalnum() or c in ('_', '-'))
        filename = f"{sanitized_name}.html"

        templates_dir = os.path.join(app.root_path, 'static', 'templates')
        os.makedirs(templates_dir, exist_ok=True)
        file_path = os.path.join(templates_dir, filename)

        if os.path.exists(file_path):
            return jsonify({'success': False, 'message': f'Template "{filename}" already exists'}), 400

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(template_content)

        return jsonify({
            'success': True,
            'message': f'Template "{filename}" created successfully',
            'filename': f"static/templates/{filename}"
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error creating template: {str(e)}'}), 500

@app.route("/list-templates")
@login_required
def list_templates():
    try:
        templates_dir = os.path.join(app.root_path, 'static', 'templates')
        os.makedirs(templates_dir, exist_ok=True)

        template_files = [
            f for f in os.listdir(templates_dir) if f.endswith('.html')
        ]

        return jsonify({
            'success': True,
            'templates': template_files
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route("/delete-template/<template_name>", methods=["DELETE"])
@login_required
def delete_template(template_name):
    try:
        templates_dir = os.path.join(app.root_path, 'static', 'templates')
        file_path = os.path.join(templates_dir, template_name)

        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'success': True, 'message': f'{template_name} deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Template not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route("/<template_name>")
@login_required
def preview_template(template_name):
    try:
        templates_dir = os.path.join(app.root_path, 'static', 'templates')
        file_path = os.path.join(templates_dir, template_name)

        if not os.path.exists(file_path):
            return f"Template '{template_name}' not found", 404

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return content  

    except Exception as e:
        return f"Error loading template: {str(e)}", 500

# ======================
# Template Routes End
# ======================

CSV_FILE = os.path.join("static", "EmailsRecord.csv")

@app.route("/api/records")
@login_required
def get_records():
    records = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    return jsonify(records)



def get_redirect_uri():
    if "localhost" in request.host or "127.0.0.1" in request.host:
        print("Running in local environment")
        return url_for("gmail_oauth2callback", _external=True , _scheme="http")
    else:
        print("Running in deployed environment")
        return url_for("gmail_oauth2callback", _external=True, _scheme="https")

@app.route("/gmail/auth")
@login_required
def gmail_auth():
    account_number = request.args.get("account", "1")
    print(f"Account Number Selected in gmail auth: {account_number}")
    CREDENTIALS_SECRET_NAME = f"CREDENTIALS-{account_number}"

    print(f"Attempting to retrieve credentials from Key Vault Account Number {account_number}...")
    credential = DefaultAzureCredential()
    kv_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)

    try:
        credentials_secret = kv_client.get_secret(CREDENTIALS_SECRET_NAME)
        credentials_json = json.loads(credentials_secret.value)
    except Exception as e:
        return redirect(url_for("index", keyvault_error="1"))

    URL = get_redirect_uri()

    flow = Flow.from_client_config(
        credentials_json,
        scopes=SCOPES,
        redirect_uri=URL
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=account_number  # 👈 carry account number here
    )
    return redirect(auth_url)


@app.route("/oauth2callback")
@login_required
def gmail_oauth2callback():
    # Directly generate CSV with stored parameters
    account_number = request.args.get("state", "1")  # 👈 get account number from state
    print(f"Account Number Selected in oauth2callback: {account_number}")
    TOKEN_SECRET_NAME = f"TOKEN-ACC-{account_number}"
    CREDENTIALS_SECRET_NAME = f"CREDENTIALS-{account_number}"

    credential = DefaultAzureCredential()
    kv_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
    credentials_json = json.loads(kv_client.get_secret(CREDENTIALS_SECRET_NAME).value)

    # Detect environment (localhost vs deployed)
    URL = get_redirect_uri()

    flow = Flow.from_client_config(
        credentials_json,
        scopes=SCOPES,
        redirect_uri=URL
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    kv_client.set_secret(TOKEN_SECRET_NAME, creds.to_json())
    flash("✅ Gmail authentication successful! Token stored in Key Vault.", "success")
    
    # Check if we have a pending CSV request
    pending_request = session.pop("pending_csv_request", None)
    if pending_request:
        
        email_option = pending_request["email_option"]
        start_date = pending_request.get("start_date")
        end_date = pending_request.get("end_date")

        # Call your generate_csv logic
        try:
            if email_option == "date" and start_date and end_date:
                subprocess.run(
                    ["python", "gmail_to_csv.py", "date", start_date, end_date, account_number],
                    check=True
                )
            else:
                subprocess.run(
                    ["python", "gmail_to_csv.py", "all", account_number],
                    check=True
                )
            flash(f"CSV generated for emails from {start_date} to {end_date}!", "success")
        except subprocess.CalledProcessError:
            flash("Failed to generate CSV file.", "danger")

    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
