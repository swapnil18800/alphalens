import os
import requests

import sys
sys.stdout.reconfigure(encoding='utf-8')

os.makedirs("C:\\Users\\HP\\Desktop\\ai-projects\\alphalens\\assets\\logos_color", exist_ok=True)

tickers = [
    "AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","AMD","INTC",
    "CRM","ORCL","ADBE","QCOM","NFLX","UBER","IBM","PANW","NOW",
    "PYPL","PLTR","LRCX","AMAT","AVGO","MU","CSCO","TXN","SNOW"
]

BASE_URL = "https://cdn.brandfetch.io/ticker/{}"

for ticker in tickers:
    url = BASE_URL.format(ticker)
    response = requests.get(url)

    if response.status_code == 200:
        with open(f"C:\\Users\\HP\\Desktop\\ai-projects\\alphalens\\assets\\logos_color\\{ticker}.png", "wb") as f:
            f.write(response.content)
        print(f"Downloaded {ticker}")
    else:
        print(f"Missing {ticker}")