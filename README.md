# NIFTY Live Options & Spot Charting Tools

A collection of python scripts to stream and visualize live NIFTY 50 Spot and ATM (At-The-Money) Options premiums (Call & Put) in real-time. 

## Features

1. **Interactive Web Dashboard (`app.py`)**
   - Built using **Streamlit** and **Plotly**.
   - Connects to the **Upstox API** to fetch live quotes.
   - Dynamically identifies ATM strikes and pulls nearest weekly expiries.
   - Plots dual-axis charts showing NIFTY Spot (left axis) against Call (CE) and Put (PE) premiums (right axis).
   - Graceful credential handling (checks `.env` file, Streamlit secrets, or prompts via a sidebar input).

2. **Real-time CLI Graph (`main.py`)**
   - Built using **Matplotlib** in interactive mode with a professional dark mode style.
   - Fetches options chain data directly from **NSE India**.
   - Automatically bypasses WAF / TLS fingerprinting using `curl_cffi` to mimic standard browser signatures.
   - Updates every 30 seconds, plotting the spot price and ATM options premiums on secondary axes.

---

## Getting Started

### 1. Prerequisites & Virtual Environment

It is recommended to run this project in a virtual environment.

```bash
# Create a virtual environment
python -m venv venv

# Activate it (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate it (Windows CMD)
.\venv\Scripts\activate.bat

# Activate it (Mac/Linux)
source venv/bin/activate
```

### 2. Install Dependencies

Install the required Python modules:

```bash
pip install -r requirements.txt
```

### 3. Configuration & API Tokens

For **`app.py`** and **`test_api.py`**, you need an active Upstox access token.

1. Duplicate the `.env.example` file and rename it to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and paste your daily token:
   ```env
   UPSTOX_ACCESS_TOKEN=your_token_here
   ```

*Note: `.env` is automatically ignored by Git to protect your credentials.*

---

## Running the Applications

### Launch the Streamlit Dashboard
```bash
streamlit run app.py
```
This will start a local server and open the interactive dashboard in your default browser. If no `.env` token is detected, it will let you enter it securely via the sidebar.

### Launch the CLI Tracker
```bash
python main.py
```
This runs a persistent tracking window showing the live crossover graph using Matplotlib. You can press `Ctrl + C` in the terminal to stop tracking.

### Run the API Connection Test
```bash
python test_api.py
```
A quick sanity test script to check if your Upstox credentials and connection are working correctly.
