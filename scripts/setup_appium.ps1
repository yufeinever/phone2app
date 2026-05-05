$ErrorActionPreference = "Stop"

npm config set registry https://registry.npmmirror.com
npm install -g appium
appium driver install uiautomator2

python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

Write-Host "Appium setup finished."
Write-Host "Start server with: appium --address 127.0.0.1 --port 4723"
