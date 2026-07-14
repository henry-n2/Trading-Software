from curl_cffi import requests
import time
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Initialize lists to store our live data
times = []
nifty_prices = []
ce_prices = []
pe_prices = []

# --- 1. THE LIVE DATA FETCHER ---
def fetch_nse_data():
    """Fetches Live Nifty Spot, ATM CE, and ATM PE bypassing TLS Fingerprinting."""
    url_home = "https://www.nseindia.com"
    url_oc = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    
    # Impersonate Chrome to bypass NSE firewall
    session = requests.Session(impersonate="chrome110")
    
    try:
        session.get(url_home, timeout=10)
        time.sleep(1.5) # Human delay
        
        response = session.get(
            url_oc, 
            timeout=10, 
            headers={"Referer": "https://www.nseindia.com/option-chain"}
        )
        
        if response.status_code == 200:
            data = response.json()
            nifty_spot = data['records']['underlyingValue']
            nearest_expiry = data['records']['expiryDates'][0]
            atm_strike = round(nifty_spot / 50) * 50
            
            ce_price, pe_price = None, None
            
            for item in data['records']['data']:
                if item['strikePrice'] == atm_strike and item['expiryDate'] == nearest_expiry:
                    ce_price = item.get('CE', {}).get('lastPrice', 0)
                    pe_price = item.get('PE', {}).get('lastPrice', 0)
                    break
                    
            return nifty_spot, ce_price, pe_price, atm_strike, nearest_expiry
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] HTTP {response.status_code}. Retrying...")
            return None, None, None, None, None
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection error: {e}")
        return None, None, None, None, None


# --- 2. THE CHART UI SETUP ---
plt.style.use('dark_background')
plt.ion() # Turn on interactive mode for live updating
fig, ax1 = plt.subplots(figsize=(12, 6), dpi=100)
ax2 = ax1.twinx() # The critical secondary axis

# Define our professional chart colors
COLOR_NIFTY = '#f1c40f' # Yellow (Spot)
COLOR_CE = '#2ecc71'    # Green (Call)
COLOR_PE = '#e74c3c'    # Red (Put)
BG_COLOR = '#121212'

fig.patch.set_facecolor(BG_COLOR)
ax1.set_facecolor(BG_COLOR)

print("Booting Live NIFTY Options Matrix... Press Ctrl+C in terminal to stop.")
print("Fetching first data point (this takes a few seconds)...")

# --- 3. THE LIVE LOOP ---
try:
    while True:
        spot, ce, pe, atm, expiry = fetch_nse_data()
        
        if spot and ce and pe:
            current_time = datetime.now()
            
            times.append(current_time)
            nifty_prices.append(spot)
            ce_prices.append(ce)
            pe_prices.append(pe)
            
            # Keep the last 120 data points (approx 1 hour of data at 30s intervals)
            if len(times) > 120:
                times.pop(0)
                nifty_prices.pop(0)
                ce_prices.pop(0)
                pe_prices.pop(0)
            
            # Wipe the canvas to draw the new data
            ax1.clear()
            ax2.clear()
            
            # RE-APPLY STYLING (Since clear() removes it)
            ax1.set_facecolor(BG_COLOR)
            
            # Plot NIFTY Spot on Left Axis
            ax1.plot(times, nifty_prices, color=COLOR_NIFTY, linewidth=2, label=f'NIFTY Spot ({spot})')
            ax1.set_ylabel('NIFTY Spot Price', color=COLOR_NIFTY, fontsize=11, fontweight='bold')
            ax1.tick_params(axis='y', labelcolor=COLOR_NIFTY)
            ax1.grid(True, linestyle=':', alpha=0.2, color='#ffffff')
            
            # Plot Options on Right Axis
            ax2.plot(times, ce_prices, color=COLOR_CE, linewidth=1.5, label=f'ATM CE ({ce})')
            ax2.plot(times, pe_prices, color=COLOR_PE, linewidth=1.5, label=f'ATM PE ({pe})')
            ax2.set_ylabel('Option Premium (₹)', color='#ffffff', fontsize=11, fontweight='bold')
            ax2.tick_params(axis='y', labelcolor='#ffffff')
            
            # Format X-Axis Time (HH:MM:SS)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            fig.autofmt_xdate()
            
            # Combine Legends
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', frameon=True, facecolor='#1e1e1e', edgecolor='#444444')
            
            # Dynamic Title
            plt.title(f"LIVE: NIFTY Relative Strength Matrix | ATM Strike: {atm} | Expiry: {expiry}", 
                      fontsize=12, fontweight='bold', pad=15, color='#ffffff')
            
            plt.tight_layout()
            
            # Force Matplotlib to render the new frame
            fig.canvas.draw()
            fig.canvas.flush_events()
            
            print(f"[{current_time.strftime('%H:%M:%S')}] NIFTY: {spot} | {atm} CE: {ce} | {atm} PE: {pe}")
            
        # Hard delay to prevent the WAF from banning your IP
        time.sleep(30)
        
except KeyboardInterrupt:
    print("\nLive tracking stopped by user.")
    plt.ioff()
    plt.show() # Keeps the final graph open after stopping the loop