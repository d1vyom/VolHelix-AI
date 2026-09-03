import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest

# Load .env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

def test_connection():
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")
    
    if not api_key or not api_secret:
        print("[ERROR] ALPACA_API_KEY or ALPACA_API_SECRET not found in .env")
        return

    print(f"[INFO] Connecting to Alpaca Paper API with key {api_key[:6]}...")
    
    try:
        # 1. Test Trading Client
        trading_client = TradingClient(api_key, api_secret, paper=True)
        account = trading_client.get_account()
        
        print("\n[OK] Trading Client Connected!")
        print(f"   Account Status: {account.status}")
        print(f"   Buying Power: ${float(account.buying_power):,.2f}")
        print(f"   Options Approved Level: {account.options_approved_level}")
        print(f"   Options Trading Level: {account.options_trading_level}")
        
        if account.options_approved_level < 2:
            print("\n[WARNING] Options trading level is below 2. Spreads require at least level 2/3.")
        else:
            print("\n[OK] Options Trading is enabled and ready.")
            
        # 2. Test Clock
        clock = trading_client.get_clock()
        print(f"\n[OK] Clock Checked. Market is currently {'OPEN' if clock.is_open else 'CLOSED'}")
        
    except Exception as e:
        print(f"\n[ERROR] Connection Failed: {e}")

if __name__ == "__main__":
    test_connection()
