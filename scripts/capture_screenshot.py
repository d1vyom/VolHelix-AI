import subprocess
import os
import shutil

chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
if not os.path.exists(chrome_path):
    chrome_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

target_png = r'd:\Projects\VolHelix-AI\docs\assets\dashboard.png'
public_png = r'd:\Projects\VolHelix-AI\frontend\public\dashboard.png'

cmd = [
    chrome_path,
    '--headless=new',
    '--disable-gpu',
    '--window-size=1920,1080',
    '--virtual-time-budget=7000',
    f'--screenshot={target_png}',
    'http://localhost:3000/'
]

print("Capturing dashboard screenshot with command:", cmd)
res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
print("Return code:", res.returncode)
if res.stdout:
    print("Stdout:", res.stdout)
if res.stderr:
    print("Stderr:", res.stderr)

if os.path.exists(target_png) and os.path.getsize(target_png) > 1000:
    print(f"Screenshot captured successfully! Size: {os.path.getsize(target_png)} bytes")
    shutil.copyfile(target_png, public_png)
    print("Copied to frontend/public/dashboard.png as well.")
else:
    print("Screenshot file was not created or is empty.")
