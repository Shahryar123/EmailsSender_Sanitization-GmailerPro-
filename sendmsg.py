import requests

ACCESS_TOKEN = "EAAKxLIAr5q0BPXpmuFJOEcy1eLZAmlPYvd0ubMCMo4uoWNVpDbepmvWtNQMTboizMGFVab5qFYurxOLKxMtiy3tuLr6AjfBwggqPphwpMW33KahWqc76OUPsE6KNICi3U2aeebyRu9QYFnQMiIi1A1eiysuy0WI6k41NdUDXX8eJG7e7swq2ylnFZAf05SAG0ceFkGlrcNcwGJVsz7lqmI4vwftNa2UWFZAHJZCB9VAYvtIZD"
PHONE_NUMBER_ID = "827984493724347"
API_VERSION = "v22.0"  # use same version Meta gave you

WHATSAPP_API_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

def send_template_message(to_number: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "hello_world",   # Default approved template
            "language": {"code": "en_US"}
        }
    }

    response = requests.post(WHATSAPP_API_URL, headers=HEADERS, json=payload)
    print(response.status_code, response.json())

def send_freeform_message(to_number: str, message: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message}
    }
    response = requests.post(WHATSAPP_API_URL, headers=HEADERS, json=payload)
    print(response.status_code, response.json())



def send_custom_template(to_number: str, name: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "welcome_msg",   # <-- your template name
            "language": {"code": "en_US"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": name}  # replaces {{1}}
                    ]
                }
            ]
        }
    }

    response = requests.post(WHATSAPP_API_URL, headers=HEADERS, json=payload)
    print(response.status_code, response.json())


if __name__ == "__main__":
    send_template_message("923041203011")
    # send_freeform_message("923012620841", "Hello 👋 freeform message test!")
    # send_custom_template("923012620841", "Shahryar")


