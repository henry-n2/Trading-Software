

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import time
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
st.set_page_config(layout="wide", page_title="NIFTY Live Crossover")
st.title("NIFTY + ATM CALL & PUT PRICE CROSSOVER")

# Try to get access token from environment variables or Streamlit secrets
ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
if not ACCESS_TOKEN and "UPSTOX_ACCESS_TOKEN" in st.secrets:
    ACCESS_TOKEN = st.secrets["UPSTOX_ACCESS_TOKEN"]

# Fallback: allow user to input token in Streamlit sidebar
if not ACCESS_TOKEN:
    ACCESS_TOKEN = st.sidebar.text_input("Enter your Upstox Access Token:", type="password")
    if not ACCESS_TOKEN:
        st.info("Please set the UPSTOX_ACCESS_TOKEN environment variable in .env, add it to Streamlit secrets, or enter it in the sidebar to fetch data.")
        st.stop()

HEADERS = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}

# Initialize session state for charting history
if 'market_data' not in st.session_state:
    st.session_state.market_data = pd.DataFrame(columns=['Time', 'Nifty_Spot', 'ATM_CE', 'ATM_PE'])
    
# --- API PIPELINE FUNCTIONS ---
def get_spot_price():
    """Fetches live Nifty 50 Spot price"""
    url = "https://api.upstox.com/v2/market-quote/quotes"
    params = {'instrument_key': 'NSE_INDEX|Nifty 50'}
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 200:
            data = response.json().get('data', {})
            # Look for Nifty 50 in both known Upstox return formats
            for k, v in data.items():
                if "Nifty 50" in k:
                    return v.get('last_price')
        else:
            st.sidebar.error(f"Spot Error: {response.text}")
    except Exception as e:
        st.sidebar.error(f"Network Error (Spot): {e}")
    return None

def get_nearest_expiry_keys(atm_strike):
    """Dynamically maps the exact instrument keys for the closest ATM expiry."""
    url = "https://api.upstox.com/v2/option/contract"
    params = {'instrument_key': 'NSE_INDEX|Nifty 50'}
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 200:
            contracts = response.json().get('data', [])
            if not contracts:
                st.sidebar.error("Contracts API returned an empty list.")
                return None, None, None
                
            # Safely cast strike prices to floats to ensure matching
            atm_contracts = [c for c in contracts if float(c.get('strike_price', -1)) == float(atm_strike)]
            if not atm_contracts:
                st.sidebar.error(f"No contracts found matching ATM Strike {atm_strike}.")
                return None, None, None
                
            # Sort expiries to find the closest upcoming date
            expiries = sorted(list(set([c.get('expiry') for c in atm_contracts if c.get('expiry')])))
            if not expiries:
                return None, None, None
                
            nearest_expiry = expiries[0]
            
            ce_key, pe_key = None, None
            for c in atm_contracts:
                if c.get('expiry') == nearest_expiry:
                    if c.get('instrument_type') == 'CE':
                        ce_key = c.get('instrument_key')
                    elif c.get('instrument_type') == 'PE':
                        pe_key = c.get('instrument_key')
                        
            return nearest_expiry, ce_key, pe_key
        else:
            st.sidebar.error(f"Contracts Error: {response.text}")
    except Exception as e:
        st.sidebar.error(f"Network Error (Contracts): {e}")
    return None, None, None

def get_option_prices(ce_key, pe_key):
    """Fetches live last traded prices for selected option keys by inspecting the instrument_token."""
    url = "https://api.upstox.com/v2/market-quote/quotes"
    params = {'instrument_key': f"{ce_key},{pe_key}"}
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 200:
            data = response.json().get('data', {})
            
            ce_price = None
            pe_price = None
            
            # Iterate through the returned nested dictionaries
            for symbol_key, payload in data.items():
                token = payload.get('instrument_token', '')
                
                # Match the token inside the payload exactly against our requested keys
                if token == ce_key:
                    ce_price = payload.get('last_price')
                elif token == pe_key:
                    pe_price = payload.get('last_price')
            
            if ce_price is None or pe_price is None:
                st.sidebar.error("Prices not found using instrument_token mapping.")
                
            return ce_price, pe_price
        else:
            st.sidebar.error(f"Options Quote Error: {response.text}")
    except Exception as e:
        st.sidebar.error(f"Network Error (Options): {e}")
    return None, None

# --- MAIN DASHBOARD LOOP ---
placeholder = st.empty()

while True:
    with placeholder.container():
        current_time = datetime.now().strftime("%H:%M:%S")
        spot_price = get_spot_price()
        
        if spot_price:
            atm_strike = round(spot_price / 50) * 50
            
            # Cache the keys so we don't spam the heavy contracts API
            if 'current_atm' not in st.session_state or st.session_state.current_atm != atm_strike:
                expiry, ce_key, pe_key = get_nearest_expiry_keys(atm_strike)
                if ce_key and pe_key:
                    st.session_state.current_atm = atm_strike
                    st.session_state.ce_key = ce_key
                    st.session_state.pe_key = pe_key
                    st.session_state.expiry = expiry
            
            # Pull prices once valid keys are indexed
            if 'ce_key' in st.session_state and 'pe_key' in st.session_state:
                ce_price, pe_price = get_option_prices(st.session_state.ce_key, st.session_state.pe_key)
                
                # Only plot if we successfully extracted valid numbers
                if ce_price is not None and pe_price is not None:
                    st.sidebar.success(f"Connected! Expiry: {st.session_state.expiry} | ATM Strike: {atm_strike}")
                    
                    new_row = pd.DataFrame({
                        'Time': [current_time], 
                        'Nifty_Spot': [spot_price], 
                        'ATM_CE': [ce_price], 
                        'ATM_PE': [pe_price]
                    })
                    st.session_state.market_data = pd.concat([st.session_state.market_data, new_row], ignore_index=True).tail(150)
                    df = st.session_state.market_data
                    
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    
                    fig.add_trace(
                        go.Scatter(x=df['Time'], y=df['Nifty_Spot'], name="NIFTY (Spot)", line=dict(color='#F4D03F', width=2)),
                        secondary_y=False,
                    )
                    fig.add_trace(
                        go.Scatter(x=df['Time'], y=df['ATM_CE'], name="ATM CALL (CE)", line=dict(color='#2ECC71', width=2)),
                        secondary_y=True,
                    )
                    fig.add_trace(
                        go.Scatter(x=df['Time'], y=df['ATM_PE'], name="ATM PUT (PE)", line=dict(color='#E74C3C', width=2)),
                        secondary_y=True,
                    )
                    
                    fig.update_layout(
                        plot_bgcolor='#0E1117',
                        paper_bgcolor='#0E1117',
                        font=dict(color='white'),
                        xaxis_title="Time",
                        hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        margin=dict(l=40, r=40, t=40, b=40)
                    )
                    
                    fig.update_yaxes(title_text="NIFTY Spot", secondary_y=False, showgrid=False, zeroline=False)
                    fig.update_yaxes(title_text="Option Price (₹)", secondary_y=True, showgrid=True, gridcolor='#2C3E50', zeroline=False)
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Parsing F&O data tokens...")
            else:
                 st.info("Locating closest weekly contracts...")
        else:
            st.warning("Connecting to NIFTY Spot stream...")
            
    # Poll interval
    time.sleep(5)