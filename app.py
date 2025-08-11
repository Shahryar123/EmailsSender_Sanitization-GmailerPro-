from flask import Flask, render_template, request, redirect, url_for, flash, session, get_flashed_messages
import subprocess
from send_emails import run_email_sender

app = Flask(__name__)
app.secret_key = "super_secret_key"  # Required for session and flash messages

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "generate_csv" in request.form:
            num_emails = request.form.get("num_emails")
            try:
                subprocess.run(["python", "gmail_to_csv.py", num_emails], check=True)
                session['num_emails'] = num_emails  # store selection in session
                flash(f"CSV with {num_emails} records generated successfully!", "success")
            except subprocess.CalledProcessError:
                flash("Failed to generate CSV file.", "error")
                pass
        elif "send_email" in request.form:
            template = request.form.get("template_name")
            num_emails = session.get('num_emails', 'all')
            try:
                logs = run_email_sender(template_name=template)  # returns list of messages
                # Flash each message with 'success' or 'error' based on content:
                for log in logs:
                    if "❌" in log or "Error" in log:
                        flash(log, "error")
                    else:
                        flash(log, "success")
            except Exception as e:
                flash(f"Failed to send emails: {e}", "error")

        return redirect(url_for("index"))

    last_num_emails = session.get('num_emails', '5')
    messages = [{'category': cat, 'message': msg} for cat, msg in get_flashed_messages(with_categories=True)]
    return render_template("index.html", last_num_emails=last_num_emails, flash_messages=messages)

if __name__ == "__main__":
    app.run(debug=True)
