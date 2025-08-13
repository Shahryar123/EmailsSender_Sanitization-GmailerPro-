from flask import Flask, render_template, request, redirect, url_for, flash, session, get_flashed_messages
import subprocess
from send_emails import run_email_sender

app = Flask(__name__)
app.secret_key = "super_secret_key"  # Required for session and flash messages

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

            try:
                if email_option == "date" and start_date and end_date:
                    subprocess.run(
                        ["python", "gmail_to_csv.py", "date", start_date, end_date],
                        check=True
                    )
                    flash(f"CSV generated for emails from {start_date} to {end_date}!", "success")
                else:
                    subprocess.run(["python", "gmail_to_csv.py", "all"], check=True)
                    flash("CSV with all emails generated successfully!", "success")
            except subprocess.CalledProcessError:
                flash("Failed to generate CSV file.", "error")

        elif "send_email" in request.form:
            template = request.form.get("template_name")
            email_option = session.get('email_option', 'all')
             # Get checkbox value (True if checked, False if not)
            allow_duplicates = request.form.get("allow_duplicates") == "1"
            
            try:
                logs = run_email_sender(template_name=template, allow_duplicates=allow_duplicates)
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

if __name__ == "__main__":
    app.run(debug=True)
