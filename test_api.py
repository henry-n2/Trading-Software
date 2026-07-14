import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "") 

url = "https://api.upstox.com/v2/market-quote/quotes"
headers = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}
# requests handles the URL encoding (like %20 for spaces) automatically
params = {'instrument_key': 'NSE_INDEX|Nifty 50'}

print("Sending request to Upstox API...")
response = requests.get(url, headers=headers, params=params)

print("\n--- API RESPONSE ---")
print(f"Status Code: {response.status_code}")
print(f"Raw Data: {response.text}")
print("--------------------\n")