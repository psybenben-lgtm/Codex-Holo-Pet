'use strict';

(() => {
  const $ = id => document.getElementById(id);
  const state = {
    mode: 'coffee',
    faces: 4,
    ip: '',
    port: 29765,
    ips: [],
    info: null,
  };

  async function api(url, body) {
    const opts = body !== undefined
      ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : { method: 'GET', cache: 'no-store' };
    const r = await fetch(url, opts);
    return r.json();
  }

  function updateSeg(containerId, attr, val) {
    const box = $(containerId);
    if (!box) return;
    box.querySelectorAll('button').forEach(b => {
      b.classList.toggle('on', b.getAttribute(attr) === String(val));
    });
  }

  function renderQRs() {
    const ip = $('ipSelect').value || state.ip || location.hostname || '127.0.0.1';
    const base = `http://${ip}:${state.port}`;
    const f = state.faces;
    let items = [];
    if (state.mode === 'coffee') {
      items = [
        { title: '🔮 手机 A · 全息接咖啡端', desc: f === 4 ? '四面投影 · 放上 1×6×3.5cm 塑料罩' : '单图直看 · 无需全息金字塔', url: `${base}/coffee/holo?mode=coffee&faces=${f}` },
        { title: '📱 手机 B · 触控倒咖啡端', desc: '手指左滑/滑条倾斜倒咖啡进全息杯', url: `${base}/coffee/pour` },
        { title: '💻 电脑网页工位端（备用）', desc: '平板或副屏也可扫此码看小人接杯', url: `${base}/coffee/desk` },
      ];
    } else if (state.mode === 'strike') {
      items = [
        { title: '🔮 手机 A · 全息挖土 & 泡澡端', desc: f === 4 ? '四面全息 · 接住甩泥与泡泡浴' : '单图直看 · 免全息金字塔', url: `${base}/coffee/holo?mode=strike&faces=${f}` },
        { title: '📱 手机 B · 推浴缸 & 调温 & 搓澡', desc: '推桶 / 拧龙虾水温 / 搓背弹❓', url: `${base}/coffee/bath` },
        { title: '🎛️ 平板/手机三端总览（可选）', desc: '副屏一键控制全部挖土与洗浴节奏', url: `${base}/strike/dash` },
      ];
    } else {
      items = [
        { title: '🔮 手机 A · 全息发球机端（必选）', desc: f === 4 ? '四面全息发球入电脑 · 支持清屏模式' : '单图发球机预览 · 无需全息金字塔', url: `${base}/badminton/holo?faces=${f}` },
        { title: '📱 手机 B · 辅助导演遥控台（可选）', desc: '手机遥控开打、切拍、连发七球', url: `${base}/badminton/ctrl` },
      ];
    }
    const grid = $('qrGrid');
    grid.innerHTML = items.map(it => {
      const qrSrc = `/api/qrcode?text=${encodeURIComponent(it.url)}`;
      return `
        <div class="qr-card">
          <div style="font-size:13.5px;font-weight:800;color:#f8fafc;">${it.title}</div>
          <div style="font-size:11.5px;color:var(--muted);">${it.desc}</div>
          <img src="${qrSrc}" alt="${it.title}">
          <code>${it.url}</code>
          <div style="display:flex;gap:6px;">
            <a class="btn" href="${it.url}" target="_blank">网页打开 ↗</a>
            <button class="btn" onclick="navigator.clipboard?.writeText('${it.url}').then(()=>this.textContent='已复制 ✓')">复制地址</button>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderStage() {
    const f = state.faces;
    const grid = $('stageGrid');
    const bar = $('stageQuickBtns');
    grid.className = state.mode === 'badminton' ? 'stage-grid two' : 'stage-grid';

    if (state.mode === 'coffee') {
      $('stageTitle').textContent = '☕ 跨屏倒咖啡 · 电脑端三屏实时联调舞台（无需手机也能一键倒咖啡看 Codex 喝杯说 Thanks）';
      bar.innerHTML = `
        <button class="btn gold" id="btnQuickPour">☕ 一键满杯倾倒演示（免手机）</button>
        <button class="btn" id="btnResetCoffee">🔄 重新倒一杯</button>
      `;
      grid.innerHTML = `
        <div class="frame-card">
          <div class="frame-head"><span>💻 电脑桌面工位 / 接杯预览</span><a href="/coffee/desk" target="_blank">独立窗口 ↗</a></div>
          <div class="frame-box"><iframe src="/coffee/desk?embed=1"></iframe></div>
        </div>
        <div class="frame-card">
          <div class="frame-head"><span>🔮 全息手机预览 (${f === 4 ? '四面金字塔' : '单图直看'})</span><a href="/coffee/holo?mode=coffee&faces=${f}" target="_blank">独立窗口 ↗</a></div>
          <div class="frame-box"><iframe src="/coffee/holo?mode=coffee&faces=${f}&embed=1"></iframe></div>
        </div>
        <div class="frame-card">
          <div class="frame-head"><span>📱 手机倾倒交互端（可用鼠标滑倒）</span><a href="/coffee/pour" target="_blank">独立窗口 ↗</a></div>
          <div class="frame-box"><iframe src="/coffee/pour?embed=1"></iframe></div>
        </div>
      `;
      $('btnQuickPour').onclick = async () => {
        const { round } = await api('/coffee/clock').then(() => api('/api/pet/mode'));
        const cur = await api('/coffee/reset', {});
        const r = cur.round;
        let seq = 1;
        for (const amt of [0.16, 0.34, 0.52, 0.68, 0.80]) {
          await api('/coffee/pour', { owner: 'carafe-pc-demo', seq: seq++, round: r, amount: amt, flow: 0.9 });
          await new Promise(res => setTimeout(res, 220));
        }
      };
      $('btnResetCoffee').onclick = () => api('/coffee/reset', {});
    } else if (state.mode === 'strike') {
      $('stageTitle').textContent = '🛁 挖土罢工 & 全息搓澡 · 电脑端三屏联调（无需读键盘 & 无需拖拽浴缸，点按钮逐关触发）';
      bar.innerHTML = `
        <button class="btn primary" onclick="fetch('/api/strike/input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hits:12})})">⛏️ 模拟打字挖土</button>
        <button class="btn red" onclick="fetch('/api/strike/trigger',{method:'POST',body:'{}'})">💥 暴怒跨屏甩泥</button>
        <button class="btn" style="background:#0369a1;" onclick="fetch('/api/strike/bath_push',{method:'POST',body:'{}'})">🛁 推入浴缸(免拖)</button>
        <button class="btn" onclick="fetch('/api/strike/bath_knob',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({temp:86})})">🦞 86°C 过烫跳出</button>
        <button class="btn green" onclick="fetch('/api/strike/scrub_start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({immediate:true})})">🧽 开始搓澡</button>
        <button class="btn purple" onclick="fetch('/api/strike/scrub_move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({zone:'head',y:0.2})})">❓ 搓头弹问号</button>
        <button class="btn gold" onclick="fetch('/api/strike/return_office',{method:'POST',body:'{}'})">🏠 洗净回工位</button>
        <button class="btn" onclick="fetch('/api/strike/reset',{method:'POST',body:'{}'})">🔄 重置</button>
      `;
      grid.innerHTML = `
        <div class="frame-card">
          <div class="frame-head"><span>💻 电脑端（工位 ⇋ 甩泥 ⇋ 搓澡）</span><a href="/coffee/desk" target="_blank">独立窗口 ↗</a></div>
          <div class="frame-box"><iframe src="/coffee/desk?embed=1"></iframe></div>
        </div>
        <div class="frame-card">
          <div class="frame-head"><span>🔮 全息端 (${f === 4 ? '四面金字塔' : '单图直看'})</span><a href="/coffee/holo?mode=strike&faces=${f}" target="_blank">独立窗口 ↗</a></div>
          <div class="frame-box"><iframe src="/coffee/holo?mode=strike&faces=${f}&embed=1"></iframe></div>
        </div>
        <div class="frame-card">
          <div class="frame-head"><span>📱 手机触控（推桶/调温/海绵）</span><a href="/coffee/bath" target="_blank">独立窗口 ↗</a></div>
          <div class="frame-box"><iframe src="/coffee/bath?embed=1"></iframe></div>
        </div>
      `;
    } else {
      $('stageTitle').textContent = '🏸 羽毛球互动（双屏联动：已自动内置全息发球机视角，单台空白电脑不开摄像头也能直接鼠标挥拍对打）';
      bar.innerHTML = `
        <button class="btn gold" onclick="fetch('/api/badminton/live/start',{method:'POST',body:'{}'})">🏸 开始开打</button>
        <button class="btn primary" onclick="fetch('/api/badminton/live/swing',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({x:0.5,y:0.5,power:0.86,assisted:true,force_smash:true})})">💥 辅助挥拍扣杀</button>
        <button class="btn purple" onclick="fetch('/api/badminton/live/barrage',{method:'POST',body:'{}'})">⚡ 七球连发开挂</button>
        <button class="btn" onclick="fetch('/api/badminton/live/hand_mode',{method:'POST',body:'{}'})">🖐/🏸 切换手与球拍</button>
        <button class="btn" onclick="fetch('/api/badminton/live/quit',{method:'POST',body:'{}'})">🏠 收拍回工位</button>
      `;
      grid.innerHTML = `
        <div class="frame-card">
          <div class="frame-head"><span>🎬 导演控制台（开关摄像头 / 鼠标控拍 / 比分调试）</span><a href="/badminton/director" target="_blank">完整导演台 ↗</a></div>
          <div class="frame-box"><iframe src="/badminton/director"></iframe></div>
        </div>
        <div class="frame-card">
          <div class="frame-head"><span>🔮 全息发球机端 (${f === 4 ? '四面金字塔' : '单图直看'}) · 维持自动发球在线</span><a href="/badminton/holo?faces=${f}" target="_blank">全屏打开 ↗</a></div>
          <div class="frame-box"><iframe src="/badminton/holo?faces=${f}"></iframe></div>
        </div>
      `;
    }
    renderQRs();
  }

  function applyInfo(info) {
    if (!info) return;
    state.info = info;
    if (info.mode && info.mode !== state.mode) {
      state.mode = info.mode;
      document.querySelectorAll('.mode-card').forEach(c => c.classList.toggle('active', c.dataset.mode === state.mode));
      renderStage();
    }
    state.faces = info.holo_faces || 4;
    updateSeg('facesSeg', 'data-faces', state.faces);
    updateSeg('workSeg', 'data-work', info.work_override || 'auto');
    updateSeg('bmCtrlSeg', 'data-bm', info.badminton_control || 'mouse');
    updateSeg('kbSeg', 'data-kb', info.keyboard_capture === false ? '0' : '1');

    const petOnline = Boolean(info.desktop_online);
    const petPill = $('petPill');
    petPill.textContent = petOnline ? `● 透明桌宠在线 (${info.mode})` : '○ 桌宠未拉起 · 点右侧拉起';
    petPill.className = 'pill ' + (petOnline ? 'ok' : 'warn');

    const codexPill = $('codexPill');
    if (info.codex_cli_detected) {
      codexPill.textContent = `🤖 本机 Codex 已连接 (${info.effective_work})`;
      codexPill.className = 'pill ok';
    } else {
      codexPill.textContent = `🤖 未检测到 Codex CLI · 当前体验模式: ${info.effective_work}`;
      codexPill.className = 'pill warn';
    }
    $('workBadge').textContent = info.effective_work === 'working' ? '工作中' : (info.effective_work === 'idle' ? '空闲摸鱼' : '待机');
    $('bmCtrlBadge').textContent = info.camera_deps_ready ? '摄像头/鼠标均可' : '仅需纯鼠标(免AI包)';
  }

  async function refreshStatus() {
    try {
      const info = await api('/api/pet/mode');
      applyInfo(info);
    } catch {}
  }

  async function init() {
    state.ip = location.hostname || '127.0.0.1';
    state.port = Number(location.port) || 29765;
    $('ipSelect').innerHTML = `<option value="${state.ip}">${state.ip}</option>`;

    // 同步首屏渲染舞台与二维码，避免等待接口时出现空白与跳动
    renderStage();

    $('ipSelect').onchange = () => {
      state.ip = $('ipSelect').value;
      renderQRs();
    };

    document.querySelectorAll('.mode-card').forEach(btn => {
      btn.onclick = async () => {
        const m = btn.dataset.mode;
        state.mode = m;
        document.querySelectorAll('.mode-card').forEach(c => c.classList.toggle('active', c.dataset.mode === m));
        renderStage();
        const res = await api('/api/pet/mode', { mode: m, spawn: true });
        applyInfo(res);
      };
    });

    $('workSeg').querySelectorAll('button').forEach(b => {
      b.onclick = async () => applyInfo(await api('/api/work_state', { override: b.dataset.work }));
    });
    $('facesSeg').querySelectorAll('button').forEach(b => {
      b.onclick = async () => {
        state.faces = Number(b.dataset.faces);
        updateSeg('facesSeg', 'data-faces', state.faces);
        renderStage();
        await api('/api/privacy', { holo_faces: state.faces });
      };
    });
    $('bmCtrlSeg').querySelectorAll('button').forEach(b => {
      b.onclick = async () => applyInfo(await api('/api/privacy', { badminton_control: b.dataset.bm }));
    });
    $('kbSeg').querySelectorAll('button').forEach(b => {
      b.onclick = async () => applyInfo(await api('/api/privacy', { keyboard_capture: b.dataset.kb === '1' }));
    });

    $('btnWakePet').onclick = async () => applyInfo(await api('/api/pet/mode', { mode: state.mode, spawn: true }));
    $('btnChatPet').onclick = async () => {
      const lines = [
        '你要给我倒咖啡吗？☕',
        '不接手机、不开摄像头也能点上面按钮和我玩哦！',
        '敲字累了就切到搓澡模式给我在全息浴缸泡个澡吧～🛁',
      ];
      const msg = lines[Math.floor(Math.random() * lines.length)];
      await api('/api/pet/chat', { text: msg });
    };
    $('btnShutdown').onclick = async () => {
      if (confirm('确定停止透明桌宠与本地同步服务吗？')) {
        await api('/api/system/shutdown', {});
        $('srvPill').textContent = '○ 服务已停止';
        $('srvPill').className = 'pill';
      }
    };

    $('btnOpenHoloGuide').onclick = () => $('dlgHolo').showModal();
    $('btnOpenPrivacy').onclick = () => $('dlgPrivacy').showModal();
    $('btnOpenNetHelp').onclick = () => $('dlgNet').showModal();

    // 异步并行拉取局域网 IP 列表与中枢状态
    await Promise.allSettled([
      api('/coffee/lan').then(lan => {
        if (!lan) return;
        state.ips = lan.ips || ['127.0.0.1'];
        state.ip = lan.ip || state.ips[0];
        state.port = lan.http_port || state.port;
        $('ipSelect').innerHTML = state.ips
          .map((ip, i) => `<option value="${ip}">${ip}${i === 0 ? ' (推荐主 Wi-Fi)' : ''}</option>`)
          .join('');
        renderQRs();
      }),
      refreshStatus(),
    ]);
    setInterval(refreshStatus, 1500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
