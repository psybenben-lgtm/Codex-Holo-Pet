'use strict';

// The phone renders the original hologram and acknowledges each actual launch.
(() => {
  const canvas = document.getElementById('holoCanvas');
  const ctx = canvas.getContext('2d');
  const connPill = document.getElementById('connPill');
  const scenePill = document.getElementById('scenePill');

  const params = new URLSearchParams(location.search);
  let fourFaces = params.get('faces') !== '1';
  let mirrorFlip = true;
  let shootLeft = true; // 默认出球口朝向电脑侧

  const offscreen = document.createElement('canvas');
  offscreen.width = 240;
  offscreen.height = 180;
  const g = offscreen.getContext('2d');

  let state = null;
  let serverOffset = 0;
  let online = false;
  let localLaunchAnim = -Infinity;
  let session = null;
  let latestSeq = -1;
  let sent = null;
  let retryAt = 0;
  let lastLaunch = 0;
  let scheduled = [];
  let heartbeatBusy = false;
  let sounds = null;

  function unlockAudio() {
    if (sounds) return;
    const make = (f, v) => { const a = new Audio('/coffee/' + f); a.volume = v; return a; };
    sounds = {
      start: make('machine_start.wav', 0.45),
      charge: make('machine_charge.wav', 0.45),
      launch: make('shuttle_launch.wav', 0.65),
      rapid: make('cheat_rapid.wav', 0.55),
      jam: make('machine_jam.wav', 0.65),
      giant: make('giant_impact.wav', 0.75),
    };
  }

  function playSound(name) {
    const a = sounds?.[name];
    if (!a) return;
    try { a.currentTime = 0; a.play().catch(() => {}); } catch {}
  }

  function post(action, body) {
    return fetch('/api/badminton/live/' + action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    });
  }

  function connection(ok) {
    online = ok;
    connPill.textContent = ok ? '● 全息发球机在线' : '○ 正在连接电脑';
    connPill.classList.toggle('offline', !ok);
  }

  function confirm(next) {
    const pending = next.pending;
    if (!pending || !next.desktop_online || !next.phone_online || document.hidden) return;
    if (sent === pending.id && performance.now() < retryAt) return;
    sent = pending.id;
    retryAt = performance.now() + 600;
    post('launch', { session: next.session, id: pending.id, side: shootLeft ? 'right' : 'left' }).then(applyState).catch(() => {});
  }

  function applyState(next) {
    if (!next || !next.session) return;
    if (next.session !== session) {
      session = next.session;
      latestSeq = -1;
      lastLaunch = 0;
      sent = null;
      scheduled = [];
      localLaunchAnim = -Infinity;
    }
    if (next.seq < latestSeq) return;
    latestSeq = next.seq;
    const local = performance.now();
    const sample = next.now * 1000 - local;
    serverOffset = state?.session === session ? serverOffset * .84 + sample * .16 : sample;
    connection(true);
    const names = { desk: '待机', clear: '正在清出球场', rally: '对打', charge: '蓄力', barrage: '连发', quit: '收拍' };
    scenePill.textContent = next.desktop_online ? names[next.phase] || '待机' : '等待电脑桌宠';
    if (next.phase === 'desk' || next.phase === 'quit') {
      scheduled = [];
      localLaunchAnim = -Infinity;
    }
    for (const launch of next.launches || []) {
      if (launch.id <= lastLaunch) continue;
      lastLaunch = launch.id;
      const when = launch.at * 1000 - serverOffset;
      if (when >= local - 120 && next.phase !== 'desk' && next.phase !== 'quit') {
        scheduled.push({ when, kind: launch.kind });
      }
    }
    state = next;
    confirm(next);
  }

  function heartbeat() {
    if (heartbeatBusy) return;
    heartbeatBusy = true;
    post('phone', { visible: !document.hidden }).then(applyState).catch(() => connection(false)).finally(() => { heartbeatBusy = false; });
  }

  const sync = new EventSource('/api/badminton/live/stream');
  sync.onmessage = e => {
    try { applyState(JSON.parse(e.data).data); } catch {}
  };
  sync.onerror = () => connection(false);
  setInterval(heartbeat, 800);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) heartbeat(); });
  heartbeat();

  function rect(c, x, y, w, h) {
    g.fillStyle = c;
    g.fillRect(Math.round(x), Math.round(y), Math.max(1, Math.round(w)), Math.max(1, Math.round(h)));
  }

  function renderMachineScene(now) {
    g.fillStyle = '#000000';
    g.fillRect(0, 0, 240, 180);

    const phase = state?.phase || 'desk';
    const isCheat = phase === 'charge' || phase === 'barrage';
    const charge = state?.pending || scheduled.length ? .9 : phase === 'charge' ? .76 : .24;
    const holo = { barrel_angle: isCheat ? 23 : charge > .8 ? 21 : 16,
                   shuttles_left: 5 - ((state?.launches || []).length % 5), charge };
    const vib = isCheat ? 1.5 : 0;
    const vx = vib ? Math.sin(now * 0.08) * vib : 0;
    const vy = vib ? Math.cos(now * 0.11) * vib : 0;

    const launchAge = (now - localLaunchAnim) / 1000;
    const recoil = (launchAge >= 0 && launchAge < 0.22) ? Math.sin((launchAge / 0.22) * Math.PI) * 6 : 0;

    g.save();
    // 适当放大全息发球机主体并留足边缘安全区，适配四面金字塔和单面视图
    g.translate(132 + vx, 126 + vy);
    g.scale(1.26, 1.26);
    if (!shootLeft) g.scale(-1, 1);

    // 1. 底部高对比度全息底座投影光圈
    g.fillStyle = isCheat ? 'rgba(239, 68, 68, 0.22)' : 'rgba(56, 189, 248, 0.20)';
    g.beginPath();
    g.ellipse(0, 12, 46, 8, 0, 0, Math.PI * 2);
    g.fill();

    // 2. 发球机稳固金属底座与状态指示灯 (LED)
    rect('#1e293b', -32, -4, 64, 14);
    rect('#475569', -28, -6, 56, 4);
    rect('#94a3b8', -24, -5, 48, 2);

    // 状态指示灯：正常模式翠绿常亮；作弊/失控模式猩红高频爆闪！
    const ledOn = isCheat ? (Math.floor(now / 90) % 2 === 0) : true;
    const ledCol = !online ? '#f59e0b' : (isCheat ? (ledOn ? '#ef4444' : '#7f1d1d') : '#4ade80');
    rect(ledCol, -20, 0, 8, 5);
    if (isCheat && ledOn) {
      g.fillStyle = 'rgba(239, 68, 68, 0.45)';
      g.beginPath();
      g.arc(-16, 2.5, 9, 0, Math.PI * 2);
      g.fill();
    }

    // 支撑立柱与液压转轴
    rect('#334155', -10, -28, 20, 24);
    rect('#64748b', -6, -26, 12, 20);

    // 3. 顶部透明垂直储球管（清晰看到内部叠放的少量白色羽毛球！）
    const tubeX = 4;
    const tubeY = -72;
    // 透明玻璃管壁高光边框
    g.strokeStyle = 'rgba(186, 230, 253, 0.75)';
    g.lineWidth = 2;
    g.strokeRect(tubeX - 11, tubeY, 22, 38);
    g.fillStyle = 'rgba(56, 189, 248, 0.12)';
    g.fillRect(tubeX - 10, tubeY + 1, 20, 36);

    const count = Math.max(1, holo.shuttles_left);
    for (let i = 0; i < count; i++) {
      const sy = tubeY + 30 - i * 6;
      const jamShift = 0;
      // 储球管内的小羽毛球（软木球头朝下，白羽毛朝上）
      rect('#ffffff', tubeX - 6 + jamShift, sy - 4, 12, 4);
      rect('#ef4444', tubeX - 5 + jamShift, sy, 10, 1);
      rect('#fde047', tubeX - 3 + jamShift, sy + 1, 6, 3);
    }

    // 4. 可抬头蓄力的机械发球炮筒与明确出球口（朝左发射向电脑桌面）
    const angleDeg = holo.barrel_angle;
    const angleRad = (angleDeg * Math.PI) / 180;
    g.save();
    g.translate(0, -26);
    g.rotate(angleRad);
    g.translate(recoil, 0); // 发射瞬间后坐力回缩

    // 炮筒主体（膨胀蓄力时微鼓）
    const swell = 0;
    rect('#475569', -36, -11 - swell / 2, 54, 22 + swell);
    rect('#94a3b8', -34, -9 - swell / 2, 50, 6);
    rect('#1e293b', -32, -2, 46, 5);

    // 内部蓄力弹簧活塞可视窗
    const pistonCharge = holo.charge;
    const pistonX = -10 + pistonCharge * 16;
    rect('#f59e0b', pistonX, -3, 8, 6);
    for (let sx = pistonX + 8; sx < 12; sx += 4) {
      rect('#cbd5e1', sx, -2, 2, 4);
    }

    // 左侧明确的喇叭形出球口 (Muzzle)
    rect('#e2e8f0', -42, -13 - swell / 2, 7, 26 + swell);
    rect('#0f172a', -43, -9 - swell / 2, 3, 18 + swell);
    rect(isCheat ? '#ef4444' : '#38bdf8', -35, -12 - swell / 2, 3, 24 + swell);

    // 5. 发射瞬间从出球口喷出的羽毛球与气浪光环
    if (launchAge >= 0 && launchAge < 0.24) {
      const p = launchAge / 0.24;
      const sx = -46 - p * 54;
      const sy = -p * 10;
      // 出球口环形气浪
      g.strokeStyle = isCheat ? `rgba(248, 113, 113, ${1 - p})` : `rgba(125, 211, 252, ${1 - p})`;
      g.lineWidth = 2;
      g.beginPath();
      g.ellipse(-44, 0, 4 + p * 6, 10 + p * 12, 0, 0, Math.PI * 2);
      g.stroke();

      // 飞出的羽毛球
      const bScale = 1.;
      rect('#fde047', sx - 5 * bScale, sy - 3 * bScale, 5 * bScale, 6 * bScale);
      rect('#ffffff', sx, sy - 6 * bScale, 11 * bScale, 12 * bScale);
      rect('#ef4444', sx, sy - 4 * bScale, 2 * bScale, 8 * bScale);
    }

    g.restore();

    g.restore();
  }

  function renderLoop(now) {
    while (scheduled.length && scheduled[0].when <= now) {
      const shot = scheduled.shift();
      if (now - shot.when < 230) {
        localLaunchAnim = shot.when;
        playSound(shot.kind === 'barrage' ? 'rapid' : 'launch');
      }
    }
    renderMachineScene(now);

    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    if (fourFaces) {
      // 四面倒金字塔光学投影布局（稍微放大发球机显示尺寸）
      const turns = [
        [0, -212, 0],
        [212, 0, Math.PI / 2],
        [0, 212, Math.PI],
        [-212, 0, -Math.PI / 2],
      ];
      for (const [dx, dy, rot] of turns) {
        ctx.save();
        ctx.translate(360 + dx, 360 + dy);
        ctx.rotate(rot);
        ctx.scale(mirrorFlip ? -1 : 1, 1);
        ctx.drawImage(offscreen, -152, -114, 304, 228);
        ctx.restore();
      }
    } else {
      ctx.save();
      ctx.translate(360, 360);
      ctx.scale(mirrorFlip ? 1 : -1, 1);
      ctx.drawImage(offscreen, -350, -262, 700, 524);
      ctx.restore();
    }

    requestAnimationFrame(renderLoop);
  }

  const cleanToast = document.getElementById('cleanToast');
  let toastTimer = 0;
  function showCleanToast() {
    if (!cleanToast) return;
    cleanToast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => cleanToast.classList.remove('show'), 2200);
  }

  function enterCleanFullscreen() {
    document.body.classList.add('clean-projection');
    const root = document.documentElement;
    if (!document.fullscreenElement && root.requestFullscreen) {
      try {
        const p = root.requestFullscreen();
        if (p && typeof p.catch === 'function') p.catch(() => {});
      } catch {}
    }
    showCleanToast();
  }

  function exitCleanFullscreen() {
    document.body.classList.remove('clean-projection');
    if (cleanToast) cleanToast.classList.remove('show');
    if (document.fullscreenElement && document.exitFullscreen) {
      try {
        const p = document.exitFullscreen();
        if (p && typeof p.catch === 'function') p.catch(() => {});
      } catch {}
    }
  }

  function toggleCleanFullscreen() {
    if (document.body.classList.contains('clean-projection') || document.fullscreenElement) {
      exitCleanFullscreen();
    } else {
      enterCleanFullscreen();
    }
  }

  if (params.get('clean') === '1') {
    document.body.classList.add('clean-projection');
  }

  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) {
      document.body.classList.remove('clean-projection');
      if (cleanToast) cleanToast.classList.remove('show');
    }
  });

  // 按钮绑定
  const btnFaces = document.getElementById('btnFaces');
  btnFaces.textContent = fourFaces ? '切到单面大视图' : '切到四面金字塔';
  btnFaces.onclick = e => {
    unlockAudio();
    fourFaces = !fourFaces;
    e.target.textContent = fourFaces ? '切到单面大视图' : '切到四面金字塔';
  };
  document.getElementById('btnMirror').onclick = () => {
    unlockAudio();
    mirrorFlip = !mirrorFlip;
  };
  document.getElementById('btnDir').onclick = e => {
    unlockAudio();
    shootLeft = !shootLeft;
    e.target.textContent = shootLeft ? '手机在电脑右侧' : '手机在电脑左侧';
  };
  document.getElementById('btnClean').onclick = () => {
    unlockAudio();
    enterCleanFullscreen();
  };

  let lastTapAt = 0;
  canvas.addEventListener('click', () => {
    unlockAudio();
  });
  canvas.addEventListener('dblclick', () => {
    unlockAudio();
    toggleCleanFullscreen();
  });
  canvas.addEventListener('touchend', e => {
    const nowAt = performance.now();
    if (nowAt - lastTapAt < 320) {
      e.preventDefault();
      unlockAudio();
      toggleCleanFullscreen();
      lastTapAt = 0;
    } else {
      lastTapAt = nowAt;
    }
  }, { passive: false });

  requestAnimationFrame(renderLoop);
})();
