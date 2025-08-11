# 📧 Gmail Email Automation Tool

This project automates:
1. 📥 Reading emails from a Gmail account using the Gmail API.
2. 📤 Sending bulk emails using Gmail SMTP with an App Password.

It is designed for clients or developers to easily set up and run the automation locally.

---

## ✨ Features
- 📬 **Read Gmail messages** via the Gmail API.
- 📢 **Send emails** using Gmail SMTP.
- 📄 **Template-based sending** (e.g., Notification or Welcome emails).
- 🗂 **CSV generation** of recipients.
- 🚫 **Duplicate prevention** for certain templates.

---

## 🛠 Prerequisites
Before running the project, make sure you have:
- 🐍 Python 3.7+
- ☁️ Google Cloud Project with Gmail API enabled.
- 🔑 OAuth 2.0 credentials JSON file.
- 📧 Gmail account with:
  - ✅ **2-Step Verification enabled**
  - 🔐 **App Password generated**

---

## ⚙️ Setup Instructions

### 1️⃣ Enable Gmail API & Create OAuth Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a **New Project** (or use an existing one).
3. Enable the **Gmail API**:
   - Go to **APIs & Services > Library**.
   - Search for **Gmail API** and enable it.
4. Create OAuth 2.0 credentials:
   - **APIs & Services > Credentials > Create Credentials > OAuth Client ID**.
   - Application type: **Desktop App**.
   - Download the JSON file and rename it to `credentials.json`.
   - Place `credentials.json` in your project root.

**Required OAuth Scopes:**
```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify"
]
```

---

### 2️⃣ Generate Gmail App Password
1. Go to [Google Account Security Settings](https://myaccount.google.com/security).
2. Enable **2-Step Verification** (if not already enabled).
3. Under **App Passwords**, generate a new password for **Mail** on your device.
4. Save this password — you’ll use it in `app.py` for SMTP authentication.

---

### 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

---

### 4️⃣ Run the Flask App
```bash
python app.py
```
- The app will start at `http://127.0.0.1:5000/`.
- Open the link in your browser.

---

## 📂 Folder Structure
```
project-root/
│
├── app.py                # Main Flask application
├── send_emails.py        # Email sending logic
├── gmail_to_csv.py       # CSV generation from Gmail
├── templates/            # HTML templates for emails & UI
│   ├── index.html
│   ├── Template_01.html
│   ├── Template_02.html
├── credentials.json      # OAuth credentials (from Google Cloud Console)
├── token.json            # Generated after OAuth authentication
├── requirements.txt      # Python dependencies
└── README.md             # Project documentation
```

---

## 📌 Usage Notes
- If you choose **Template 02 (Welcome)**, the system will skip sending emails to recipients who have already received it before.
- To reset the authentication, delete `token.json` and re-run the app.

---

## 📜 License
This project is licensed under the MIT License — feel free to modify and use.

---

💡 **Tip:** Keep your credentials safe and never commit `credentials.json` or `token.json` to a public repository.
