// 电脑嘴替与全息中枢交互引擎 v20261111_pro
let actionSerial = 0;
let actionTimer = null;
let currentUtterance = null;
let systemSpeechId = null;

const actionLog = document.getElementById('lastEventLog');

// 注入通用操作条按钮
const dockLinks = document.querySelector('.dock-links');
if (dockLinks && !document.getElementById('apkDownloadLink')) {
  const apkLink = document.createElement('a');
  apkLink.id = 'apkDownloadLink';
  apkLink.className = 'dock-link';
  apkLink.href = '/download';
  apkLink.textContent = '📱 手机端 App 下载 / 桌面安装';
  dockLinks.appendChild(apkLink);
}

const footerDock = document.querySelector('.footer-dock');
if (footerDock && !document.getElementById('cancelActionButton')) {
  const stopButton = document.createElement('button');
  stopButton.id = 'cancelActionButton';
  stopButton.className = 'btn-silent';
  stopButton.style.borderColor = '#ef4444';
  stopButton.style.color = '#fca5a5';
  stopButton.textContent = '⏹ 停止电脑播报 / 取消触发';
  stopButton.onclick = () => cancelAction(true);
  footerDock.appendChild(stopButton);
}

// 初始化所有台词记忆
if (typeof CLIPS !== 'undefined' && Array.isArray(CLIPS)) {
  CLIPS.forEach(clip => {
    const input = document.getElementById(`voice-input-${clip.id}`);
    if (input) {
      input.value = localStorage.getItem(`fuzz-voice-${clip.id}`) || clip.defaultVoice;
      input.addEventListener('input', () => localStorage.setItem(`fuzz-voice-${clip.id}`, input.value));
    }
  });
}

function resetCards() {
  if (typeof CLIPS === 'undefined') return;
  for (const clip of CLIPS) {
    const card = document.getElementById(`card-${clip.id}`);
    if (card) card.classList.remove('playing');
    const button = document.getElementById(`btn-fire-${clip.id}`);
    if (button) {
      button.disabled = false;
      button.innerHTML = '<span>🔊</span><span>电脑播报并联动全息</span>';
    }
    const fill = document.getElementById(`fill-${clip.id}`);
    if (fill) {
      fill.style.transition = 'none';
      fill.style.width = '0%';
    }
  }
}

function cancelAction(showMessage = false) {
  ++actionSerial;
  clearTimeout(actionTimer);
  if (systemSpeechId) {
    fetch('/api/pc_speech_stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: systemSpeechId })
    }).catch(() => {});
    systemSpeechId = null;
  }
  if (currentUtterance) {
    currentUtterance.onend = currentUtterance.onerror = null;
    currentUtterance = null;
  }
  if ('speechSynthesis' in window) {
    speechSynthesis.cancel();
  }
  resetCards();
  if (showMessage && actionLog) {
    actionLog.textContent = '⏹ 已停止电脑发声并取消待触发动作。';
  }
}

// 核心触发流程：电脑发声 -> 精准等待 200ms -> 手机全息触发动画
async function triggerClipAction(clipId, withVoice = true) {
  if (typeof CLIPS === 'undefined') return;
  const clip = CLIPS.find(item => item.id === clipId);
  if (!clip) return;

  cancelAction();
  const serial = actionSerial;
  const inputEl = document.getElementById(`voice-input-${clipId}`);
  const text = inputEl ? inputEl.value.trim() : clip.defaultVoice;
  const button = document.getElementById(`btn-fire-${clipId}`);
  const fill = document.getElementById(`fill-${clipId}`);
  const card = document.getElementById(`card-${clipId}`);

  if (card) card.classList.add('playing');
  if (button) button.disabled = true;

  function fail(message) {
    if (serial !== actionSerial) return;
    if (actionLog) actionLog.textContent = message;
    resetCards();
  }

  // 手机端全息动效联动广播
  async function broadcast() {
    if (serial !== actionSerial) return;
    if (button) button.innerHTML = '<span>✨</span><span>正在联动手机全息…</span>';
    try {
      const response = await fetch('/api/fuzz_trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip: clipId, voice: text, subtitle: text, delay_ms: 0 })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      if (!result.ok) throw new Error('中枢未接受动作');
      if (serial !== actionSerial) return;
      if (actionLog) actionLog.textContent = `✅ 已成功联动：${clip.title}！全息画面已同步切换。`;
      resetCards();
    } catch (error) {
      fail(`❌ 联动失败：${error.message}，请确保手机和电脑在同一 WiFi 局域网。`);
    }
  }

  // 语音播毕后的精准延迟倒计时
  function afterSpeech() {
    if (serial !== actionSerial) return;
    currentUtterance = null;
    const wait = Math.max(0, Number(delayMs) || 200);
    if (button) button.innerHTML = `<span>⏳</span><span>等待 ${wait}ms 触发全息…</span>`;
    if (fill) {
      fill.style.transition = `width ${wait}ms linear`;
      fill.style.width = '100%';
    }
    actionTimer = setTimeout(broadcast, wait);
  }

  // 静音联动
  if (!withVoice || !text) {
    broadcast();
    return;
  }

  // 首选：让电脑主机扬声器作为“嘴替”直接发声（调用 Windows 原生语音）
  systemSpeechId = `speech-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const curId = systemSpeechId;
  if (button) button.innerHTML = '<span>🎙️</span><span>电脑扬声器播报中…</span>';
  if (actionLog) actionLog.textContent = `🎙️ 电脑正在发声：「${text}」，播完即刻触发全息。`;

  try {
    const pcRes = await fetch('/api/pc_speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: curId, text: text, volume: voiceVol })
    });
    if (pcRes.ok) {
      const pcData = await pcRes.json();
      if (pcData.ok && pcData.finished) {
        systemSpeechId = null;
        afterSpeech();
        return;
      }
    }
  } catch (err) {
    console.warn('PC system speech unavailable, falling back to browser TTS:', err);
  }

  // 备用降级方案：浏览器本地 Web Speech 合成
  if ('speechSynthesis' in window) {
    if (button) button.innerHTML = '<span>🔊</span><span>浏览器语音播报中…</span>';
    const utterance = new SpeechSynthesisUtterance(text);
    currentUtterance = utterance;
    utterance.lang = 'zh-CN';
    utterance.rate = 1.05;
    utterance.volume = voiceVol;
    const voices = speechSynthesis.getVoices();
    const zhVoice = voices.find(v => /^zh/i.test(v.lang));
    if (zhVoice) utterance.voice = zhVoice;

    let finished = false;
    utterance.onend = () => {
      if (!finished) {
        finished = true;
        afterSpeech();
      }
    };
    utterance.onerror = (e) => {
      if (!finished) {
        finished = true;
        console.warn('Browser TTS error:', e);
        afterSpeech(); // 发生微小语音错误依然平滑推进动画，不阻塞用户
      }
    };
    speechSynthesis.speak(utterance);
    return;
  }

  // 若无可用语音环境，平滑过渡
  afterSpeech();
}

// 仅电脑发声试听（不触发手机端）
async function auditionSpeech(clipId) {
  if (typeof CLIPS === 'undefined') return;
  const clip = CLIPS.find(item => item.id === clipId);
  if (!clip) return;
  const inputEl = document.getElementById(`voice-input-${clipId}`);
  const text = inputEl ? inputEl.value.trim() : clip.defaultVoice;
  if (!text) return;

  if (actionLog) actionLog.textContent = `🔊 电脑试听：「${text}」`;
  fetch('/api/pc_speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: `audition-${Date.now()}`, text: text, volume: voiceVol })
  }).then(r => r.json()).then(data => {
    if (actionLog) actionLog.textContent = `🔊 试听完成！`;
  }).catch(() => {
    if ('speechSynthesis' in window) {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN';
      u.volume = voiceVol;
      speechSynthesis.speak(u);
    }
  });
}

window.addEventListener('pagehide', () => cancelAction());
