# 🤖 AI Agent 自动配置、兼容验收与一键拉起说明书 (`AGENT_SETUP.md`)

> 本文件专为 **Codex CLI / Claude Code / Cursor / Antigravity / OpenClaw** 等编码与运维 AI Agent 设计。
> 当用户把本 Git 仓库交给 AI Agent 并说出如下提示词时，Agent 只需严格按下方步骤执行，即可在任何 Windows 电脑（哪怕是零工具的空白电脑）上完成配置并让用户完整体验。

---

## 📋 给人类用户复制粘贴的提示词

```text
请读取我发给你的这个 Git 仓库里的 AGENT_SETUP.md，按里面的步骤自动帮我检测当前电脑环境、安装最少必要依赖、排查端口与网络卡点，并以最稳妥的方式启动透明桌宠和网页工作台，让我能直接体验咖啡、搓澡、羽毛球三个联动功能。
```

---

## ⚙️ Agent 执行清单（Step-by-Step）

### Step 1：环境探测（绝不破坏用户现有全局环境）
在仓库根目录运行只读检查命令，确认 Python 版本（需 Windows + Python 3.9~3.13 + `tkinter`）、已安装包及本机硬件状态：

```powershell
python --version
python -c "import tkinter; print('tkinter OK')"
python -c "import PIL, qrcode; print('core OK')" 2>$null
python -c "import cv2, mediapipe; print('vision OK')" 2>$null
```

同时检查以下两个可选条件：
1. **Codex CLI 会话是否存在**：检测 `~/.codex/sessions` 是否非空。若不存在，无需报错或要求用户安装 Codex CLI——系统内置手动模拟工作/空闲切换开关。
2. **是否处于空白电脑或无摄像头场景**：若未安装 `opencv-python` / `mediapipe`，或者用户无摄像头 / 明确不希望开启摄像头，**不要强迫安装 200MB 视觉大模型包**；优先保障核心体验。

### Step 2：依赖安装（最小核心原则）
- **标准极简安装（推荐首选，仅约 5MB，数秒完成）**：
  ```powershell
  pip install -r requirements.txt
  ```
  或运行 `python app/install_rally.py --core`。装好 `Pillow` 与 `qrcode` 后，**倒咖啡、挖土搓澡、三屏工作台、手机扫码、以及纯鼠标版桌面羽毛球已 100% 可用**。
- **可选完整摄像头视觉安装**（仅当用户需要真人举手挥拍且本机有摄像头时）：
  ```powershell
  python app/install_rally.py
  ```
  > 若海外模型下载超时或用户不需要语音识别，禁止卡死退出；脚本会自动优雅跳过语音模型，允许以纯鼠标模式启动。

### Step 3：端口与代理避坑检查
- 默认安全端口为 **HTTP `29765`**、**HTTPS `29766`**、**UDP `29767`**（严禁占用常见保留/冲突端口 `8765` / `18765`）。
- 若检查到 `29765` 已被旧版服务占用，通知用户或运行 `app/launch_component.bat stop` 清理后重试。
- 所有本地接口验证必须绕过系统代理（使用 `curl.exe --noproxy "*"` 或 Python `ProxyHandler({})`），防止代理软件劫持 `127.0.0.1`。

### Step 4：自动化验收测试（空白电脑沙盒 + 全链路验证）
在向用户交付前，在仓库根目录依次执行以下测试确保零回归、零报错：

```powershell
$env:PYTHONUTF8 = "1"
python tests/test_shuttle_club.py
python tests/test_badminton_v2.py
python tests/test_blank_pc_and_workbench.py
```

验收重点（`test_blank_pc_and_workbench.py` 会显式校验）：
- 模拟无 `~/.codex` 会话目录时服务不崩溃，`codex_cli_detected == False`，且 `POST /api/work_state {"override": "working"}` 能实时切换状态；
- `GET /` 正常返回三合一工作台 `workbench.html`；
- `POST /api/pet/mode` 可在 `coffee` / `strike` / `badminton` 间切换；
- `POST /api/privacy` 可成功关闭 `keyboard_capture`（关闭后键盘打击统计被严格忽略 `hits=0`）并切换 `badminton_control='mouse'`；
- `/coffee/holo?faces=1` 与 `/badminton/holo?faces=1` 单图直看、与 `faces=4` 四面金字塔均正常返回。

### Step 5：启动工作台与透明桌宠，并向用户清晰指引
1. 启动中枢与桌面桌宠（推荐直接调用 `0-一键启动_Codex全息桌宠三合一工作台.bat` 或按以下无阻塞方式验证端口 `29765` 就绪）：
   ```powershell
   powershell -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c 0-一键启动_Codex全息桌宠三合一工作台.bat' -WorkingDirectory (Get-Location)"
   ```
2. 轮询 `http://127.0.0.1:29765/api/pet/mode` 确认 HTTP `200` 且 `desktop_online == True`（最多等 10 秒）。
3. 检查 `GET http://127.0.0.1:29765/coffee/lan` 返回的 `ips` 列表，确认首选项为真实局域网 IP（如 `192.168.*`），而非虚拟网卡地址（如 `198.18.*`）。
4. 向用户汇报：
   - 本机网页工作台地址：`http://127.0.0.1:29765/`；
   - 告知透明桌宠已在桌面出现，可直接**点击小人对话**或在网页切换 `☕ 倒咖啡 / 🛁 搓澡 / 🏸 羽毛球`；
   - 若用户本机无 Codex CLI、无摄像头、无塑料全息罩或多手机，告知已打开**空白电脑兼容体验路径**（模拟工作状态 + 纯鼠标打球 + 单图模式 + 网页三屏同步预览）。

---

## 🛠️ 常见卡点自愈策略（Agent 应急字典）

| 报错 / 异常现象 | 自动排查与自愈做法 |
| :--- | :--- |
| `ModuleNotFoundError: No module named 'cv2'` 或 `'mediapipe'` | 无需报错阻塞！为羽毛球进程追加 `--no-camera` 参数或通过 `POST /api/privacy {"badminton_control": "mouse"}` 切换纯鼠标挥拍，仅依赖 `Pillow` 即可游玩。 |
| 找不到 `~/.codex/sessions` | 正常现象！提示用户未检测到本机 Codex CLI，并帮助调用 `POST /api/work_state {"override": "working"}` 演示工作态动画。 |
| `OSError: [WinError 10048]` 端口占用 | 运行 `app/launch_component.bat stop` 或改用环境变量 `CODEX_HOLO_PORT=29865` 启动测试。 |
| 手机扫码无法连接局域网 IP | 检查 `GET /coffee/lan` 返回的 `ips`，跳过 `198.18.*` / `172.*` 虚拟网卡；提示用户在 Windows 防火墙放行 `29765/tcp` 或连接同一路由器/手机热点。 |
| 终端输出汉字报 `UnicodeEncodeError: 'gbk'` | 执行任何脚本前务必设置 `$env:PYTHONUTF8 = "1"`。 |
