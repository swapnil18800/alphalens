import os
import requests

import sys
sys.stdout.reconfigure(encoding='utf-8')

# Create folder
os.makedirs("logos", exist_ok=True)

ticker_to_slug = {
    "AAPL": "apple",
    "MSFT": "microsoft",
    "GOOGL": "google",
    "AMZN": "amazon",
    "NVDA": "nvidia",
    "META": "meta",
    "TSLA": "tesla",
    "AMD": "amd",
    "INTC": "intel",
    "CRM": "salesforce",
    "ORCL": "oracle",
    "ADBE": "adobe",
    "QCOM": "qualcomm",
    "NFLX": "netflix",
    "UBER": "uber",
    "IBM": "ibm",
    "PANW": "paloaltonetworks",
    "NOW": "servicenow",
    "PYPL": "paypal",
    "PLTR": "palantir",
    "LRCX": "lamresearch",
    "AMAT": "appliedmaterials",
    "AVGO": "broadcom",
    "MU": "microntechnology",
    "CSCO": "cisco",
    "TXN": "texasinstruments",
    "SNOW": "snowflake"
}

BASE_URL = "https://cdn.jsdelivr.net/npm/simple-icons/icons/{}.svg"

for ticker, slug in ticker_to_slug.items():
    url = BASE_URL.format(slug)
    response = requests.get(url)

    if response.status_code == 200:
        file_path = f"C:\\Users\\HP\\Desktop\\ai-projects\\alphalens\\assets\\logos\\{ticker}.svg"
        with open(file_path, "wb") as f:
            f.write(response.content)
        print(f"✅ Downloaded {ticker}")
    else:
        print(f"❌ Missing: {ticker} ({slug})")