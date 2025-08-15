import datetime
import os
from flask import Flask, jsonify, render_template,send_from_directory, request, redirect, url_for, flash, session, get_flashed_messages
import subprocess
from send_emails import run_email_sender



app = Flask(__name__)
app.secret_key = "super_secret_key"  # Required for session and flash messages

@app.route("/set-account", methods=["POST"])
def set_account():
    selected = request.form.get("smtp_account")
    if selected:
        session["smtp_account"] = selected
    return ("", 204)  # No content response


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "generate_csv" in request.form:
            email_option = request.form.get("email_option")  # 'all' or 'date'
            start_date = request.form.get("start_date")
            end_date = request.form.get("end_date")

            # Save the selections in session so they're remembered
            session['email_option'] = email_option
            session['start_date'] = start_date
            session['end_date'] = end_date
            account_number = session.get("smtp_account", "1")

            try:
                if email_option == "date" and start_date and end_date:
                    subprocess.run(
                        ["python", "gmail_to_csv.py", "date", start_date, end_date, account_number],
                        check=True
                    )
                    flash(f"CSV generated for emails from {start_date} to {end_date}!", "success")
                else:
                    subprocess.run(
                        ["python", "gmail_to_csv.py", "all", account_number],
                        check=True
                    )
                    flash("CSV with all emails generated successfully!", "success")
            except subprocess.CalledProcessError:
                flash("Failed to generate CSV file.", "error")

        elif "send_email" in request.form:
            template = request.form.get("template_name")
            email_option = session.get('email_option', 'all')
             # Get checkbox value (True if checked, False if not)
            allow_duplicates = request.form.get("allow_duplicates") == "1"
            
            # Get selected account (default to 1 if not set)
            account_number = session.get("smtp_account", "1")

            try:
                logs = run_email_sender(template_name=template,
                                        allow_duplicates=allow_duplicates,
                                        account_number=account_number)
                for log in logs:
                    if "❌" in log or "Error" in log:
                        flash(log, "error")
                    else:
                        flash(log, "success")
            except Exception as e:
                flash(f"Failed to send emails: {e}", "error")

        return redirect(url_for("index"))

    # Load last values for the form
    last_email_option = session.get('email_option', 'all')
    last_start_date = session.get('start_date', '')
    last_end_date = session.get('end_date', '')

    messages = [
        {'category': cat, 'message': msg}
        for cat, msg in get_flashed_messages(with_categories=True)
    ]
    return render_template(
        "index.html",
        last_num_emails=last_email_option,  # still using this name for backward compatibility
        last_start_date=last_start_date,
        last_end_date=last_end_date,
        flash_messages=messages
    )

# // Get files from EmailsInfo directory
CSV_FOLDER = os.path.join(os.getcwd(), "EmailsInfo")


@app.route("/list_csv")
def list_csv():
    files = []
    if os.path.exists(CSV_FOLDER):
        csv_files = [
            f for f in os.listdir(CSV_FOLDER) if f.endswith(".csv")
        ]
        # Sort by creation time (newest first)
        csv_files.sort(
            key=lambda f: os.path.getctime(os.path.join(CSV_FOLDER, f)),
            reverse=True
        )
        
        for idx, file in enumerate(csv_files, start=1):
            file_path = os.path.join(CSV_FOLDER, file)
            created_time = datetime.datetime.fromtimestamp(
                os.path.getctime(file_path)
            ).strftime("%Y-%m-%d %H:%M:%S")
            files.append({
                "sr_no": idx,
                "name": file,
                "created": created_time
            })
    return jsonify(files)


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(CSV_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
