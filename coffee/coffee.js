'use strict';

const $ = id => document.getElementById(id);
const { clamp } = Pixel;
const rawRole = location.pathname.split('/')[2] || 'lobby';
const role = rawRole === 'bath' ? 'bath' : rawRole;
const canvas = $('screen');
const ctx = canvas.getContext('2d');

const scene = document.createElement('canvas');
scene.width = 440;
scene.height = 320;
const face = scene.getContext('2d');
face.scale(2, 2);

const fluid = (role === 'pour' || role === 'bath') ? new CoffeeLiquid(Pixel.liquidOutline) : null;
const waves = new Float32Array(31), waveSpeed = new Float32Array(31);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const owner = crypto.randomUUID?.() || `carafe-${Math.random().toString(36).slice(2)}`;
const flightMs = 165;
const full = 0.8;

let snapshot, connected = false, sentSeq = 0, sending = false;
let serverOffset = 0, bestRtt = Infinity, prev = performance.now();
let rawAngle = 0, angle = 0, amount = 0, flow = 0;
let gravityStrength = 1, shakeX = 0, shakeY = 0;
let lastSubmit = -Infinity, sentFlow = 0, motionBaseline, motionEnabled = false;

const params = new URLSearchParams(location.search);
const isEmbedFrame = params.get('embed') === '1' || window.self !== window.top;
const apk = role === 'holo' && params.get('apk') === '1';
const selectedMode = params.get('mode');
const autoStrike = apk || selectedMode === 'auto';
let isStrikeMode = role === 'holo' && selectedMode === 'strike';
let forcedStrike = selectedMode === 'strike' ? true : null;
let strikeEnabled = false;
let latestStrikeState = null;

// 全息端、工位端、以及手机端均订阅 Strike 状态流以实现三端零延迟自动感应联动
const strikeHolo = new StrikeHoloController(state => {
  latestStrikeState = state;
  strikeEnabled = state.enabled;
  if (role === 'holo') {
    const active = forcedStrike ?? Boolean(strikeEnabled || (state.state && !['OFFICE_IDLE', 'OFFICE_WORK'].includes(state.state)));
    if ((autoStrike || selectedMode === 'strike' || !params.get('lock')) && active !== isStrikeMode) {
      showStrike(active);
    }
  }
  if (role === 'pour' || role === 'bath') {
    onStrikeStateForPhone(state);
  }
});

let four = params.get('faces') === '4';
let flip = false, fill = 0, newestImpact = 0, lastSound = -Infinity, splashes = [];
let spoke = false, sound, water, waterGain, thanks;
let httpsUrl = '', motionEvents = 0;
let fullVibrated = false;

// 手机端当前是否处于「泡澡与搓澡触控模式」
let inBathTouchMode = (role === 'bath');
let currentBathStep = 'push'; // 'push' | 'knob' | 'scrub'
let tubDragOffsetY = 0;
let tubPushed = false;
let knobAngle = 0;
let bathTemp = 42;
let bathFoam = 75;
let spongePos = { x: 0.5, y: 0.58, active: false, zone: 'back' };
let foamParticles = [];
let lastScrubPost = 0;

const wall = () => performance.timeOrigin + performance.now();

async function calibrateClock() {
  for (let i = 0; i < 3; i++) {
    try {
      const start = wall();
      const response = await fetch('/coffee/clock', { cache: 'no-store' });
      const { now } = await response.json();
      const end = wall();
      if (end - start < bestRtt) {
        bestRtt = end - start;
        serverOffset = now - (start + end) / 2;
      }
    } catch { return; }
  }
}

function apply(next) {
  if (snapshot && (next.round < snapshot.round || next.now < snapshot.now)) return;
  if (!snapshot || next.round !== snapshot.round) {
    amount = fill = next.base;
    sentSeq = 0;
    newestImpact = next.now - 90;
    flow = 0;
    fluid?.reset(next.sent);
    waves.fill(0);
    waveSpeed.fill(0);
    splashes = [];
    spoke = Boolean(next.lastLand && next.now > next.lastLand + 3200);
    fullVibrated = false;
  }
  if (bestRtt === Infinity) serverOffset = next.now - wall();
  snapshot = next;
  amount = next.owner !== owner ? next.sent : Math.max(amount, next.sent);
  if (fluid && next.owner !== owner && Math.abs(fluid.amount - next.sent) > 0.002) {
    fluid.reset(next.sent);
  }
}

function connection(on) {
  connected = on;
  const badge = $('connection');
  if (badge) {
    badge.dataset.online = String(on);
    badge.textContent = on ? '● 局域网已连接' : '○ 正在重连';
  }
  const resetBtn = $('reset');
  if (resetBtn) resetBtn.disabled = !on;
  const resetPour = $('reset-pour');
  if (resetPour) resetPour.disabled = !on;
}

let events = null;
if (isEmbedFrame && typeof BroadcastChannel !== 'undefined') {
  let lastBusAt = 0;
  const pullCoffee = () => fetch('/coffee/status', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(snap => { if (snap) { apply(snap); connection(true); } })
    .catch(() => connection(false));
  const bus = new BroadcastChannel('codex-holo-bus');
  bus.onmessage = e => {
    if (e.data?.coffee) {
      lastBusAt = performance.now();
      apply(e.data.coffee);
      connection(true);
    }
  };
  pullCoffee();
  calibrateClock();
  setInterval(() => {
    if (performance.now() - lastBusAt > 1800) pullCoffee();
  }, 1500);
} else {
  events = new EventSource('/coffee/events');
  events.onmessage = e => { apply(JSON.parse(e.data)); connection(true); };
  events.onerror = () => { connection(false); setNote('连接恢复中...'); };
  events.onopen = () => { bestRtt = Infinity; calibrateClock(); };
  setInterval(() => { if (connected) { bestRtt = Infinity; calibrateClock(); } }, 60000);
  const closeEvents = () => { try { events?.close(); } catch {} };
  window.addEventListener('pagehide', closeEvents);
  window.addEventListener('beforeunload', closeEvents);
}

async function post(path, data) {
  const response = await fetch('/coffee/' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  apply(await response.json());
}

async function postStrike(action, data = {}) {
  try {
    const response = await fetch('/api/strike/' + action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (response.ok) {
      const snap = await response.json();
      latestStrikeState = snap;
      onStrikeStateForPhone(snap);
      return snap;
    }
  } catch {}
  return null;
}

function setNote(message) {
  const note = $('note');
  if (note) note.textContent = message;
  const pNote = $('pour-note');
  if (pNote) pNote.textContent = message;
}

function unlockAudio() {
  strikeHolo?.unlock();
  try {
    if (!sound) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      sound = new AudioCtx();

      const noise = sound.createBuffer(1, sound.sampleRate * 2, sound.sampleRate);
      const samples = noise.getChannelData(0);
      for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1;

      water = sound.createBufferSource();
      water.buffer = noise;
      water.loop = true;

      const filter = sound.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.value = 650;
      filter.Q.value = 0.6;

      waterGain = sound.createGain();
      waterGain.gain.value = 0;

      water.connect(filter).connect(waterGain).connect(sound.destination);
      water.start();

      if (role === 'desk') {
        fetch('/coffee/thanks.wav').then(res => {
          if (!res.ok) throw new Error('voice unavailable');
          return res.arrayBuffer();
        }).then(data => sound.decodeAudioData(data)).then(buffer => {
          thanks = buffer;
        }).catch(() => {});
      }
    }
    sound.resume().catch(() => {});
  } catch {
    setNote('声音不可用，动画仍可正常进行。');
  }
}

function impact(energy, first) {
  if (sound?.state !== 'running') return;
  const at = sound.currentTime;
  if (first) {
    const osc = sound.createOscillator();
    const gain = sound.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(1450, at);
    osc.frequency.exponentialRampToValueAtTime(520, at + 0.12);
    gain.gain.setValueAtTime(0.001, at);
    gain.gain.exponentialRampToValueAtTime(0.22 * Math.min(1.2, energy + 0.5), at + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.15);
    osc.connect(gain).connect(sound.destination);
    osc.start(at);
    osc.stop(at + 0.16);
  }
  for (const [frequency, decay, weight] of [[480, 0.12, 0.65], [1150, 0.07, 0.3], [1850, 0.05, 0.15]]) {
    const tone = sound.createOscillator();
    const volume = sound.createGain();
    tone.type = 'sine';
    tone.frequency.setValueAtTime(frequency, at);
    tone.frequency.exponentialRampToValueAtTime(frequency * 0.82, at + decay);
    volume.gain.setValueAtTime(0.002, at);
    volume.gain.exponentialRampToValueAtTime((first ? 0.09 : 0.04) * weight * (0.6 + 0.4 * energy), at + 0.006);
    volume.gain.exponentialRampToValueAtTime(0.0001, at + decay);
    tone.connect(volume).connect(sound.destination);
    tone.start(at);
    tone.stop(at + decay + 0.01);
  }
}

function sayThanks() {
  if (sound?.state !== 'running') return;
  if (thanks) {
    const voice = sound.createBufferSource();
    const gain = sound.createGain();
    voice.buffer = thanks;
    gain.gain.value = 0.85;
    voice.connect(gain).connect(sound.destination);
    voice.start();
  } else if ('speechSynthesis' in window) {
    const voice = new SpeechSynthesisUtterance('Thanks.');
    voice.lang = 'en-US';
    voice.rate = 0.88;
    voice.volume = 0.75;
    speechSynthesis.speak(voice);
  }
}

function onMotion(event) {
  const g = event.accelerationIncludingGravity;
  if (!g || g.x == null || g.y == null) return;
  motionEvents++;
  const a = event.acceleration;
  const ax = a?.x || 0, ay = a?.y || 0;
  const gx = g.x - ax, gy = g.y - ay;
  if (Math.hypot(gx, gy) < 2.5) return;

  if (!motionBaseline) {
    motionBaseline = { x: gx, y: gy };
    setNote('基准已锁定！将手机向左倾倒即可倒咖啡。');
    $('pour-drawer')?.classList.remove('open');
  }

  const { x, y } = motionBaseline;
  rawAngle = Math.atan2(gx * y - gy * x, gx * x + gy * y);
  const magnitude = x * x + y * y;
  gravityStrength = clamp(Math.hypot(gx, gy) / Math.sqrt(magnitude), 0.5, 1.5);
  shakeX = clamp(-(ax * y - ay * x) / magnitude, -2, 2);
  shakeY = clamp(-(ax * x + ay * y) / magnitude, -2, 2);
}

async function enableTilt() {
  unlockAudio();
  if (motionEnabled) {
    motionBaseline = undefined;
    setNote('重新校准中，请竖直拿稳手机...');
    return;
  }
  if (!window.isSecureContext || !window.DeviceMotionEvent) {
    if (httpsUrl) {
      setNote('正在跳转到 HTTPS 倾斜页面...');
      location.href = httpsUrl + '#tilt';
      return;
    }
    setNote('当前为 HTTP 页面，您可以直接用手指在咖啡壶上向左滑动倒咖啡，或按下方步骤信任证书。');
    const setup = $('pour-setup');
    if (setup) setup.open = true;
    return;
  }
  try {
    if (typeof DeviceMotionEvent.requestPermission === 'function') {
      const state = await DeviceMotionEvent.requestPermission();
      if (state !== 'granted') {
        setNote('Safari 动作权限未开启，请直接在屏幕上滑动或用滑条倒咖啡。');
        return;
      }
    }
    window.addEventListener('devicemotion', onMotion);
    motionEnabled = true;
    const btn = $('arm-tilt');
    if (btn) btn.textContent = '重新校准基准';
    setNote('竖直拿稳手机完成基准校准。');
  } catch {
    setNote('动作权限暂不可用，可直接滑动屏幕或使用滑条。');
  }
}

// ============================================================================
// 手机端：泡澡与搓澡三步交互逻辑 (推入浴缸 -> 旋钮调温 -> 清洁海绵搓澡)
// ============================================================================
function setBathMode(active, stepOverride = null) {
  inBathTouchMode = active;
  const layer = $('bath-touch-layer');
  const swBtn = $('touch-mode-switch');
  const statusPill = $('pour-status');
  if (layer) layer.hidden = !active;
  if (swBtn) {
    swBtn.textContent = active ? '☕ 切回倒咖啡' : '🛁 切到泡澡搓澡';
    swBtn.classList.remove('alert-bath');
  }
  if (active && statusPill) {
    statusPill.textContent = '🛁 全息洗浴 & 桌宠去污中心';
  }
  if (stepOverride) {
    switchBathStep(stepOverride);
  }
}

function switchBathStep(step) {
  currentBathStep = step;
  ['push', 'knob', 'scrub'].forEach(s => {
    const tab = $('tab-step-' + s);
    const panel = $('panel-step-' + s);
    if (tab) tab.classList.toggle('active', s === step);
    if (panel) panel.hidden = (s !== step);
  });
}

function onStrikeStateForPhone(state) {
  if (!state) return;
  const st = state.state;
  const swBtn = $('touch-mode-switch');
  const toast = $('pour-toast');

  // 当小人甩泥罢工变脏 (STRIKE) 时，自动提示或切换到推浴缸界面
  if (st === 'STRIKE') {
    if (!inBathTouchMode) {
      swBtn?.classList.add('alert-bath');
      if (toast) {
        toast.hidden = false;
        toast.textContent = '💥 小人浑身是泥罢工啦！点此立即推入浴缸泡澡搓澡 🛁';
        toast.onclick = () => {
          toast.hidden = true;
          setBathMode(true, 'push');
        };
      }
      // 自动切入泡澡界面，体验无缝连贯！
      setBathMode(true, 'push');
    } else if (currentBathStep !== 'push') {
      tubPushed = false;
      tubDragOffsetY = 0;
      switchBathStep('push');
    }
  } else if (st === 'BATH_ENTER' || st === 'BATH_SOAK') {
    if (!inBathTouchMode) setBathMode(true, 'knob');
    else if (currentBathStep === 'push') switchBathStep('knob');
    updateKnobUI(state.bath || {});
  } else if (st === 'BATH_RETURN' || st === 'SCRUBBING' || st === 'CLEAN_DONE') {
    if (!inBathTouchMode) setBathMode(true, 'scrub');
    else if (currentBathStep !== 'scrub') switchBathStep('scrub');
    updateScrubUI(state);
  }
}

function updateKnobUI(bath) {
  const temp = Math.round(bath.temp ?? bathTemp);
  const foam = Math.round(bath.foam ?? bathFoam);
  bathTemp = temp;
  bathFoam = foam;
  const tSlider = $('bath-temp-slider');
  const fSlider = $('bath-foam-slider');
  if (tSlider && document.activeElement !== tSlider) tSlider.value = String(temp);
  if (fSlider && document.activeElement !== fSlider) fSlider.value = String(foam);

  const valText = $('thermo-val-text');
  const barFill = $('thermo-bar-fill');
  const reactText = $('knob-reaction-text');
  const pct = clamp((temp - 18) / (92 - 18), 0.05, 1) * 100;
  if (barFill) barFill.style.height = `${pct}%`;

  if (temp >= 72) {
    if (valText) { valText.textContent = `${temp}°C 过烫!`; valText.style.color = '#dc2626'; }
    if (reactText) {
      reactText.textContent = `🦞 哇呀！！水温 ${temp}°C 过烫！全息小人浑身烫红像煮熟龙虾一样跳出水面乱叫啦！`;
      reactText.style.color = '#dc2626';
    }
  } else if (temp < 30) {
    if (valText) { valText.textContent = `${temp}°C 偏凉`; valText.style.color = '#0284c7'; }
    if (reactText) {
      reactText.textContent = `❄️ 当前水温 ${temp}°C 偏凉，顺时针拧动旋钮加点热水和彩色泡泡吧～`;
      reactText.style.color = '#0369a1';
    }
  } else {
    if (valText) { valText.textContent = `${temp}°C 温暖`; valText.style.color = '#15803d'; }
    if (reactText) {
      reactText.textContent = `😌 当前水温 ${temp}°C 温暖舒适：全息小人正眯着眼享受彩色泡泡浴，小黄鸭在水面晃悠～`;
      reactText.style.color = '#15803d';
    }
  }
}

function updateScrubUI(state) {
  const bath = state.bath || {};
  const cleanPct = Math.round(bath.clean_progress || 0);
  const pctEl = $('scrub-pct-text');
  const reactEl = $('scrub-reaction-text');
  if (pctEl) pctEl.textContent = `${cleanPct}%`;

  if (state.state === 'CLEAN_DONE' || cleanPct >= 100) {
    if (reactEl) {
      reactEl.textContent = '✨ 叮！100% 污泥洗净！电脑桌宠周身冒出金色小星星，已换回干净办公室衣服坐回工位！';
      reactEl.style.color = '#15803d';
    }
  } else if (bath.scrub_zone === 'head') {
    if (reactEl) {
      reactEl.textContent = '❓ 哈哈！你搓到小人脑袋啦！电脑桌宠瞬间僵住猛扭回头，头顶弹出大大的黑色问号【❓】无语地瞪着你！';
      reactEl.style.color = '#b91c1c';
    }
  } else if (bath.scrub_zone === 'back') {
    if (reactEl) {
      reactEl.textContent = `🧽 正在擦拭后背泥斑 (${cleanPct}%)：电脑小人舒服得眯眼哼哼 (~ ♪)，身体 Q 弹晃动冒出雪白泡沫！`;
      reactEl.style.color = '#0369a1';
    }
  }
}

// 绘制手机端三大交互 Canvas
function drawBathTouchCanvases(now) {
  if (!inBathTouchMode) return;
  const clock = now / 1000;

  // 1. 绘制推入浴缸 Canvas (#tub-push-canvas)
  const pushCanvas = $('tub-push-canvas');
  if (pushCanvas && currentBathStep === 'push') {
    const g = pushCanvas.getContext('2d');
    g.clearRect(0, 0, 320, 240);
    g.save();
    const dy = tubPushed ? -190 : Math.min(20, tubDragOffsetY);
    g.translate(160, 145 + dy);
    g.scale(2.1, 2.1);

    // 底部水纹光圈
    g.fillStyle = 'rgba(56, 189, 248, 0.22)';
    g.beginPath();
    g.ellipse(0, 14, 52, 10, 0, 0, Math.PI * 2);
    g.fill();

    // 彩色肥皂泡沫云
    const cols = ['#ffffff', '#fce7f3', '#e0f2fe', '#dcfce7', '#fef3c7'];
    for (let i = 0; i < 13; i++) {
      g.fillStyle = cols[i % cols.length];
      const bx = -36 + i * 6;
      const by = -18 - Math.sin(clock * 4 + i) * 2.5;
      g.fillRect(Math.round(bx - 5), Math.round(by - 5), 10, 9);
    }

    // 漂浮的黄色橡皮小鸭子
    const dx = 18 + Math.sin(clock * 3) * 3;
    const duckY = -22 + Math.cos(clock * 3.5) * 1.5;
    g.fillStyle = '#facc15';
    g.fillRect(Math.round(dx - 6), Math.round(duckY - 2), 12, 5);
    g.fillStyle = '#fde047';
    g.fillRect(Math.round(dx - 4), Math.round(duckY - 7), 8, 6);
    g.fillStyle = '#f97316';
    g.fillRect(Math.round(dx - 8), Math.round(duckY - 5), 4, 3);
    g.fillStyle = '#09090d';
    g.fillRect(Math.round(dx - 2), Math.round(duckY - 5), 2, 2);

    // 像素橡木桶浴缸
    g.fillStyle = '#211c2c';
    g.fillRect(-44, -16, 88, 28);
    g.fillStyle = '#92400e';
    g.fillRect(-42, -14, 84, 24);
    for (let x = -34; x <= 34; x += 10) {
      g.fillStyle = '#b45309';
      g.fillRect(x, -14, 5, 24);
    }
    g.fillStyle = '#d97706';
    g.fillRect(-46, -18, 92, 4);
    g.fillStyle = '#fbbf24';
    g.fillRect(-41, -6, 82, 3);
    g.fillRect(-39, 3, 78, 3);
    g.restore();
  }

  // 2. 绘制水龙头旋钮 Canvas (#faucet-knob-canvas)
  const knobCanvas = $('faucet-knob-canvas');
  if (knobCanvas && currentBathStep === 'knob') {
    const g = knobCanvas.getContext('2d');
    g.clearRect(0, 0, 210, 210);
    g.save();
    g.translate(105, 105);

    // 外圈冷温烫刻度弧
    const arcCols = [
      [-Math.PI * 0.85, -Math.PI * 0.35, '#38bdf8'],
      [-Math.PI * 0.35, Math.PI * 0.25, '#4ade80'],
      [Math.PI * 0.25, Math.PI * 0.85, '#ef4444'],
    ];
    for (const [a1, a2, col] of arcCols) {
      g.strokeStyle = col;
      g.lineWidth = 10;
      g.lineCap = 'round';
      g.beginPath();
      g.arc(0, 0, 82, a1 - Math.PI / 2, a2 - Math.PI / 2);
      g.stroke();
    }

    // 旋钮旋转角度映射
    const norm = (bathTemp - 18) / (92 - 18);
    const rot = (norm - 0.5) * Math.PI * 1.5;
    g.rotate(rot);

    // 十字黄铜像素水龙头旋钮
    g.fillStyle = '#1e293b';
    g.beginPath();
    g.arc(0, 0, 62, 0, Math.PI * 2);
    g.fill();

    g.fillStyle = bathTemp >= 72 ? '#ef4444' : (bathTemp < 30 ? '#0284c7' : '#f59e0b');
    g.fillRect(-18, -56, 36, 112);
    g.fillRect(-56, -18, 112, 36);

    g.fillStyle = '#fde68a';
    g.beginPath();
    g.arc(0, 0, 28, 0, Math.PI * 2);
    g.fill();

    // 顶部指向三角形
    g.fillStyle = '#ffffff';
    g.beginPath();
    g.moveTo(0, -52);
    g.lineTo(-9, -34);
    g.lineTo(9, -34);
    g.closePath();
    g.fill();

    g.restore();
  }

  // 3. 绘制清洁海绵擦/搓澡巾触摸板 Canvas (#sponge-pad-canvas)
  const spongeCanvas = $('sponge-pad-canvas');
  if (spongeCanvas && currentBathStep === 'scrub') {
    const g = spongeCanvas.getContext('2d');
    const W = 340, H = 290;
    g.fillStyle = '#0f172a';
    g.fillRect(0, 0, W, H);

    const bath = latestStrikeState?.bath || {};
    const cleanPct = Number(bath.clean_progress || 0);
    const dirtyRatio = Math.max(0, 1 - cleanPct / 100);
    const isQuestion = bath.scrub_zone === 'head' || (Date.now() < (bath.question_until || 0));

    // 分区引导线：上方 34% 为【⚠️ 头部禁区（搓这里猛扭头弹大黑问号❓）】，下方为【✨ 后背去污区】
    const splitY = Math.round(H * 0.34);
    g.fillStyle = isQuestion ? 'rgba(239, 68, 68, 0.22)' : 'rgba(248, 113, 113, 0.08)';
    g.fillRect(0, 0, W, splitY);
    g.fillStyle = 'rgba(56, 189, 248, 0.08)';
    g.fillRect(0, splitY, W, H - splitY);

    g.strokeStyle = '#475569';
    g.setLineDash([6, 4]);
    g.beginPath();
    g.moveTo(12, splitY);
    g.lineTo(W - 12, splitY);
    g.stroke();
    g.setLineDash([]);

    g.font = 'bold 12px sans-serif';
    g.fillStyle = '#fca5a5';
    g.fillText('⚠️ 头部禁区 (滑到这里 → 小人僵住猛扭头弹出大黑问号 ❓)', 14, 22);
    g.fillStyle = '#7dd3fc';
    g.fillText('✨ 后背去污区 (在此处左右滑动海绵 → 舒服眯眼擦除泥斑)', 14, splitY + 20);

    // 绘制中央 100% 背对镜头的 Q 版小人背影轮廓（供用户直观对准擦拭）
    const cx = W / 2, cy = 238;
    g.save();
    g.translate(cx, cy);
    g.scale(2.2, 2.2);

    // 深蓝小黄鸭卡通平角大短裤 (PG 合规铁律)
    g.fillStyle = '#1d3b6e';
    g.fillRect(-19, -29, 38, 17);
    g.fillStyle = '#facc15';
    g.fillRect(-13, -21, 5, 4);
    g.fillRect(8, -21, 5, 4);

    // 背部躯干
    g.fillStyle = '#e5ad8b';
    g.fillRect(-16, -54, 32, 27);
    g.fillStyle = '#ca8e7e';
    g.fillRect(-1, -51, 2, 20);

    // 背部待擦除的深褐色泥斑
    const mudSpots = [[-11,-50,8,6],[4,-51,9,6],[-5,-42,9,5],[-13,-37,7,5],[6,-38,8,5]];
    const showSpots = Math.ceil(mudSpots.length * dirtyRatio);
    for (let i = 0; i < showSpots; i++) {
      const [mx, my, mw, mh] = mudSpots[i];
      g.fillStyle = '#5c3824';
      g.fillRect(mx, my, mw, mh);
    }

    // 腰部纯白泡泡云团与搞笑像素马赛克方块
    g.fillStyle = '#f8fafc';
    g.fillRect(-20, -32, 40, 8);
    const mCols = ['#f8dfa1', '#d4957a', '#f3c69f', '#b87b64'];
    for (let c = 0; c < 5; c++) {
      g.fillStyle = mCols[(c + Math.floor(clock * 6)) % mCols.length];
      g.fillRect(-10 + c * 4, -29, 4, 6);
    }

    // 地中海微秃后脑勺与两侧深紫棕卷发
    g.fillStyle = '#392e48';
    g.fillRect(-15, -79, 30, 23);
    g.fillStyle = '#63506b';
    g.fillRect(-12, -77, 24, 10);
    g.fillStyle = '#d99a88';
    g.fillRect(-6, -76, 12, 4);

    if (isQuestion) {
      // 猛扭回头瞪眼 + 超大黑色问号 ❓
      g.fillStyle = '#e9b296';
      g.fillRect(-1, -74, 15, 16);
      g.fillStyle = '#111118';
      g.fillRect(2, -69, 4, 4);
      g.fillRect(9, -69, 4, 4);
      g.fillStyle = '#fff9db';
      g.fillRect(-10, -104, 20, 20);
      g.fillStyle = '#09090d';
      g.font = 'bold 16px monospace';
      g.fillText('?', -4, -88);
    }
    g.restore();

    // 绘制飞舞的白色雪花泡沫粒子
    foamParticles = foamParticles.filter(p => p.life > 0);
    for (const p of foamParticles) {
      p.x += p.vx;
      p.y += p.vy;
      p.life -= 0.04;
      g.fillStyle = p.gold ? `rgba(253, 224, 71, ${p.life})` : `rgba(255, 255, 255, ${p.life})`;
      g.beginPath();
      g.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      g.fill();
    }

    // 绘制跟随手指滑动的【粗糙黄色/绿色清洁海绵擦 (Cleaning Sponge / Cloth)】
    const sx = spongePos.x * W;
    const sy = spongePos.y * H;
    g.save();
    g.translate(sx, sy);
    if (spongePos.active) {
      g.rotate(Math.sin(clock * 25) * 0.12);
    }
    // 绿色百洁布底层
    g.fillStyle = '#15803d';
    g.fillRect(-34, -18, 68, 42);
    // 亮黄色粗糙海绵顶层
    g.fillStyle = '#facc15';
    g.fillRect(-34, -22, 68, 34);
    g.strokeStyle = '#ca8a04';
    g.lineWidth = 2;
    g.strokeRect(-34, -22, 68, 34);
    // 海绵粗糙气孔像素点
    g.fillStyle = '#a16207';
    for (const [px, py] of [[-22,-12],[-10,-6],[4,-14],[18,-8],[-16,2],[0,4],[16,2],[-6,-15]]) {
      g.fillRect(px, py, 4, 4);
    }
    g.fillStyle = '#0f172a';
    g.font = 'bold 11px sans-serif';
    g.fillText('🧽 清洁海绵擦', -30, 0);
    g.restore();
  }
}

function initBathTouchEvents() {
  const swBtn = $('touch-mode-switch');
  if (swBtn) {
    swBtn.onclick = () => {
      unlockAudio();
      const nextBath = !inBathTouchMode;
      setBathMode(nextBath);
      fetch('/api/pet/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: nextBath ? 'strike' : 'coffee', spawn: true }),
      }).catch(() => {});
    };
  }

  ['push', 'knob', 'scrub'].forEach(s => {
    const tab = $('tab-step-' + s);
    if (tab) {
      tab.onclick = () => {
        unlockAudio();
        switchBathStep(s);
      };
    }
  });

  const backTopBtn = $('btn-back-office-top');
  if (backTopBtn) {
    backTopBtn.onclick = () => {
      unlockAudio();
      postStrike('return_office', {});
      setBathMode(false);
    };
  }

  // 第一步：向上推入浴缸手势
  const pushZone = $('tub-push-zone');
  let dragStartY = null;
  const triggerPushTub = () => {
    unlockAudio();
    strikeHolo?.sound('slide');
    tubPushed = true;
    postStrike('bath_push', {}).then(() => {
      setTimeout(() => {
        tubPushed = false;
        tubDragOffsetY = 0;
        switchBathStep('knob');
      }, 450);
    });
  };

  if (pushZone) {
    pushZone.addEventListener('pointerdown', e => {
      unlockAudio();
      dragStartY = e.clientY;
      tubDragOffsetY = 0;
      pushZone.setPointerCapture?.(e.pointerId);
    });
    pushZone.addEventListener('pointermove', e => {
      if (dragStartY == null) return;
      const dy = e.clientY - dragStartY;
      tubDragOffsetY = Math.min(20, dy);
      if (dy < -55) {
        dragStartY = null;
        triggerPushTub();
      }
    });
    pushZone.addEventListener('pointerup', () => {
      if (dragStartY != null && tubDragOffsetY < -35) {
        triggerPushTub();
      } else {
        tubDragOffsetY = 0;
      }
      dragStartY = null;
    });
  }

  const quickPushBtn = $('btn-quick-push');
  if (quickPushBtn) quickPushBtn.onclick = triggerPushTub;

  // 第二步：旋转水龙头旋钮与滑条调温
  const knobCanvas = $('faucet-knob-canvas');
  let knobDragging = false;
  let lastKnobPost = 0;
  const syncKnobToServer = (tempVal, foamVal, force = false) => {
    bathTemp = clamp(Math.round(tempVal), 18, 92);
    bathFoam = clamp(Math.round(foamVal), 25, 100);
    updateKnobUI({ temp: bathTemp, foam: bathFoam });
    const now = performance.now();
    if (force || now - lastKnobPost > 90) {
      lastKnobPost = now;
      postStrike('bath_knob', { temp: bathTemp, foam: bathFoam });
    }
  };

  if (knobCanvas) {
    const updateFromPointer = e => {
      const rect = knobCanvas.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const ang = Math.atan2(e.clientY - cy, e.clientX - cx) + Math.PI / 2;
      let norm = (ang / (Math.PI * 1.5)) + 0.5;
      norm = clamp(norm, 0, 1);
      const newTemp = 18 + norm * (92 - 18);
      const newFoam = Math.min(100, bathFoam + 1.5);
      syncKnobToServer(newTemp, newFoam);
    };
    knobCanvas.addEventListener('pointerdown', e => {
      unlockAudio();
      knobDragging = true;
      knobCanvas.setPointerCapture?.(e.pointerId);
      updateFromPointer(e);
    });
    knobCanvas.addEventListener('pointermove', e => {
      if (knobDragging) updateFromPointer(e);
    });
    knobCanvas.addEventListener('pointerup', () => {
      knobDragging = false;
      syncKnobToServer(bathTemp, bathFoam, true);
    });
  }

  const tSlider = $('bath-temp-slider');
  const fSlider = $('bath-foam-slider');
  if (tSlider) {
    tSlider.addEventListener('input', e => syncKnobToServer(Number(e.target.value), bathFoam, true));
  }
  if (fSlider) {
    fSlider.addEventListener('input', e => syncKnobToServer(bathTemp, Number(e.target.value), true));
  }

  document.querySelectorAll('.preset-btn[data-temp]').forEach(btn => {
    btn.addEventListener('click', () => {
      unlockAudio();
      syncKnobToServer(Number(btn.dataset.temp), Math.max(80, bathFoam), true);
    });
  });

  const goScrubBtn = $('btn-go-scrub');
  if (goScrubBtn) {
    goScrubBtn.onclick = () => {
      unlockAudio();
      postStrike('scrub_start', { immediate: false });
      switchBathStep('scrub');
    };
  }

  // 第三步：清洁海绵擦触摸板滑动搓背与搓头问号触发
  const spongeCanvas = $('sponge-pad-canvas');
  let lastPointer = null;
  if (spongeCanvas) {
    const handleScrubPointer = (e, isDown = false) => {
      const rect = spongeCanvas.getBoundingClientRect();
      const nx = clamp((e.clientX - rect.left) / rect.width, 0.05, 0.95);
      const ny = clamp((e.clientY - rect.top) / rect.height, 0.05, 0.95);
      const dx = lastPointer ? clamp((nx - lastPointer.x) * 8, -1, 1) : 0;
      const dy = lastPointer ? clamp((ny - lastPointer.y) * 8, -1, 1) : 0;
      const moveDist = lastPointer ? Math.hypot(nx - lastPointer.x, ny - lastPointer.y) : 0.04;
      lastPointer = { x: nx, y: ny };

      const zone = ny < 0.34 ? 'head' : 'back';
      spongePos = { x: nx, y: ny, active: true, zone };

      // 生成白色雪花泡沫粒子与星光
      for (let i = 0; i < 3; i++) {
        foamParticles.push({
          x: nx * 340 + (Math.random() - 0.5) * 24,
          y: ny * 290 + (Math.random() - 0.5) * 20,
          vx: (Math.random() - 0.5) * 2.5,
          vy: -0.8 - Math.random() * 1.8,
          r: 2.5 + Math.random() * 3.5,
          life: 1.0,
          gold: zone === 'back' && Math.random() > 0.7,
        });
      }

      const now = performance.now();
      if (isDown || (moveDist > 0.008 && now - lastScrubPost > 65)) {
        lastScrubPost = now;
        const delta = zone === 'back' ? Math.max(1.8, moveDist * 38) : 0;
        postStrike('scrub_move', { x: nx, y: ny, dx, dy, zone, delta });
      }
    };

    spongeCanvas.addEventListener('pointerdown', e => {
      unlockAudio();
      lastPointer = null;
      spongeCanvas.setPointerCapture?.(e.pointerId);
      handleScrubPointer(e, true);
    });
    spongeCanvas.addEventListener('pointermove', e => {
      if (spongePos.active) handleScrubPointer(e, false);
    });
    spongeCanvas.addEventListener('pointerup', () => {
      spongePos.active = false;
      lastPointer = null;
    });
  }

  const simBackBtn = $('btn-sim-scrub-back');
  if (simBackBtn) {
    simBackBtn.onclick = () => {
      unlockAudio();
      spongePos = { x: 0.5, y: 0.62, active: true, zone: 'back' };
      postStrike('scrub_move', { x: 0.5, y: 0.62, dx: 0.65, dy: 0.2, zone: 'back', delta: 20 });
    };
  }
  const simHeadBtn = $('btn-sim-scrub-head');
  if (simHeadBtn) {
    simHeadBtn.onclick = () => {
      unlockAudio();
      spongePos = { x: 0.5, y: 0.18, active: true, zone: 'head' };
      postStrike('scrub_move', { x: 0.5, y: 0.18, dx: 0.0, dy: 0.0, zone: 'head', delta: 0 });
    };
  }
  const simFinishBtn = $('btn-sim-scrub-finish');
  if (simFinishBtn) {
    simFinishBtn.onclick = () => {
      unlockAudio();
      spongePos = { x: 0.5, y: 0.6, active: true, zone: 'back' };
      postStrike('scrub_move', { x: 0.5, y: 0.6, dx: 0.5, dy: 0.2, zone: 'back', delta: 100 });
    };
  }
}

// 1. iPhone 倒咖啡绘制循环
function drawPour(now, dt) {
  if (inBathTouchMode) {
    drawBathTouchCanvases(now);
    return;
  }
  const difference = Math.atan2(Math.sin(rawAngle - angle), Math.cos(rawAngle - angle));
  angle += difference * (1 - Math.exp(-dt / 45));

  const available = connected && snapshot && (!snapshot.owner || snapshot.owner === owner || wall() + serverOffset - snapshot.sampleAt > 1400);

  const gx = -Math.sin(angle) * gravityStrength * 920 + shakeX * 320;
  const gy = Math.cos(angle) * gravityStrength * 800 + shakeY * 320;

  fluid.update(dt, gx, gy, available);
  amount = fluid.amount;
  flow = fluid.rate < 0.005 ? 0 : fluid.rate;

  if (available && !sending && now - lastSubmit >= 40 && (fluid.transferAmount > snapshot.sent + 0.00001 || sentFlow !== flow && !flow)) {
    lastSubmit = now;
    sending = true;
    sentFlow = flow;
    post('pour', {
      round: snapshot.round,
      owner,
      seq: ++sentSeq,
      amount: fluid.transferAmount,
      flow
    }).catch(() => {
      sentFlow = -1;
    }).finally(() => { sending = false; });
  }

  if (sound?.state === 'running') {
    waterGain.gain.setTargetAtTime(flow * 0.05, sound.currentTime, 0.08);
  }

  const pourPct = Math.round(100 * amount);
  const statusPill = $('pour-status');
  const toast = $('pour-toast');

  if (statusPill) {
    statusPill.classList.remove('warning', 'full');
    let tiltStr = motionBaseline ? `倾斜 ${Math.round(angle * 180 / Math.PI)}°` : '触屏左滑或点⚙️';

    if (amount >= full) {
      statusPill.classList.add('full');
      statusPill.textContent = `🎉 满杯达成 (80%)！Codex 正在接咖啡 ☕`;
      if (!fullVibrated) {
        fullVibrated = true;
        try { navigator.vibrate?.([60, 100, 60]); } catch {}
        if (toast) {
          toast.hidden = false;
          toast.textContent = '🎉 80% 满杯已达成！Codex 正在从工位过来接咖啡喝～';
          setTimeout(() => { if (toast) toast.hidden = true; }, 5000);
        }
      }
    } else if (amount >= 0.68) {
      statusPill.classList.add('warning');
      statusPill.textContent = `🟡 即将倒满！${pourPct}% / 80% · ${tiltStr}`;
    } else if (amount > 0.02) {
      statusPill.textContent = `☕ 正在倒：${pourPct}% (目标 80%) · ${tiltStr}`;
    } else {
      statusPill.textContent = `☕ 壶量 100% · 目标 80% · ${tiltStr}`;
    }
  }

  Pixel.pour(ctx, { fluid }, now);
}

// 2. 全息接水/挖土/泡澡端绘制循环
function drawHolo(now, serverNow, dt) {
  if (isStrikeMode) {
    strikeHolo.render(face);
    projectHolo();
    return;
  }
  let target = snapshot?.base || 0;
  const flight = [];

  for (const [land, amountAtLand, power] of snapshot?.parcels || []) {
    const age = (serverNow - land) / 1000;
    if (age < 0 && age >= -flightMs / 1000) {
      flight.push([1 + age * 1000 / flightMs, power]);
    }
    if (age >= 0) {
      target = amountAtLand;
      if (land > newestImpact) {
        const first = target === (snapshot?.parcels[0]?.[1]) && !snapshot.base;
        newestImpact = land;
        if (age < 0.12) {
          waveSpeed[14] += power * 12;
          waveSpeed[15] += power * 18;
          waveSpeed[16] += power * 12;
          if (!reducedMotion || first) {
            splashes.push([land, power, 130 - 31 * fill]);
          }
          if (first || land - lastSound >= 180 || target >= full) {
            impact(power, first);
            lastSound = land;
          }
        }
      }
    }
  }

  fill += (target - fill) * (1 - Math.exp(-dt / 53));
  if (target - fill < 0.00035) fill = target;

  if (sound?.state === 'running') {
    waterGain.gain.setTargetAtTime(flight.length ? 0.055 : 0, sound.currentTime, 0.07);
  }

  splashes = splashes.filter(([land]) => serverNow - land < 280);

  const lastLand = snapshot?.lastLand || 0;
  const lift = snapshot?.sent >= full ? clamp((serverNow - lastLand - 950) / 550) : 0;
  const step = Math.min(dt / 1000, 0.033);

  for (let i = 0; i < waves.length; i++) {
    const left = waves[Math.max(0, i - 1)], right = waves[Math.min(30, i + 1)];
    waveSpeed[i] += (125 * (left + right - 2 * waves[i]) - 28 * waves[i] - 5.5 * waveSpeed[i]) * step;
  }
  for (let i = 0; i < waves.length; i++) {
    waves[i] = clamp(waves[i] + waveSpeed[i] * step, -1.8, 1.8);
  }

  const model = {
    fill,
    lift,
    flight,
    waves,
    hit: Math.max(0, (serverNow - newestImpact) / 1000),
    splash: splashes.map(([land, energy, y]) => [(serverNow - land) / 1000, energy, land, y])
  };

  const amountOut = $('amount');
  if (amountOut) {
    const curPct = Math.floor(100 * fill + 0.001);
    if (fill >= full) {
      amountOut.innerHTML = `<span style="color:#ffd285;font-weight:700;text-shadow:0 0 10px rgba(255,210,133,0.85)">✨ 80% 满杯！Codex 来接啦</span>`;
    } else if (fill >= 0.68) {
      amountOut.innerHTML = `<span style="color:#f8b577;font-weight:600">🟡 ${curPct}% / 80% (即将满杯)</span>`;
    } else {
      amountOut.textContent = `${curPct}% / 80% 满`;
    }
  }

  Pixel.holo(face, model, now);
  projectHolo();
}

function projectHolo() {
  ctx.imageSmoothingEnabled = false;
  ctx.setTransform(2, 0, 0, 2, 0, 0);
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (four) {
    const turns = [[0, -104, 0], [104, 0, Math.PI / 2], [0, 104, Math.PI], [-104, 0, -Math.PI / 2]];
    for (const [x, y, rotation] of turns) {
      ctx.save();
      ctx.translate(180 + x, 180 + y);
      ctx.rotate(rotation);
      ctx.scale(flip ? 1 : -1, 1);
      ctx.drawImage(scene, -67, -49, 134, 98);
      ctx.restore();
    }
  } else {
    ctx.save();
    if (flip) {
      ctx.translate(220, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(scene, 0, 0, 220, 160);
    ctx.restore();
  }
}

function showStrike(active) {
  isStrikeMode = active;
  document.body.classList.toggle('strike-view', active);
  $('scene-name').textContent = active ? '挖土 & 泡澡全息' : '接杯全息';
  $('scene-kicker').hidden = active;
  $('amount').hidden = active;
  $('mode-toggle').textContent = active ? '切到咖啡' : '切到挖土';
  if ($('reset')) $('reset').hidden = false;
  setNote(active ? '点画面可切换清屏全屏。支持接收跨屏挖土、迎面甩泥与推入木桶泡澡！' : '对准金字塔后，可切到四面全屏。');
}

// 主渲染循环
function animate(now) {
  const dt = Math.min(50, now - prev);
  prev = now;
  const serverNow = wall() + serverOffset;

  if (role === 'pour' || role === 'bath') drawPour(now, dt);
  if (role === 'holo') drawHolo(now, serverNow, dt);
  if (role === 'desk') {
    const since = snapshot?.sent >= full ? serverNow - snapshot.lastLand - 1500 : -Infinity;
    if (!spoke && since >= 1520 && since < 1870) {
      sayThanks();
      spoke = true;
    }
    const working = snapshot?.work === 'working';
    const amountOut = $('amount');
    if (amountOut) {
      const st = latestStrikeState?.state;
      amountOut.textContent = (st && st !== 'OFFICE_IDLE') ? `状态: ${st}` : (working ? '正在工作' : '工位待机');
    }
    Pixel.desk(ctx, now, { since, working, strikeState: latestStrikeState });
  }

  requestAnimationFrame(animate);
}

function fullscreen() {
  document.body.classList.toggle('cinema');
  if (document.body.classList.contains('cinema')) {
    document.documentElement.requestFullscreen?.().catch(() => {});
  } else if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
}

// 页面初始化
if (role === 'lobby') {
  $('lobby').hidden = false;
  const cover = $('cover').getContext('2d');
  Pixel.desk(cover, 0, { since: 2800, working: true });
  fetch('/coffee/lan').then(res => res.json()).then(({ ip, http_port }) => {
    const port = http_port || location.port || 29765;
    const iphonePour = `http://${ip}:${port}/coffee/pour`;
    const iphoneBath = `http://${ip}:${port}/coffee/bath`;
    const holo = `http://${ip}:${port}/coffee/holo?mode=strike&faces=4`;
    if ($('iphone')) $('iphone').href = iphoneBath;
    if ($('iphone-pour')) $('iphone-pour').href = iphonePour;
    if ($('bath-address')) $('bath-address').textContent = iphoneBath;
    if ($('iphone-address')) $('iphone-address').textContent = iphonePour;
    if ($('holo-strike-link')) $('holo-strike-link').href = holo;
    if ($('holo-address')) $('holo-address').textContent = holo;
  }).catch(() => {});
} else {
  document.body.dataset.role = role;
  $('scene').hidden = false;

  const resetAction = () => {
    const scope = (role === 'pour' || role === 'bath')
      ? (inBathTouchMode ? 'strike' : 'coffee')
      : (isStrikeMode ? 'strike' : 'coffee');
    fetch('/api/pet/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope }),
    }).catch(() => {});
  };

  const rBtn = $('reset');
  if (rBtn) {
    rBtn.disabled = false;
    rBtn.onclick = resetAction;
  }
  const rAllBtn = $('reset-all-btn');
  if (rAllBtn) {
    rAllBtn.onclick = () => {
      fetch('/api/pet/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope: 'all' }),
      }).catch(() => {});
    };
  }
  const rPour = $('reset-pour');
  if (rPour) {
    rPour.disabled = false;
    rPour.onclick = resetAction;
  }
  const retOfficeBtn = $('return-office-btn');
  if (retOfficeBtn) {
    retOfficeBtn.onclick = () => {
      fetch('/api/pet/return_office', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      }).catch(() => {});
    };
  }

  if (role === 'pour' || role === 'bath') {
    document.querySelector('meta[name="theme-color"]').content = '#ffffff';
    canvas.width = 440;
    canvas.height = 500;
    ctx.scale(2, 2);

    $('pour-bar').hidden = false;
    const drawer = $('pour-drawer');
    const gearBtn = $('gear-btn');
    const closeDrawer = $('close-drawer');

    const toggleDrawer = () => drawer.classList.toggle('open');
    gearBtn.onclick = e => { e.stopPropagation(); toggleDrawer(); };
    closeDrawer.onclick = e => { e.stopPropagation(); drawer.classList.remove('open'); };

    // 支持直接在咖啡壶画面上按住向左滑动倾倒咖啡（HTTP 下零门槛免证书使用！）
    let pourDragStartX = null;
    canvas.addEventListener('pointerdown', e => {
      unlockAudio();
      drawer.classList.remove('open');
      pourDragStartX = e.clientX;
    });
    canvas.addEventListener('pointermove', e => {
      if (pourDragStartX == null) return;
      const dx = pourDragStartX - e.clientX;
      if (dx > 5) {
        rawAngle = clamp(dx / 140, 0, 1) * 1.8;
      } else if (dx < -10) {
        rawAngle = Math.max(0, rawAngle - 0.15);
      }
    });
    canvas.addEventListener('pointerup', () => {
      pourDragStartX = null;
      rawAngle = 0;
    });

    const armTilt = $('arm-tilt');
    if (armTilt) armTilt.onclick = enableTilt;

    const tiltSlider = $('tilt');
    if (tiltSlider) {
      tiltSlider.min = '0';
      tiltSlider.max = '100';
      tiltSlider.value = '0';
      tiltSlider.addEventListener('input', e => {
        rawAngle = (Number(e.target.value) / 100) * 1.8;
        gravityStrength = 1;
        shakeX = shakeY = 0;
      });
      tiltSlider.addEventListener('pointerdown', unlockAudio);
    }

    initBathTouchEvents();
    setBathMode(role === 'bath');
    setNote('支持手指直接在画面向左拖动倒咖啡，或点击上方「🛁 切到泡澡搓澡」体验推浴缸与海绵搓背！');
  } else {
    const exit = document.createElement('button');
    exit.id = 'exit';
    exit.textContent = '退出全屏';
    exit.hidden = true;
    exit.onclick = fullscreen;
    document.body.append(exit);

    const start = $('arm');
    if (start) {
      start.onclick = () => {
        unlockAudio();
        start.textContent = '声音已开启';
        start.disabled = true;
      };
    }

    const cinema = document.createElement('button');
    cinema.textContent = '全屏';
    cinema.onclick = fullscreen;
    $('controls').append(cinema);

    document.addEventListener('fullscreenchange', () => {
      if (!document.fullscreenElement) document.body.classList.remove('cinema');
    });

    if (role === 'holo') {
      try { flip = localStorage.getItem('holo-flip') === '1'; } catch {}
      $('scene-name').textContent = '接杯';
      $('scene-kicker').textContent = '02 / PYRAMID';
      function layout() {
        canvas.width = four ? 720 : 440;
        canvas.height = four ? 720 : 320;
        $('layout').textContent = four ? '切到单面' : '切到四面';
      }
      $('layout').hidden = $('flip').hidden = false;
      $('layout').onclick = () => { four = !four; layout(); };
      $('flip').textContent = '反转入口朝向';
      $('flip').onclick = () => {
        flip = !flip;
        try { localStorage.setItem('holo-flip', flip ? '1' : '0'); } catch {}
      };
      layout();
      showStrike(isStrikeMode);
      $('mode-toggle').hidden = false;
      $('mode-toggle').onclick = () => {
        const nextStrike = !isStrikeMode;
        forcedStrike = null;
        showStrike(nextStrike);
        fetch('/api/pet/mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: nextStrike ? 'strike' : 'coffee', spawn: true }),
        }).catch(() => {});
      };
      const bmBtn = $('mode-badminton-btn');
      if (bmBtn) {
        bmBtn.hidden = false;
        bmBtn.onclick = () => {
          fetch('/api/pet/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'badminton', spawn: true }),
          }).catch(() => {});
        };
      }
      if (isStrikeMode && params.get('embed') !== '1') {
        document.body.classList.add('cinema');
      }

      canvas.addEventListener('click', () => {
        unlockAudio();
        if (apk) {
          document.body.classList.toggle('cinema');
        } else if (params.get('embed') !== '1') {
          fullscreen();
        }
      });

      if (apk) {
        document.body.classList.add('apk', 'cinema');
        const classic = document.createElement('a');
        classic.href = '/holo?live=1&classic=1';
        classic.textContent = '原全息';
        $('controls').append(classic);
        cinema.onclick = () => document.body.classList.add('cinema');
        unlockAudio();
      }
    } else {
      canvas.width = 480;
      canvas.height = 270;
      $('scene-name').textContent = 'Codex 的工位';
      $('scene-kicker').textContent = '03 / THE NIGHT SHIFT';
      setNote('实时同步展示：敲代码、深叹气握铲跨屏离场、全屏湿泥受击、以及 100% 背对镜头合规搓澡与问号微表情。');
    }
  }

  requestAnimationFrame(animate);
}

// 仅记录可选 HTTPS 链接，绝不强行自动跳转导致未安装证书的手机断连报错！
if ((role === 'pour' || role === 'bath' || role === 'lobby') && location.protocol === 'http:') {
  fetch('/coffee/lan').then(res => res.json()).then(({ ip, tls, https_port }) => {
    if (!tls) return;
    httpsUrl = `https://${ip}:${https_port || 29766}/coffee/pour`;
    document.querySelectorAll('.tilt-url').forEach(link => link.href = httpsUrl);
    document.querySelectorAll('.tilt-setup').forEach(panel => panel.hidden = false);
  }).catch(() => {});
}
