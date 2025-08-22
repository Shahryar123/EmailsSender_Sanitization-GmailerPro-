import csv
import datetime
import os
from flask import Flask, jsonify, render_template, send_from_directory, request, redirect, url_for, flash, session, get_flashed_messages
import subprocess
from send_emails import run_email_sender
import pandas as pd
from datetime import datetime


app = Flask(__name__)
app.secret_key = "super_secret_key"  # Required for session and flash messages

# ------------------------
# Default User Credentials (for demo)
# ------------------------
users = {"admin@gmail.com": "admin"}  # TODO: replace with DB or hashed passwords

# ------------------------
# Authentication Routes
# ------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

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
# Main page
# ------------------------

@app.route("/", methods=["GET"])
@login_required
def index():
    flash_messages = get_flashed_messages(with_categories=True)
    formatted_messages = [
        {"category": cat, "message": msg} for cat, msg in flash_messages
    ]
    return render_template("index.html", flash_messages=formatted_messages)

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
    template = data.get("template_name")
    csv_files = data.get("csv_files", [])   # ✅ accept multiple csvs
    allow_duplicates = data.get("allow_duplicates", False)
    account_number = session.get("smtp_account", "1")

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
# Generate CSV
# ======================
@app.route("/generate_csv", methods=["POST"])
@login_required
def generate_csv():
    data = request.get_json()
    email_option = data.get("email_option")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    account_number = session.get("smtp_account", "1")

    try:
        if email_option == "date" and start_date and end_date:
            subprocess.run(
                ["python", "gmail_to_csv.py", "date", start_date, end_date, account_number],
                check=True
            )
            return jsonify({"success": True, "message": f"CSV generated for emails from {start_date} to {end_date}!"})
        else:
            subprocess.run(
                ["python", "gmail_to_csv.py", "all", account_number],
                check=True
            )
            return jsonify({"success": True, "message": "CSV with all emails generated successfully!"})
    except subprocess.CalledProcessError:
        return jsonify({"success": False, "message": "Failed to generate CSV file."}), 500

# ======================
# Files
# ======================
CSV_FOLDER = os.path.join(os.getcwd(), "EmailsInfo")

@app.route("/list_csv")
@login_required
def list_csv():
    files = []
    if os.path.exists(CSV_FOLDER):
        csv_files = [
            f for f in os.listdir(CSV_FOLDER) if f.endswith(".csv")
        ]
        csv_files.sort(
            key=lambda f: os.path.getctime(os.path.join(CSV_FOLDER, f)),
            reverse=True
        )
        
        for idx, file in enumerate(csv_files, start=1):
            file_path = os.path.join(CSV_FOLDER, file)
            created_time = datetime.fromtimestamp(
                os.path.getctime(file_path)
            ).strftime("%Y-%m-%d %H:%M:%S")
            files.append({
                "sr_no": idx,
                "name": file,
                "created": created_time
            })
    return jsonify(files)

@app.route("/download/<filename>")
@login_required
def download_file(filename):
    return send_from_directory(CSV_FOLDER, filename, as_attachment=True)

@app.route("/delete/<filename>", methods=["DELETE"])
@login_required
def delete_file(filename):
    file_path = os.path.join(CSV_FOLDER, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return jsonify({"success": True, "message": f"{filename} deleted successfully"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    else:
        return jsonify({"success": False, "message": "File not found"}), 404

# ======================
# Template Routes
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


# ======================
# Upload CSV
# ======================
SAVE_DIR = os.path.join(os.getcwd(), "EmailsInfo")
os.makedirs(SAVE_DIR, exist_ok=True)

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return "No file part", 400

    file = request.files["file"]

    if file.filename == "":
        return "No selected file", 400

    if file and file.filename.endswith(".csv"):
        # Read uploaded CSV into DataFrame
        df = pd.read_csv(file)

        # Save with same filename into EmailsInfo folder
        save_path = os.path.join(SAVE_DIR, file.filename)
        df.to_csv(save_path, index=False, encoding="utf-8")

        return f"✅ File processed and saved as {save_path}"

    return "Only CSV files are allowed", 400


if __name__ == "__main__":
    app.run(debug=True)
