import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time
from datetime import datetime, timedelta, timezone, time as dtime
import os
import threading
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- CONFIGURATION RESOLVER ---
def load_config_value(key_name):
    try:
        if key_name in st.secrets:
            val = st.secrets[key_name]
            if val and val.strip():
                return val.strip()
    except Exception:
        pass
    val = os.getenv(key_name)
    if val and val.strip():
        return val.strip()
    load_dotenv()
    val = os.getenv(key_name)
    if val and val.strip():
        return val.strip()
    if os.path.exists(".env.example"):
        load_dotenv(".env.example")
        val = os.getenv(key_name)
        if val and val.strip():
            return val.strip()
    return None

GSHEET_WEBAPP_URL = load_config_value("GSHEET_WEBAPP_URL")
GSHEET_EXPORT_URL = load_config_value("GSHEET_EXPORT_URL")

# --- CONFIGURATION ---
st.set_page_config(layout="wide", page_title="NIFTY Live Crossover")

# --- CUSTOM CSS INJECTION ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #0d0f12;
        color: #e2e8f0;
    }
    
    /* Premium Metric Card Styling */
    div[data-testid="metric-container"] {
        background-color: #141822;
        border: 1px solid #1e2433;
        padding: 20px 24px;
        border-radius: 12px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.45);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        border-color: #2c354d;
    }
    
    div[data-testid="stMetricValue"] > div {
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #ffffff !important;
    }
    
    div[data-testid="stMetricLabel"] > div {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #8f929d !important;
    }
    
    /* Sidebar Border & Styling */
    [data-testid="stSidebar"] {
        background-color: #080a0f;
        border-right: 1px solid #141822;
    }
    
    /* Connection Status Widget */
    .status-card {
        background: linear-gradient(135deg, #131722 0%, #0a0d14 100%);
        border: 1px solid #1e2433;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 25px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    }
    /* Style Plotly ModeBar controls toolbar */
    .modebar-container {
        top: 5px !important;
        left: 50% !important;
        right: auto !important;
        transform: translateX(-50%) !important;
        background: #141822 !important;
        border: 1px solid #1e2433 !important;
        border-radius: 6px !important;
        padding: 3px 6px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4) !important;
    }
    
    .modebar-btn svg {
        transform: scale(1.35) !important;
        fill: #94a3b8 !important;
    }
    
    .modebar-btn:hover svg {
        fill: #F4D03F !important;
    }
    
    .modebar-btn {
        padding: 4px 6px !important;
        margin: 0 2px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Header Section
st.markdown(
    """
    <div style="background: linear-gradient(90deg, #141822 0%, #0d0f12 100%); padding: 22px 30px; border-radius: 12px; margin-bottom: 28px; border: 1px solid #1e2433;">
        <h1 style="margin: 0; font-weight: 700; color: #ffffff; font-size: 2.1rem; letter-spacing: -0.03em;">NIFTY 50 Live Option Matrix</h1>
        <p style="margin: 6px 0 0 0; color: #8f929d; font-size: 1.0rem;">Real-time ATM Call & Put premium crossover tracking during Indian market hours (09:15 - 15:30 IST).</p>
    </div>
    """,
    unsafe_allow_html=True
)

db_lock = threading.Lock()

# --- SHARED STATE FOR STREAMLIT CONCURRENCY ---
class BackgroundState:
    def __init__(self):
        self.status = "Initializing..."
        self.expiry = "N/A"
        self.atm_strike = "N/A"
        self.last_update = "N/A"
        self.error = None
        self.latest_spot = 0.0
        self.latest_ce = 0.0
        self.latest_pe = 0.0
        
        # Load existing history from Google Sheets
        loaded = False
        if GSHEET_EXPORT_URL:
            try:
                self.df = pd.read_csv(GSHEET_EXPORT_URL).tail(3600)
                print(f"Loaded {len(self.df)} historical points from Google Sheets.")
                loaded = True
            except Exception as e:
                print(f"Failed to load from Google Sheets: {e}")
                
        if not loaded:
            self.df = pd.DataFrame(columns=['Time', 'Nifty_Spot', 'ATM_CE', 'ATM_PE'])

@st.cache_resource
def get_shared_state_v2():
    return BackgroundState()

# --- TOKEN RESOLVER ---
ACCESS_TOKEN = load_config_value("UPSTOX_ACCESS_TOKEN")
if not ACCESS_TOKEN:
    st.error("❌ Access Token not found! Please set `UPSTOX_ACCESS_TOKEN` in Streamlit secrets, or in a local `.env` or `.env.example` file.")
    st.stop()

# --- TIMEZONE AND HOURS HELPER ---
def get_ist_now():
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist_tz)

def is_market_hours():
    now_ist = get_ist_now()
    
    # Weekday check (Saturday=5, Sunday=6)
    if now_ist.weekday() >= 5:
        return False, "Market Closed (Weekend)"
        
    current_time_val = now_ist.time()
    start_time = dtime(9, 15)
    end_time = dtime(15, 30)
    
    if not (start_time <= current_time_val <= end_time):
        return False, "Market Closed (Outside Hours: 09:15 - 15:30 IST)"
        
    return True, "Market Open"

# --- API PIPELINE FUNCTIONS (THREAD-SAFE) ---
def get_spot_price(token):
    """Fetches live Nifty 50 Spot price"""
    url = "https://api.upstox.com/v2/market-quote/quotes"
    params = {'instrument_key': 'NSE_INDEX|Nifty 50'}
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get('data', {})
            for k, v in data.items():
                if "Nifty 50" in k:
                    return v.get('last_price')
        elif response.status_code == 401:
            state = get_shared_state_v2()
            state.error = "❌ Upstox Access Token is expired or unauthorized! Please generate a new daily token and update your secrets."
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Auth Error: Token is expired or invalid (HTTP 401)")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Spot Error: HTTP {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Network Error (Spot): {e}")
    return None

def get_nearest_expiry_keys(token, atm_strike):
    """Dynamically maps the exact instrument keys for the closest ATM expiry."""
    url = "https://api.upstox.com/v2/option/contract"
    params = {'instrument_key': 'NSE_INDEX|Nifty 50'}
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            contracts = response.json().get('data', [])
            if not contracts:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Contracts API returned empty list.")
                return None, None, None
                
            atm_contracts = [c for c in contracts if float(c.get('strike_price', -1)) == float(atm_strike)]
            if not atm_contracts:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No contracts found matching ATM Strike {atm_strike}.")
                return None, None, None
                
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
        elif response.status_code == 401:
            state = get_shared_state_v2()
            state.error = "❌ Upstox Access Token is expired or unauthorized! Please generate a new daily token and update your secrets."
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Auth Error: Token is expired or invalid (HTTP 401)")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Contracts Error: HTTP {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Network Error (Contracts): {e}")
    return None, None, None

def get_option_prices(token, ce_key, pe_key):
    """Fetches live option prices using token mappings."""
    url = "https://api.upstox.com/v2/market-quote/quotes"
    params = {'instrument_key': f"{ce_key},{pe_key}"}
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get('data', {})
            
            ce_price = None
            pe_price = None
            
            for symbol_key, payload in data.items():
                tok = payload.get('instrument_token', '')
                if tok == ce_key:
                    ce_price = payload.get('last_price')
                elif tok == pe_key:
                    pe_price = payload.get('last_price')
                    
            return ce_price, pe_price
        elif response.status_code == 401:
            state = get_shared_state_v2()
            state.error = "❌ Upstox Access Token is expired or unauthorized! Please generate a new daily token and update your secrets."
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Auth Error: Token is expired or invalid (HTTP 401)")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Options Quote Error: HTTP {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Network Error (Options): {e}")
    return None, None

# --- BACKGROUND DATA COLLECTOR ---
def background_worker(token):
    state = get_shared_state_v2()
    state.status = "Started"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Background collector thread started.")
    
    current_atm = None
    ce_key = None
    pe_key = None
    expiry = None
    
    last_csv_write_time = time.time()
    pending_rows = []
    
    while True:
        try:
            # 1. Market Hour Pre-check
            is_open, time_status = is_market_hours()
            if not is_open:
                state.status = time_status
                state.error = None
                time.sleep(1) 
                continue
            
            current_time = get_ist_now().strftime("%H:%M:%S")
            spot_price = get_spot_price(token)
            
            if spot_price:
                atm_strike = round(spot_price / 50) * 50
                
                # Fetch keys if strike changed or keys are missing
                if current_atm != atm_strike or not ce_key or not pe_key:
                    exp, ck, pk = get_nearest_expiry_keys(token, atm_strike)
                    if ck and pk:
                        current_atm = atm_strike
                        ce_key = ck
                        pe_key = pk
                        expiry = exp
                
                if ce_key and pe_key:
                    ce_price, pe_price = get_option_prices(token, ce_key, pe_key)
                    
                    if ce_price is not None and pe_price is not None:
                        # Store the high-fidelity 1s values in memory for UI metrics
                        state.latest_spot = spot_price
                        state.latest_ce = ce_price
                        state.latest_pe = pe_price
                        
                        new_row_dict = {
                            'Time': current_time, 
                            'Nifty_Spot': spot_price, 
                            'ATM_CE': ce_price, 
                            'ATM_PE': pe_price
                        }
                        pending_rows.append(new_row_dict)
                        
                        new_row_df = pd.DataFrame([new_row_dict])
                        
                        # Append to memory DataFrame, capped to last 3600 seconds (1 hour of detailed tick data)
                        state.df = pd.concat([state.df, new_row_df], ignore_index=True).tail(3600)
                        
                        # Periodic write to Google Sheets every 10 seconds
                        now = time.time()
                        if now - last_csv_write_time >= 10:
                            if GSHEET_WEBAPP_URL:
                                if pending_rows:
                                    try:
                                        response = requests.post(GSHEET_WEBAPP_URL, json=pending_rows, timeout=8)
                                        if response.status_code == 200:
                                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {len(pending_rows)} points to Google Sheets.")
                                            pending_rows.clear()
                                        else:
                                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Google Sheets Save Error: HTTP {response.status_code} - {response.text}")
                                    except Exception as e:
                                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Google Sheets Connection Error: {e}")
                            else:
                                pending_rows.clear()
                            last_csv_write_time = now
                            
                            # Flat price check (120 consecutive 1-second points = closed / halted)
                            if len(state.df) >= 120:
                                last_120 = state.df['Nifty_Spot'].tail(120).unique()
                                if len(last_120) == 1:
                                    state.status = "Market Closed (No price movement)"
                                else:
                                    state.status = "Running (Market Open)"
                            else:
                                state.status = "Running (Market Open)"
                        
                        state.expiry = expiry
                        state.atm_strike = current_atm
                        state.last_update = current_time
                        state.error = None
                    else:
                        if not state.error or not state.error.startswith("❌"):
                            state.error = "Error fetching CE/PE option premium prices"
                else:
                    if not state.error or not state.error.startswith("❌"):
                        state.error = f"Contract mapping failed for Strike {atm_strike}"
            else:
                if not state.error or not state.error.startswith("❌"):
                    state.error = "Nifty 50 spot price lookup failed"
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Background Thread Loop Exception: {e}")
            if not state.error or not state.error.startswith("❌"):
                state.error = str(e)
            
        # Poll interval is 1 second in background for high fidelity
        time.sleep(1)

@st.cache_resource
def start_background_collector(token):
    thread = threading.Thread(target=background_worker, args=(token,), daemon=True)
    thread.start()
    return thread

# Start background collection daemon
start_background_collector(ACCESS_TOKEN)

state = get_shared_state_v2()
df = state.df.copy()

# Render sidebar connection state with live prices
with st.sidebar:
    if state.error:
        st.markdown(
            f"""
            <div class="status-card" style="border-left: 5px solid #ef4444;">
                <h4 style="margin:0 0 10px 0;color:#ef4444;font-size:16px;">⚠️ Engine Alert</h4>
                <p style="margin:0;font-size:13px;color:#cbd5e1;line-height:1.4;">{state.error}</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""
            <div class="status-card" style="border-left: 5px solid #10b981;">
                <h4 style="margin:0 0 10px 0;color:#10b981;font-size:16px;">⚡ Live Core Engine</h4>
                <p style="margin:0 0 8px 0;font-size:13.5px;color:#e2e8f0;">
                    <strong>Engine Status:</strong> <br/><span style="color:#10b981;font-weight:600;">{state.status}</span>
                </p>
                <p style="margin:0 0 8px 0;font-size:13.5px;color:#e2e8f0;">
                    <strong>Weekly Expiry:</strong> <br/><span style="color:#3b82f6;font-weight:600;">{state.expiry}</span>
                </p>
                <p style="margin:0 0 8px 0;font-size:13.5px;color:#e2e8f0;">
                    <strong>ATM Strike Level:</strong> <br/><span style="color:#a855f7;font-weight:600;">{state.atm_strike}</span>
                </p>
                <hr style="border-color:#1e2433;margin:12px 0;"/>
                <p style="margin:0 0 6px 0;font-size:13px;color:#e2e8f0;">
                    <strong>Live Spot:</strong> <span style="color:#F4D03F;font-weight:600;float:right;">{state.latest_spot:,.2f}</span>
                </p>
                <p style="margin:0 0 6px 0;font-size:13px;color:#e2e8f0;">
                    <strong>Live Call (CE):</strong> <span style="color:#2ECC71;font-weight:600;float:right;">₹{state.latest_ce:,.2f}</span>
                </p>
                <p style="margin:0;font-size:13px;color:#e2e8f0;">
                    <strong>Live Put (PE):</strong> <span style="color:#E74C3C;font-weight:600;float:right;">₹{state.latest_pe:,.2f}</span>
                </p>
                <hr style="border-color:#1e2433;margin:12px 0;"/>
                <p style="margin:0;font-size:11.5px;color:#94a3b8;">
                    <strong>Last Sync:</strong> {state.last_update}
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown('<p style="font-size:12.5px;font-weight:700;color:#94a3b8;margin:18px 0 6px 0;text-transform:uppercase;letter-spacing:0.04em;">Auto Refresh Controls</p>', unsafe_allow_html=True)
        pause_refresh = st.toggle(
            "⏸️ Pause Chart Refresh", 
            value=False, 
            help="Pause auto-refreshing so you can draw trendlines, rectangles, pan, or zoom without resets. Background data logging remains active."
        )
        if not pause_refresh:
            refresh_interval = st.slider(
                "Refresh Interval (s)", 
                min_value=1, 
                max_value=20, 
                value=3, 
                step=1,
                help="Set how frequently the page pulls the latest ticks."
            )
        else:
            refresh_interval = 3

# Render dashboard charts and metrics
if not df.empty:
    # Convert Time column to datetime and clean NaTs to enable Plotly datetime axis auto-scaling
    today_str = get_ist_now().strftime("%Y-%m-%d")
    df['Datetime'] = pd.to_datetime(today_str + ' ' + df['Time'], errors='coerce')
    df = df.dropna(subset=['Datetime'])
    # Convert to standard space-separated string format YYYY-MM-DD HH:MM:SS for robust Plotly JS date-axis parsing
    df['Datetime_Str'] = df['Datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    col1, col2 = st.columns(2)
    
    # --- LEFT SIDE: Nifty 50 Rate and Nifty-only Chart ---
    with col1:
        st.subheader("NIFTY 50 Spot")
        
        # Metric shows live 1s rate
        live_spot = state.latest_spot if state.latest_spot > 0 else df['Nifty_Spot'].iloc[-1]
        plotted_spot = df['Nifty_Spot'].iloc[-1]
        
        change = live_spot - plotted_spot
        pct_change = (change / plotted_spot) * 100 if plotted_spot > 0 else 0.0
        
        st.metric(
            label="NSE NIFTY 50 Live",
            value=f"{live_spot:,.2f}",
            delta=f"{change:+.2f} ({pct_change:+.2f}%) since last printed tick" if abs(change) > 0.01 else "Flat"
        )
        
        # Graph of only Nifty 50 with gradient area fill
        fig_nifty = go.Figure()
        fig_nifty.add_trace(
            go.Scatter(
                x=df['Datetime_Str'].tolist(), 
                y=df['Nifty_Spot'], 
                name="NIFTY 50", 
                line=dict(color='#F4D03F', width=2),
                fill='tozeroy',
                fillcolor='rgba(244, 208, 63, 0.04)',
                mode='lines'
            )
        )
        
        # Add horizontal dashed line at latest spot price (Kite style)
        fig_nifty.add_shape(
            type="line",
            x0=df['Datetime_Str'].iloc[0],
            y0=live_spot,
            x1=df['Datetime_Str'].iloc[-1],
            y1=live_spot,
            line=dict(color='#F4D03F', width=1.5, dash="dash"),
        )
        
        # Add price badge on the right margin (Kite style)
        fig_nifty.add_annotation(
            x=df['Datetime_Str'].iloc[-1],
            y=live_spot,
            text=f"{live_spot:,.2f}",
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(color="black", size=9, weight="bold"),
            bgcolor='#F4D03F',
            bordercolor='#F4D03F',
            borderwidth=1,
            borderpad=3,
            align="left"
        )
        
        fig_nifty.update_layout(
            plot_bgcolor='#0d0f12',
            paper_bgcolor='#0d0f12',
            font=dict(family='Inter, sans-serif', color='#e2e8f0'),
            dragmode='pan',
            xaxis=dict(
                title="Time",
                type='date',
                tickformat='%H:%M',
                hoverformat='%H:%M:%S',
                showgrid=True,
                gridcolor='#1e2433',
                zeroline=False,
                showspikes=True,
                spikesnap="data",
                spikemode="across",
                spikethickness=1,
                spikecolor="#2c354d",
                spikedash="dash"
            ),
            yaxis=dict(
                title="Spot Price (INR)",
                showgrid=True,
                gridcolor='#1e2433',
                zeroline=False,
                showspikes=True,
                spikesnap="data",
                spikemode="across",
                spikethickness=1,
                spikecolor="#2c354d",
                spikedash="dash"
            ),
            hovermode="x unified",
            margin=dict(l=40, r=80, t=45, b=40),
            height=450
        )
        
        plotly_config = {
            'scrollZoom': True,
            'displaylogo': False,
            'modeBarButtonsToAdd': ['drawline', 'drawrect', 'eraseshape'],
            'displayModeBar': True
        }
        st.plotly_chart(fig_nifty, width='stretch', config=plotly_config, key="nifty_spot_chart")
        
    # --- RIGHT SIDE: Option Premium Crossover ---
    with col2:
        st.subheader("ATM Call & Put Crossover")
        
        # Metrics show live 1s rates
        live_ce = state.latest_ce if state.latest_ce > 0 else df['ATM_CE'].iloc[-1]
        plotted_ce = df['ATM_CE'].iloc[-1]
        change_ce = live_ce - plotted_ce
        
        live_pe = state.latest_pe if state.latest_pe > 0 else df['ATM_PE'].iloc[-1]
        plotted_pe = df['ATM_PE'].iloc[-1]
        change_pe = live_pe - plotted_pe
        
        subcol1, subcol2 = st.columns(2)
        with subcol1:
            st.metric(
                label=f"Call Premium (CE) - {state.atm_strike}",
                value=f"₹{live_ce:,.2f}",
                delta=f"{change_ce:+.2f} since last printed tick" if abs(change_ce) > 0.01 else "Flat"
            )
        with subcol2:
            st.metric(
                label=f"Put Premium (PE) - {state.atm_strike}",
                value=f"₹{live_pe:,.2f}",
                delta=f"{change_pe:+.2f} since last printed tick" if abs(change_pe) > 0.01 else "Flat"
            )
        
        # Options-only crossover graph with gradient area fills
        fig_options = go.Figure()
        fig_options.add_trace(
            go.Scatter(
                x=df['Datetime_Str'].tolist(), 
                y=df['ATM_CE'], 
                name="ATM CALL (CE)", 
                line=dict(color='#2ECC71', width=2),
                fill='tozeroy',
                fillcolor='rgba(46, 204, 113, 0.04)',
                mode='lines'
            )
        )
        fig_options.add_trace(
            go.Scatter(
                x=df['Datetime_Str'].tolist(), 
                y=df['ATM_PE'], 
                name="ATM PUT (PE)", 
                line=dict(color='#E74C3C', width=2),
                fill='tozeroy',
                fillcolor='rgba(231, 76, 60, 0.04)',
                mode='lines'
            )
        )
        
        # Add horizontal dashed line at latest Call price
        fig_options.add_shape(
            type="line",
            x0=df['Datetime_Str'].iloc[0],
            y0=live_ce,
            x1=df['Datetime_Str'].iloc[-1],
            y1=live_ce,
            line=dict(color='#2ECC71', width=1.5, dash="dash"),
        )
        
        # Add Call price badge on the right margin
        fig_options.add_annotation(
            x=df['Datetime_Str'].iloc[-1],
            y=live_ce,
            text=f"CE: {live_ce:,.2f}",
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(color="white", size=9, weight="bold"),
            bgcolor='#2ECC71',
            bordercolor='#2ECC71',
            borderwidth=1,
            borderpad=3,
            align="left"
        )
        
        # Add horizontal dashed line at latest Put price
        fig_options.add_shape(
            type="line",
            x0=df['Datetime_Str'].iloc[0],
            y0=live_pe,
            x1=df['Datetime_Str'].iloc[-1],
            y1=live_pe,
            line=dict(color='#E74C3C', width=1.5, dash="dash"),
        )
        
        # Add Put price badge on the right margin
        fig_options.add_annotation(
            x=df['Datetime_Str'].iloc[-1],
            y=live_pe,
            text=f"PE: {live_pe:,.2f}",
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            font=dict(color="white", size=9, weight="bold"),
            bgcolor='#E74C3C',
            bordercolor='#E74C3C',
            borderwidth=1,
            borderpad=3,
            align="left"
        )
        
        fig_options.update_layout(
            plot_bgcolor='#0d0f12',
            paper_bgcolor='#0d0f12',
            font=dict(family='Inter, sans-serif', color='#e2e8f0'),
            dragmode='pan',
            xaxis=dict(
                title="Time",
                type='date',
                tickformat='%H:%M',
                hoverformat='%H:%M:%S',
                showgrid=True,
                gridcolor='#1e2433',
                zeroline=False,
                showspikes=True,
                spikesnap="data",
                spikemode="across",
                spikethickness=1,
                spikecolor="#2c354d",
                spikedash="dash"
            ),
            yaxis=dict(
                title="Option Price (₹)",
                showgrid=True,
                gridcolor='#1e2433',
                zeroline=False,
                showspikes=True,
                spikesnap="data",
                spikemode="across",
                spikethickness=1,
                spikecolor="#2c354d",
                spikedash="dash"
            ),
            hovermode="x unified",
            legend=dict(
                orientation="h", 
                yanchor="bottom", 
                y=1.02, 
                xanchor="left", 
                x=0.01,
                bgcolor='rgba(0,0,0,0)'
            ),
            margin=dict(l=40, r=80, t=45, b=40),
            height=450
        )
        
        st.plotly_chart(fig_options, width='stretch', config=plotly_config, key="options_crossover_chart")
else:
    st.markdown(
        """
        <div style="background-color:#141822; padding:30px; border-radius:12px; border:1px solid #1e2433; text-align:center;">
            <h3 style="color:#ffffff; margin:0 0 10px 0;">🔄 Synchronizing Market Database...</h3>
            <p style="color:#8f929d; margin:0 0 15px 0; font-size:14.5px;">
                The background engine is currently querying live quotes and establishing the history.
            </p>
            <p style="color:#f59e0b; margin:0; font-size:13px; font-weight:600;">
                Note: Live data collection runs every second in the background. Hover gridlines will adjust automatically to spacing on zooming.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
# Sleep for refresh interval, then rerun to pull the next update
if not pause_refresh:
    time.sleep(refresh_interval)
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()
else:
    st.sidebar.info("⏸️ Auto-refresh is paused. You can now draw trendlines, zoom, and inspect without resets.")