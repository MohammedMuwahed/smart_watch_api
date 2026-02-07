import os
import time
import requests
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv('FITBIT_CLIENT_ID')
CLIENT_SECRET = os.getenv('FITBIT_CLIENT_SECRET')
REDIRECT_URI = os.getenv('FITBIT_REDIRECT_URI')
ACCESS_TOKEN = os.getenv('FITBIT_ACCESS_TOKEN')
REFRESH_TOKEN = os.getenv('FITBIT_REFRESH_TOKEN')
USER_ID = os.getenv('FITBIT_USER_ID')

TOKEN_URL = 'https://api.fitbit.com/oauth2/token'
HEART_RATE_URL = f'https://api.fitbit.com/1/user/{USER_ID}/activities/heart/date/today/1d/1sec.json'

# Scopes required for heart rate
SCOPE = ['heartrate', 'activity', 'profile']

# Helper: Refresh token if needed
def refresh_token(session):
    extra = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
    token = session.refresh_token(TOKEN_URL, refresh_token=REFRESH_TOKEN, **extra)
    return token

# Helper: Get current heart rate
def get_current_heartrate(session):
    resp = session.get(HEART_RATE_URL)
    if resp.status_code == 200:
        data = resp.json()
        # Extract latest heart rate value
        try:
            dataset = data['activities-heart-intraday']['dataset']
            if dataset:
                latest = dataset[-1]
                return latest['value'], latest['time']
            else:
                return None, None
        except Exception:
            return None, None
    elif resp.status_code == 429:
        print('Rate limit exceeded. Waiting before retrying...')
        time.sleep(30)
        return get_current_heartrate(session)
    else:
        print(f'Error: {resp.status_code} {resp.text}')
        return None, None

def main(interval=30):
    token = {
        'access_token': ACCESS_TOKEN,
        'refresh_token': REFRESH_TOKEN,
        'token_type': 'Bearer',
        'expires_in': 3600,
    }
    session = OAuth2Session(CLIENT_ID, token=token, auto_refresh_url=TOKEN_URL,
                           auto_refresh_kwargs={
                               'client_id': CLIENT_ID,
                               'client_secret': CLIENT_SECRET,
                           },
                           token_updater=None)
    print('Starting Fitbit heart rate fetcher...')
    while True:
        hr, t = get_current_heartrate(session)
        if hr is not None:
            print(f'[{t}] Current Heart Rate: {hr} bpm')
        else:
            print('No heart rate data available.')
        time.sleep(interval)

if __name__ == '__main__':
    # Set the interval in seconds (default: 60)
    main(interval=30)
