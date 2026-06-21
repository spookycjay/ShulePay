import os
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY')
CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET')
SHORTCODE = os.getenv('MPESA_SHORTCODE')
PASSKEY = os.getenv('MPESA_PASSKEY')
CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL')
MPESA_ENV = os.getenv('MPESA_ENV', 'sandbox')

BASE_URL = (
    'https://sandbox.safaricom.co.ke'
    if MPESA_ENV == 'sandbox'
    else 'https://api.safaricom.co.ke'
)


def get_access_token():
    """Get OAuth access token from Daraja."""
    url = f'{BASE_URL}/oauth/v1/generate?grant_type=client_credentials'
    response = requests.get(
        url,
        auth=(CONSUMER_KEY, CONSUMER_SECRET),
        timeout=30
    )
    response.raise_for_status()
    return response.json()['access_token']


def generate_password():
    """Generate the base64 password required by Daraja STK Push."""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f'{SHORTCODE}{PASSKEY}{timestamp}'
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def stk_push(phone_number, amount, account_ref, description):
    """
    Trigger STK Push to parent's phone.
    
    phone_number: format 2547XXXXXXXX (no + or leading 0)
    amount: integer (KSh)
    account_ref: e.g. student admission number
    description: e.g. 'School Fees Payment'
    """
    token = get_access_token()
    password, timestamp = generate_password()

    phone = str(phone_number).strip()
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif phone.startswith('+'):
        phone = phone[1:]

    payload = {
        'BusinessShortCode': SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': phone,
        'PartyB': SHORTCODE,
        'PhoneNumber': phone,
        'CallBackURL': CALLBACK_URL,
        'AccountReference': account_ref,
        'TransactionDesc': description
    }

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    url = f'{BASE_URL}/mpesa/stkpush/v1/processrequest'
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    return response.json()

if __name__ == "__main__":
    try:
        token = get_access_token()
        print("ACCESS TOKEN:", token)
    except Exception as e:
        print("ERROR:", e)