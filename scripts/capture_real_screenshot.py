import subprocess
import asyncio
import json
import urllib.request
import base64
import os
import shutil
import time

CHROME_PATH = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PORT = 9222
TARGET_PNG = r'd:\Projects\VolHelix-AI\docs\assets\dashboard.png'
PUBLIC_PNG = r'd:\Projects\VolHelix-AI\frontend\public\dashboard.png'

async def capture():
    # 1. Launch Chrome with remote debugging
    user_data = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "chrome_snap_profile")
    os.makedirs(user_data, exist_ok=True)
    cmd = [
        CHROME_PATH,
        '--headless=new',
        '--disable-gpu',
        f'--user-data-dir={user_data}',
        f'--remote-debugging-port={PORT}',
        '--window-size=1920,1080',
        '--hide-scrollbars',
        'http://localhost:3000/'
    ]
    proc = subprocess.Popen(cmd)
    try:
        # 2. Wait for Chrome DevTools endpoint to become available
        ws_url = None
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                with urllib.request.urlopen(f'http://localhost:{PORT}/json') as resp:
                    tabs = json.loads(resp.read().decode())
                    if tabs and 'webSocketDebuggerUrl' in tabs[0]:
                        ws_url = tabs[0]['webSocketDebuggerUrl']
                        break
            except Exception:
                pass

        if not ws_url:
            raise RuntimeError("Could not connect to Chrome DevTools endpoint")

        print(f"Connected to DevTools: {ws_url}")
        import websockets
        async with websockets.connect(ws_url) as ws:
            # Wait 5 seconds for React components and candlestick chart to fully load
            print("Waiting for chart & market data to render...")
            await asyncio.sleep(5.0)

            # Request screenshot
            req = {
                "id": 1,
                "method": "Page.captureScreenshot",
                "params": {"format": "png", "captureBeyondViewport": False}
            }
            await ws.send(json.dumps(req))
            res = await ws.recv()
            data = json.loads(res)
            
            img_b64 = data["result"]["data"]
            img_bytes = base64.b64decode(img_b64)
            
            with open(TARGET_PNG, "wb") as f:
                f.write(img_bytes)
            print(f"Successfully captured screenshot: {len(img_bytes)} bytes written to {TARGET_PNG}")
            
            shutil.copyfile(TARGET_PNG, PUBLIC_PNG)
            print(f"Copied to {PUBLIC_PNG}")

    finally:
        proc.terminate()
        proc.wait()

if __name__ == '__main__':
    asyncio.run(capture())
