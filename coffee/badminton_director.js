'use strict';

/**
 * 透明桌面羽毛球互动 · 网页主控制台、摄像头控制中心、多网卡二维码中心与同步预监脚本
 */
(() => {
  const $ = id => document.getElementById(id);

  let state = null;
  let liveState = null;
  let playedAudioIds = new Set();
  let masterVol = 0.9;
  let audioBank = {};
  const isMobileCtrl = location.pathname.endsWith('/ctrl');

  function getServerHttpPort() {
    const port = Number(state?.http_port || location.port || 29765);
    return (!port || port === 8765 || port === 18765) ? 29765 : port;
  }

  // 24 种定制场景音效与音乐清单
  const SFX_CATALOG = [
    ['invite_chime', '🔔 收到打球邀请'],
    ['close_laptop', '💻 合上电脑'],
    ['push_desk', '🪑 吃力推桌子'],
    ['change_clothes', '👕 运动包换装'],
    ['grab_racket', '🏸 拿起球拍'],
    ['warmup_swing', '💨 热身挥拍'],
    ['machine_start', '⚙️ 发球机启动'],
    ['machine_charge', '🔋 发球机蓄力'],
    ['shuttle_launch', '🚀 羽毛球发射'],
    ['shuttle_fly', '🍃 羽毛球飞行'],
    ['hit_normal', '🎯 正常击球拍击'],
    ['hit_smash', '⚡ 强力扣杀拍击'],
    ['shuttle_fast', '☄️ 高速飞球破风'],
    ['shuttle_land', '🏀 羽毛球落地弹跳'],
    ['codex_step', '👟 小人跑步脚步'],
    ['codex_fall', '💥 扑空摔倒碰撞'],
    ['lose_sigh', '😮‍💨 输球失落叹气'],
    ['bgm_pity', '🎻 假装可怜委屈旋律'],
    ['cheat_button', '😈 掏遥控器启动作弊'],
    ['cheat_rapid', '🔥 作弊高速连发'],
    ['machine_jam', '⚠️ 机器卡顿失速故障'],
    ['giant_impact', '💣 超大羽毛球反噬拍扁'],
    ['splat_slide', '🫠 贴屏幕挤压缓慢滑落'],
    ['ending_awkward', '😅 尴尬把球拍藏身后'],
    ['smash_blast', '💥 扣杀爆裂减分'],
    ['codex_poke', '💢 戳小人烦躁']
  ];

  function playSfx(name, vol = 1.0) {
    if (!name || name === 'silence') return;
    const file = name.endsWith('.wav') ? name : `${name}.wav`;
    if (!audioBank[file]) {
      audioBank[file] = new Audio('/coffee/' + file);
    }
    const a = audioBank[file];
    a.volume = Math.max(0, Math.min(1, masterVol * vol));
    try {
      a.currentTime = 0;
      a.play().catch(() => {});
    } catch {}
  }

  function stopAllAudio() {
    Object.values(audioBank).forEach(a => {
      try { a.pause(); a.currentTime = 0; } catch {}
    });
  }

  // 初始化 24 个单独预听音效按钮
  const sfxWrap = $('sfxPreviewWrap');
  if (sfxWrap) {
    SFX_CATALOG.forEach(([key, label]) => {
      const btn = document.createElement('button');
      btn.className = 'sfx-chip';
      btn.textContent = label;
      btn.onclick = () => playSfx(key, 1.0);
      sfxWrap.appendChild(btn);
    });
  }

  async function apiPost(action, payload = {}) {
    try {
      const res = await fetch('/api/badminton/' + action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        const snap = await res.json();
        applyState(snap);
        return snap;
      }
    } catch {}
    return null;
  }

  async function livePost(action, payload = {}) {
    try {
      const res = await fetch('/api/badminton/live/' + action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.status === 403) {
        alert(`拉起或关闭电脑透明桌面进程需在电脑本机操作（请访问 http://127.0.0.1:${getServerHttpPort()}/badminton/director）；桌面已运行后，手机端可直接实时开打、切换球拍/五指、扣杀与开关摄像头。`);
        return null;
      }
      if (res.ok) {
        const snap = await res.json();
        applyLiveState(snap);
        return snap;
      }
    } catch {}
    return null;
  }

  function setPill(id, label, on) {
    const el = $(id);
    if (!el) return;
    el.textContent = label;
    el.classList.toggle('online', Boolean(on));
  }

  // =========================================================================
  // 1. S0 ~ S10 时间线渲染与状态同步
  // =========================================================================
  let timelineBuilt = false;
  function buildTimeline(scenes) {
    if (timelineBuilt || !scenes) return;
    timelineBuilt = true;
    const grid = $('timelineGrid');
    grid.innerHTML = '';
    scenes.forEach(sc => {
      const div = document.createElement('div');
      div.className = 'scene-node';
      div.id = 'node-' + sc.id;
      div.innerHTML = `<span class="s-id">${sc.id}</span><span class="s-name">${sc.title.split('｜')[1] || sc.title}</span>`;
      div.title = sc.desc;
      div.onclick = () => {
        stopAllAudio();
        apiPost('jump_scene', { scene_id: sc.id });
      };
      grid.appendChild(div);
    });
  }

  const POSE_LABELS = {
    work_type: '坐在工位敲键盘',
    invite_surprise: '抬头看镜头·惊喜起身',
    close_laptop: '合上笔记本电脑',
    push_strain_still: '用力推桌子(桌子沉重未动)',
    push_desk_move: '吃力把办公桌推向边缘',
    wipe_sweat_clap: '拍手擦额头汗水',
    take_bag: '拿出小运动包',
    spin_change: '跳跃旋转换上运动服',
    warmup_wobble: '挥拍试拍·用力过猛差点失衡',
    shy_ready: '不好意思地站稳准备接球',
    ready_wait: '持拍呼吸待命·眼神追球',
    move_anticipate: '压低重心预判来球',
    move_run: '快速移动脚步接球',
    hit_swing: '挥拍击球与收拍',
    wait_puzzled: '疑惑等待重新发球',
    panic_run: '慌乱飞奔救球',
    dive_fall: '扑空摔倒·球拍甩飞·坐地叹气',
    sit_pity: '缩着肩膀假装委屈',
    pity_peek: '偷偷抬起一只黑豆眼看你心软没',
    evil_remote: '坏笑掏出红灯小遥控器',
    cheat_laugh: '双手叉腰得意大笑(发球机连发)',
    slow_turn_to_holo: '笑声骤停·慢慢转头盯着失控机器',
    panic_freeze: '惊恐呆住来不及躲避',
    screen_pancake: '被超大羽毛球拍扁贴在电脑屏幕上滑落!',
    floor_press_stop: '狼狈趴地伸手按停遥控器',
    awkward_hide_racket: '爬起检查球拍·尴尬藏到身后'
  };

  let lastLanKey = '';

  function syncControlsFromState(next) {
    const p = next.params || {};
    const court = next.court || {};
    const active = document.activeElement;

    const setVal = (id, val) => {
      const el = $(id);
      if (el && val !== undefined && active !== el) el.value = val;
    };
    setVal('selSystemMode', next.system_mode);
    setVal('selVersionMode', next.compact_version ? 'compact' : 'full');
    setVal('selPreset', next.preset);

    const chkGuide = $('chkGuideLines');
    if (chkGuide && court.show_guide_lines !== undefined && active !== chkGuide) {
      chkGuide.checked = Boolean(court.show_guide_lines);
    }
    const btnEdit = $('btnToggleEdit');
    if (btnEdit) {
      const editing = Boolean(court.desktop_edit_mode);
      btnEdit.textContent = editing ? '🔒 锁定桌面球场（完成布局）' : '✏️ 桌面球场编辑';
    }
    if (p.master_volume !== undefined && active !== $('rngVolume')) {
      masterVol = Number(p.master_volume);
    }

    const sliderSpecs = [
      ['rngCharScale', 'valCharScale', p.char_scale, v => `${v.toFixed(2)}x`],
      ['rngShuttleSpeed', 'valShuttleSpeed', p.shuttle_speed, v => `${v.toFixed(2)}x`],
      ['rngArcHeight', 'valArcHeight', p.arc_height, v => `${v.toFixed(2)}x`],
      ['rngSmashSpeed', 'valSmashSpeed', p.smash_speed, v => `${v.toFixed(2)}x`],
      ['rngHitWindow', 'valHitWindow', p.hit_window_ms, v => `${Math.round(v)} ms`],
      ['rngCooldown', 'valCooldown', p.cooldown_ms, v => `${Math.round(v)} ms`],
      ['rngVolume', 'valVolume', p.master_volume, v => `${Math.round(v * 100)}%`],
      ['rngAudioOffset', 'valAudioOffset', p.audio_offset_ms, v => `${Math.round(v)} ms`]
    ];
    for (const [rngId, valId, rawVal, fmt] of sliderSpecs) {
      const rng = $(rngId);
      const valEl = $(valId);
      if (!rng || rawVal === undefined) continue;
      const num = Number(rawVal);
      if (active !== rng) rng.value = String(num);
      if (valEl) valEl.textContent = fmt(num);
    }
  }

  function applyState(next) {
    if (!next) return;
    const isFirstSnapshot = state === null;
    state = next;
    buildTimeline(next.scenes_catalog);

    // 首次接入只标记历史音效 ID 避免积压重播，后续实时增量播报
    for (const evt of next.audio_events || []) {
      if (evt.id && !playedAudioIds.has(evt.id)) {
        playedAudioIds.add(evt.id);
        if (!isFirstSnapshot && !liveState?.desktop_online) {
          if (evt.bgm === 'stop' || evt.bgm === 'pause') stopAllAudio();
          playSfx(evt.sound, evt.volume || 1.0);
        }
      }
    }

    if (!liveState?.desktop_online) {
      $('curScenePill').textContent = `当前节点：${next.scene_title}`;
      $('sceneDescText').textContent = `${next.scene_title}：${next.scene_desc}`;
      const poseKey = next.character?.pose || 'ready_wait';
      $('curPosePill').textContent = `角色状态：${POSE_LABELS[poseKey] || poseKey}`;
      $('rallyCounterText').textContent = `对打回合：${next.rally_count || 0} / 2`;
    }

    $('btnPauseResume').textContent = next.paused ? '▶ 继续剧情' : '⏸ 暂停剧情';

    document.querySelectorAll('.scene-node').forEach(el => {
      el.classList.toggle('current', el.id === 'node-' + next.scene_id);
    });

    syncControlsFromState(next);

    if (!liveState?.desktop_online) {
      const dev = next.devices || {};
      setPill('devDesktopPill', dev.desktop?.online ? `💻 透明桌面层：在线 (${dev.desktop.mode === 'edit' ? '编辑模式' : '穿透模式'})` : '💻 透明桌宠：待启动 (点击下方按钮启动)', dev.desktop?.online);
      setPill('devHoloPill', dev.holo?.online ? `🔮 全息手机 A：在线 (${dev.holo.rtt_ms || 12}ms)` : '🔮 全息手机 A：等待扫码连接', dev.holo?.online);
    }
    setPill('devCtrlPill', isMobileCtrl ? '📱 手机副控端 B：在线' : '💻 电脑网页控制台：在线', true);

    const curLanKey = `${(next.lan_ips || []).join(',')}|${next.preferred_ip || ''}|${getServerHttpPort()}`;
    if (next.lan_ips?.length && curLanKey !== lastLanKey) {
      lastLanKey = curLanKey;
      populateLanIps(next.lan_ips, next.preferred_ip);
    }

    if (next.system_shutdown) {
      $('curScenePill').textContent = '⏻ 已安全停止';
      $('sceneDescText').textContent = '✅ 本地桌面桌宠与后台同步服务已全部停止，您现在可以放心关闭此浏览器标签页。';
      setPill('devCtrlPill', '⏻ 服务已退出', false);
    }
  }

  // =========================================================================
  // 2. 新版透明桌宠与本机摄像头实时控制同步 (/api/badminton/live/*)
  // =========================================================================
  function syncLiveUI(v) {
    if (!v) return;
    const cam = v.camera || 'offline';
    const camIdx = Number(v.camera_index || 0);
    const online = Boolean(v.desktop_online);
    const enabled = Boolean(v.camera_enabled);
    const handMode = v.hand_mode === 'racket' ? 'racket' : 'hands';
    const isRacket = handMode === 'racket';
    const pScore = Number(v.player_score || 0);
    const cScore = v.codex_score ?? 5;
    const cMax = v.codex_max_score ?? 5;
    const pokeCnt = Number(v.poke_count || 0);

    const metaMap = {
      tracked: {
        label: isRacket ? '已切换球拍形态 (可挥拍/戳工位)' : '已锁定五指 · 21 个关节点',
        color: isRacket ? '#c084fc' : '#4ade80',
        pill: isRacket ? '📷 摄像头：球拍形态生效中' : '📷 摄像头：已识别五指(21点)',
        pillOn: true,
        banner: isRacket
          ? `🟣 本机摄像头 #${camIdx} 已切换「🏸 球拍形态」！对局中挥拍扣杀可触发爆裂减分；在工位时把球拍伸入 Codex 桌面区域还能戳烦他！`
          : `🟢 本机摄像头 #${camIdx} 已识别五指！21 个镜像关节点已叠加至桌面，快速挥拍或合掌扣杀可触发爆裂火花与 -1 扣分。`
      },
      looking: { label: '摄像头已开启 · 等待手入镜', color: '#38bdf8', pill: `📷 摄像头 #${camIdx}：已开启待入镜`, pillOn: true, banner: `📷 本机摄像头 #${camIdx} 正在采集！请在摄像头前举起一只手露出手腕与五指，可随时在控制台切为球拍形态。` },
      starting: { label: '正在连接本机摄像头…', color: '#facc15', pill: `📷 摄像头 #${camIdx}：连接中`, pillOn: false, banner: `⏳ 正在打开本机摄像头 #${camIdx} 并加载手势识别模型，请稍候 1~2 秒…` },
      paused: { label: '摄像头已关闭 (点击开启)', color: '#94a3b8', pill: '📷 摄像头：已关闭', pillOn: false, banner: '⏸ 本机摄像头当前处于关闭状态。点击绿色「▶ 开启摄像头」按钮即可立即开启。' },
      error: { label: v.camera_status || '摄像头未就绪', color: '#f87171', pill: '🔴 摄像头未就绪', pillOn: false, banner: `🔴 ${v.camera_status || '摄像头未就绪，可能被占用或未授权'}。可关闭占用软件后点「🔄 重连摄像头」，或点「🔀 切换镜头」尝试其它设备。` },
      offline: { label: '透明桌宠未启动 (点击开启)', color: '#facc15', pill: '📷 等待桌宠启动', pillOn: false, banner: '💻 透明桌面桌宠尚未运行。请在电脑双击启动脚本或点击「🚀 启动/唤醒透明桌宠」。' }
    };
    const meta = metaMap[cam] || metaMap.offline;

    if ($('liveScorePill')) {
      $('liveScorePill').textContent = `🏆 比分 你 ${pScore} : ${cScore} Codex`;
      $('liveScorePill').style.color = (v.angry || cScore <= 1) ? '#fca5a5' : '#fdba74';
    }
    if ($('mobileScoreText')) $('mobileScoreText').textContent = `你 ${pScore} : ${cScore}/${cMax} Codex`;
    if ($('handModePill')) {
      $('handModePill').textContent = isRacket ? '🏸 手部：球拍形态(可戳桌)' : '🖐 手部：五指21点';
      $('handModePill').classList.toggle('online', isRacket);
    }
    if ($('btnHandModeToggle')) $('btnHandModeToggle').textContent = isRacket ? '🏸 当前：球拍形态 (点此切五指)' : '🖐 手势形态：五指 21 点 (点此切球拍)';
    if ($('btnHandModeCam')) $('btnHandModeCam').textContent = isRacket ? '🖐 切回五指 21 点' : '🏸 切换球拍形态';
    if ($('btnMobHandMode')) $('btnMobHandMode').textContent = isRacket ? '🏸 当前：球拍形态' : '🖐 当前：五指21点';

    const pokeLabel = pokeCnt > 0 ? `👉 戳工位小人 (已戳 ${pokeCnt} 次)` : '👉 戳工位 Codex (烦躁反馈)';
    if ($('btnPokeCodex')) {
      $('btnPokeCodex').textContent = pokeLabel;
      $('btnPokeCodex').style.opacity = v.phase === 'desk' ? '1' : '0.55';
    }
    if ($('btnMobPoke')) {
      $('btnMobPoke').textContent = pokeCnt > 0 ? `👉 戳小人 (${pokeCnt})` : '👉 戳工位小人';
      $('btnMobPoke').style.opacity = v.phase === 'desk' ? '1' : '0.55';
    }
    if ($('mobileBubbleHint')) {
      if (v.codex_bubble) {
        $('mobileBubbleHint').textContent = `💬 Codex：「${v.codex_bubble}」`;
        $('mobileBubbleHint').style.color = (v.angry || v.annoyed) ? '#fda4af' : '#fde047';
      } else {
        $('mobileBubbleHint').textContent = v.phase === 'desk'
          ? '工位待机中：可切为「🏸 球拍形态」戳小人，或点击「🏸 开始开打」。'
          : `对打中（Codex 剩 ${cScore}/${cMax} 分）：全力扣杀触发爆裂 -1，扣光后连发七球！`;
        $('mobileBubbleHint').style.color = '#cbd5e1';
      }
    }

    if ($('teleHand')) {
      $('teleHand').textContent = meta.label;
      $('teleHand').style.color = meta.color;
    }
    if ($('camStatePill')) {
      $('camStatePill').textContent = meta.pill;
      $('camStatePill').classList.toggle('online', meta.pillOn);
    }
    if ($('camBanner')) {
      $('camBanner').textContent = meta.banner;
      $('camBanner').style.borderColor = meta.pillOn ? 'rgba(74,222,128,0.45)' : (cam === 'error' ? 'rgba(248,113,113,0.55)' : 'rgba(56,189,248,0.28)');
    }
    if ($('teleCamIdx')) $('teleCamIdx').textContent = `摄像头 #${camIdx}`;
    if ($('telePhone')) {
      $('telePhone').textContent = v.phone_online ? '🟢 全息发球端在线' : '○ 等待扫码连接';
      $('telePhone').style.color = v.phone_online ? '#4ade80' : '#facc15';
    }

    const canStop = online && enabled && cam !== 'paused' && cam !== 'error' && cam !== 'offline';
    const toggleText = canStop ? '⏸ 关闭摄像头' : '▶ 开启摄像头';
    [$('btnCamToggle'), $('btnCamQuickTop'), $('btnMobCam')].forEach(btn => {
      if (!btn) return;
      btn.textContent = btn.id === 'btnMobCam' ? (canStop ? '⏸ 关电脑摄像头' : '📷 开电脑摄像头') : toggleText;
      btn.classList.toggle('btn-green', !canStop);
    });
    if ($('btnCamSwitch')) $('btnCamSwitch').textContent = `🔀 切换镜头 (#${camIdx})`;
    if ($('btnCamPreview')) $('btnCamPreview').textContent = v.preview_open ? '🪞 关闭镜像预览' : '🪞 本机镜像预览';
    if ($('btnMobPreview')) $('btnMobPreview').textContent = v.preview_open ? '🪞 关镜像校准' : '🪞 电脑镜像校准';
    if ($('btnLaunchOverlay')) $('btnLaunchOverlay').textContent = online ? '🎛️ 展开桌面悬浮条' : '🚀 启动/唤醒透明桌宠';
    if ($('btnMobStart')) $('btnMobStart').textContent = v.phase === 'desk' ? '🏸 开始开打' : '🔄 局内已开打';

    if (online) {
      setPill('devDesktopPill', '💻 透明桌宠：运行中 (21点/球拍叠加)', true);
      setPill('devHoloPill', v.phone_online ? '🔮 全息手机 A：在线可发球' : '🔮 全息手机 A：等待扫码连接', v.phone_online);
      setPill('devCamPill', meta.pill, meta.pillOn);

      const phaseNames = {
        desk: v.annoyed ? '工位被戳烦躁中 💢' : '工位待机 (可举手 / 切球拍戳人)',
        clear: '推桌进场中…',
        rally: v.waiting ? '等待全息手机发球连接…' : `扣杀激战中 (Codex 剩 ${cScore} 分)`,
        charge: 'Codex 气急败坏开挂中…',
        barrage: '狂暴七球连发中！',
        quit: '扔拍回工位中…'
      };
      const phaseDescs = {
        desk: v.annoyed && v.codex_bubble
          ? `💢 Codex 被球拍戳烦了：「${v.codex_bubble}」（已戳 ${pokeCnt} 次），点击「开始开打」进入球局！`
          : 'Codex 坐在工位工作；可自由切换「🖐 五指 21 点 / 🏸 球拍形态」，把球拍伸进工位区可戳烦他，或点「开始开打」。',
        clear: 'Codex 正在合上电脑并推开办公桌，清出透明桌面球场…',
        rally: v.waiting
          ? '⏳ 电脑端已就绪，请用手机打开全息发球页 (/badminton/holo)，手机出球后电脑边缘立即接上！'
          : (v.codex_bubble ? `💥 ${v.codex_bubble}（全力挥拍触发爆裂火花，每记扣杀扣 Codex 1 分，当前剩 ${cScore}/${cMax} 分！）`
             : `🏸 对打进行中！来球亮圈时用力挥拍或点强力扣杀，爆裂击回 Codex 半场即可扣 1 分（当前剩 ${cScore}/${cMax} 分，扣光连发七球）！`),
        charge: '😈 分数被你扣光啦！Codex 气急败坏掏出遥控器开启作弊七连发！',
        barrage: '🔥 全息发球机连续发射 7 颗高速球！逐颗挥拍或扣杀打回！',
        quit: '😅 Codex 忙不过来扔拍认输了，正在把办公桌推回桌面边缘…'
      };
      $('curScenePill').textContent = `当前状态：${phaseNames[v.phase] || v.phase}`;
      $('sceneDescText').textContent = phaseDescs[v.phase] || '透明桌面羽毛球实机联动运行中';
      $('curPosePill').textContent = `本机识别：${meta.label}`;
      $('rallyCounterText').textContent = `比分 你 ${pScore} : ${cScore} Codex ｜ 累计 ${v.hits || 0} 拍`;

      const hwBadge = $('hitWindowBadge');
      const teleWin = $('teleWindow');
      if (v.can_swing) {
        if (hwBadge) { hwBadge.textContent = '🟠 接球圈已出现！快挥拍扣杀！'; hwBadge.style.color = '#fb923c'; }
        if (teleWin) { teleWin.textContent = '🟢 可击球 (快挥拍/扣杀)'; teleWin.style.color = '#4ade80'; }
      } else {
        if (hwBadge) { hwBadge.textContent = v.waiting ? '⏳ 等待全息手机发射…' : '等待来球进入接球圈'; hwBadge.style.color = '#94a3b8'; }
        if (teleWin) { teleWin.textContent = v.waiting ? '等待手机发球' : '等待来球'; teleWin.style.color = '#cbd5e1'; }
      }

      if ($('teleCooldown')) {
        $('teleCooldown').textContent = v.cooldown_active ? '⏳ 冷却防误触中' : '✅ 就绪';
        $('teleCooldown').style.color = v.cooldown_active ? '#facc15' : '#4ade80';
      }
      if ($('teleLastHit') && v.last_swing_at) {
        const secAgo = Math.max(0, (v.now || 0) - v.last_swing_at).toFixed(1);
        $('teleLastHit').textContent = `${secAgo} 秒前触发挥拍 (总 ${v.hits || 0} 拍)`;
      }
    } else {
      setPill('devCamPill', meta.pill, false);
    }
  }

  function applyLiveState(next) {
    if (!next || typeof next !== 'object') return;
    liveState = next;
    syncLiveUI(next);
  }

  if (isMobileCtrl && $('mobileCtrlBar')) {
    $('mobileCtrlBar').style.display = 'flex';
  }
  if (isMobileCtrl && $('camWizardHint')) {
    $('camWizardHint').textContent = '📱 当前为手机实时遥控端：可直接开打、强力扣杀、切换球拍/五指形态、戳小人及远程开关电脑摄像头！';
  }

  // 拉取初始状态 + SSE 双通道实时流
  fetch('/api/badminton/status').then(r => r.ok ? r.json() : null).then(applyState).catch(() => {});
  fetch('/api/badminton/live/status', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(applyLiveState).catch(() => {});

  function connectSSE() {
    const isEmbed = new URLSearchParams(location.search).get('embed') === '1' || window.self !== window.top;
    if (isEmbed && typeof BroadcastChannel !== 'undefined') {
      const bus = new BroadcastChannel('codex-holo-bus');
      bus.onmessage = e => {
        try {
          if (e.data?.badminton) applyState(e.data.badminton);
          if (e.data?.live) applyLiveState(e.data.live);
        } catch {}
      };
      return;
    }
    const syncEs = new EventSource('/api/sync/stream');
    syncEs.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.badminton) applyState(msg.badminton);
        if (msg.live) applyLiveState(msg.live);
      } catch {}
    };
    const closeEs = () => { try { syncEs.close(); } catch {} };
    window.addEventListener('pagehide', closeEs);
    window.addEventListener('beforeunload', closeEs);
  }
  connectSSE();

  setInterval(() => {
    apiPost('heartbeat', { role: 'ctrl' });
  }, 1500);
  setInterval(() => {
    fetch('/api/badminton/live/status', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(applyLiveState).catch(() => {});
  }, 1200);

  // =========================================================================
  // 3. 透明桌面主场景同步预监 & 模拟全息发球机绘制
  // =========================================================================
  const courtCanvas = $('courtPreviewCanvas');
  const courtCtx = courtCanvas.getContext('2d');
  const simHoloCanvas = $('simHoloCanvas');
  const simHoloCtx = simHoloCanvas.getContext('2d');

  function liveProject(x, z, h = 0) {
    const size = 1 / (1 + 1.30 * z);
    return [512 + x * 398 * size, 330 + 320 * (1 - z) * size - h * size, size];
  }

  function renderLivePreview(now) {
    const W = courtCanvas.width, H = courtCanvas.height;
    const sx = W / 1024, sy = H / 704;
    const v = liveState;
    const t = now / 1000;
    const gY = H * 0.84;

    if (v.clear_court > 0.02) {
      const [nlx, nly] = liveProject(-1.05, 0.5, 75);
      const [nrx, nry] = liveProject(1.05, 0.5, 75);
      const [blx, bly] = liveProject(-1.05, 0.5, 1);
      courtCtx.strokeStyle = `rgba(148, 230, 210, ${0.7 * v.clear_court})`;
      courtCtx.lineWidth = 2;
      courtCtx.beginPath();
      courtCtx.moveTo(nlx * sx, nly * sy);
      courtCtx.lineTo(nrx * sx, nry * sy);
      courtCtx.stroke();
      courtCtx.fillStyle = `rgba(21, 40, 56, ${0.35 * v.clear_court})`;
      courtCtx.fillRect(nlx * sx, nly * sy, (nrx - nlx) * sx, (bly - nly) * sy);
    }

    const isAnnoyed = Boolean(v.annoyed || (v.annoyed_until && v.annoyed_until > v.now));
    const isAngry = Boolean(v.angry || (v.angry_until && v.angry_until > v.now));
    const shakeX = isAnnoyed ? Math.sin(t * 48) * 3 : (isAngry ? Math.sin(t * 36) * 2 : 0);

    if (v.desk_offset < 0.99) {
      const dx = (855 + 249 * (v.desk_offset || 0)) * sx + shakeX;
      const dy = (596 - 32 * (v.desk_offset || 0)) * sy;
      courtCtx.fillStyle = '#774857';
      courtCtx.fillRect(dx - 32, dy - 18, 64, 8);
      courtCtx.fillStyle = '#563943';
      courtCtx.fillRect(dx - 28, dy - 10, 5, 16);
      courtCtx.fillRect(dx + 23, dy - 10, 5, 16);
      courtCtx.fillStyle = '#1e3740';
      courtCtx.fillRect(dx - 16, dy - 32, 24, 14);
      if (isAnnoyed) {
        courtCtx.fillStyle = '#ff4d6d';
        courtCtx.font = 'bold 14px sans-serif';
        courtCtx.fillText('💢', dx + 18, dy - 42);
      }
    }

    const actor = v.actor || [0, 0.78];
    const [ax, ay, sc] = liveProject(actor[0], actor[1], 0);
    const cx = ax * sx + shakeX, cy = ay * sy;
    courtCtx.save();
    courtCtx.translate(cx, cy + Math.sin(t * 7) * 1.5);
    courtCtx.fillStyle = 'rgba(0,0,0,0.45)';
    courtCtx.beginPath(); courtCtx.ellipse(0, 0, 14, 3.5, 0, 0, Math.PI * 2); courtCtx.fill();
    courtCtx.fillStyle = v.phase === 'desk' ? '#566f9b' : '#f8fafc';
    courtCtx.fillRect(-10, -28 * sc * 1.1, 20, 18 * sc * 1.1);
    courtCtx.fillStyle = '#392e48';
    courtCtx.fillRect(-11, -44 * sc * 1.1, 22, 16 * sc * 1.1);
    courtCtx.fillStyle = '#efb294';
    courtCtx.fillRect(-8, -38 * sc * 1.1, 16, 10 * sc * 1.1);
    if (isAngry || isAnnoyed) {
      courtCtx.fillStyle = '#ef4444';
      courtCtx.fillRect(-9, -40 * sc * 1.1, 18, 3);
      courtCtx.font = 'bold 13px sans-serif';
      courtCtx.fillText('💢', 12, -46 * sc * 1.1);
    }
    courtCtx.fillStyle = isAngry ? '#fca5a5' : '#ffdc38';
    courtCtx.font = 'bold 10px monospace';
    courtCtx.fillText('codex', -14, -48 * sc * 1.1);
    courtCtx.restore();

    for (const b of v.shots || []) {
      const p = Math.min(1, Math.max(0, (v.now - b.at) / b.flight));
      const x = b.start[0] + (b.end[0] - b.start[0]) * p;
      const z = b.start[1] + (b.end[1] - b.start[1]) * p;
      const h = b.start[2] + (b.end[2] - b.start[2]) * p + 4 * b.lift * p * (1 - p);
      const [bx, by, bs] = liveProject(x, z, h);
      const [gx, gy] = liveProject(x, z, 0);
      const isHot = Boolean(b.hot || (b.power || 0) >= 0.62);
      courtCtx.fillStyle = 'rgba(0,0,0,0.3)';
      courtCtx.beginPath(); courtCtx.ellipse(gx * sx, Math.min(gY, gy * sy), 7 * bs, 2.5, 0, 0, Math.PI * 2); courtCtx.fill();
      if (isHot) {
        const tp = Math.max(0, p - 0.14);
        const tx = b.start[0] + (b.end[0] - b.start[0]) * tp;
        const tz = b.start[1] + (b.end[1] - b.start[1]) * tp;
        const th = b.start[2] + (b.end[2] - b.start[2]) * tp + 4 * b.lift * tp * (1 - tp);
        const [tbx, tby] = liveProject(tx, tz, th);
        courtCtx.strokeStyle = 'rgba(255, 110, 32, 0.85)';
        courtCtx.lineWidth = Math.max(3, 7 * bs);
        courtCtx.beginPath(); courtCtx.moveTo(tbx * sx, tby * sy); courtCtx.lineTo(bx * sx, by * sy); courtCtx.stroke();
      }
      courtCtx.fillStyle = isHot ? '#ff5400' : '#fde047';
      courtCtx.beginPath(); courtCtx.arc(bx * sx, by * sy, Math.max(4, (isHot ? 8.5 : 7) * bs), 0, Math.PI * 2); courtCtx.fill();
      if (b.towards === 'player' && (v.now - b.at) / b.flight >= 0.66) {
        courtCtx.strokeStyle = '#fb923c';
        courtCtx.lineWidth = 2.5;
        courtCtx.beginPath(); courtCtx.arc(bx * sx, by * sy, 16 + Math.sin(t * 14) * 3, 0, Math.PI * 2); courtCtx.stroke();
      }
    }

    // 绘制扣杀爆裂火花、-1 飘字和戳人火花特效
    for (const ef of v.effects || []) {
      const [at, pos, kind] = ef;
      const age = Math.max(0, v.now - at);
      if (kind === 'blast' || kind === 'smash') {
        const [ex, ey] = liveProject(pos[0], pos[1], pos[2] || 40);
        const p = Math.min(1, age / (kind === 'blast' ? 0.9 : 0.6));
        const r = (kind === 'blast' ? 38 : 24) * p + 6;
        courtCtx.strokeStyle = `rgba(255, 140, 40, ${1 - p})`;
        courtCtx.lineWidth = 2.2;
        for (let i = 0; i < 10; i++) {
          const ang = (Math.PI * 2 * i) / 10;
          courtCtx.beginPath();
          courtCtx.moveTo(ex * sx + Math.cos(ang) * r * 0.3, ey * sy + Math.sin(ang) * r * 0.3);
          courtCtx.lineTo(ex * sx + Math.cos(ang) * r, ey * sy + Math.sin(ang) * r);
          courtCtx.stroke();
        }
      } else if (kind === 'score_drop') {
        const [ex, ey] = liveProject(pos[0], pos[1], pos[2] || 80);
        const p = Math.min(1, age / 1.15);
        courtCtx.fillStyle = `rgba(248, 113, 113, ${1 - p * 0.85})`;
        courtCtx.font = 'bold 16px sans-serif';
        courtCtx.fillText('-1', ex * sx - 8, ey * sy - p * 26);
      } else if (kind === 'poke') {
        const p = Math.min(1, age / 0.7);
        const r = 8 + 22 * p;
        courtCtx.strokeStyle = `rgba(251, 113, 133, ${1 - p})`;
        courtCtx.lineWidth = 2;
        courtCtx.beginPath(); courtCtx.arc(pos[0] * sx, pos[1] * sy, r, 0, Math.PI * 2); courtCtx.stroke();
      }
    }

    // 预监左上角实时比分牌 + Codex 台词气泡
    courtCtx.fillStyle = 'rgba(15, 23, 42, 0.78)';
    courtCtx.fillRect(8, 8, 138, 24);
    courtCtx.strokeStyle = isAngry ? '#f87171' : '#38bdf8';
    courtCtx.lineWidth = 1;
    courtCtx.strokeRect(8, 8, 138, 24);
    courtCtx.fillStyle = '#fde047';
    courtCtx.font = 'bold 11.5px sans-serif';
    courtCtx.fillText(`你 ${v.player_score || 0} : ${v.codex_score ?? 5} Codex`, 16, 24);
    if (v.codex_bubble && v.codex_bubble_until > v.now) {
      courtCtx.fillStyle = 'rgba(127, 29, 29, 0.88)';
      courtCtx.fillRect(Math.max(10, cx - 72), Math.max(36, cy - 82), 144, 22);
      courtCtx.fillStyle = '#fff1f2';
      courtCtx.font = 'bold 10.5px sans-serif';
      courtCtx.fillText(v.codex_bubble.slice(0, 14), Math.max(14, cx - 66), Math.max(51, cy - 67));
    }

    simHoloCtx.fillStyle = '#000000';
    simHoloCtx.fillRect(0, 0, 240, 180);
    const isCheat = v.phase === 'charge' || v.phase === 'barrage';
    simHoloCtx.save();
    simHoloCtx.translate(125, 132);
    simHoloCtx.fillStyle = '#334155';
    simHoloCtx.fillRect(-28, -4, 56, 12);
    simHoloCtx.fillStyle = !v.phone_online ? '#f59e0b' : (isCheat ? '#ef4444' : '#4ade80');
    simHoloCtx.fillRect(-18, 0, 8, 5);
    simHoloCtx.strokeStyle = '#38bdf8';
    simHoloCtx.strokeRect(-6, -68, 18, 34);
    const leftCount = Math.max(1, 5 - ((v.launches || []).length % 5));
    for (let i = 0; i < leftCount; i++) {
      simHoloCtx.fillStyle = '#ffffff';
      simHoloCtx.fillRect(-3, -40 - i * 6, 12, 4);
    }
    simHoloCtx.rotate(((isCheat ? 23 : (v.pending ? 21 : 16)) * Math.PI) / 180);
    simHoloCtx.fillStyle = '#64748b';
    simHoloCtx.fillRect(-36, -34, 50, 18);
    simHoloCtx.fillStyle = isCheat ? '#ef4444' : '#38bdf8';
    simHoloCtx.fillRect(-40, -36, 5, 22);
    simHoloCtx.restore();
  }

  function renderCourtPreview(now) {
    const W = courtCanvas.width, H = courtCanvas.height;
    courtCtx.fillStyle = '#0b1324';
    courtCtx.fillRect(0, 0, W, H);
    courtCtx.strokeStyle = 'rgba(148, 163, 184, 0.06)';
    for (let x = 0; x < W; x += 26) {
      courtCtx.beginPath(); courtCtx.moveTo(x, 0); courtCtx.lineTo(x, H); courtCtx.stroke();
    }
    for (let y = 0; y < H; y += 26) {
      courtCtx.beginPath(); courtCtx.moveTo(0, y); courtCtx.lineTo(W, y); courtCtx.stroke();
    }

    if (liveState?.desktop_online) {
      renderLivePreview(now);
      return;
    }

    if (!state) return;
    const t = now / 1000;
    const court = state.court || {};
    const char = state.character || {};
    const props = state.props || {};
    const groundY = H * (court.ground_y_ratio || 0.82);
    const charX = W * (char.x || 0.68);
    const humanX = W * (court.human_zone_x_ratio || 0.24);
    const humanY = H * (court.human_zone_y_ratio || 0.56);

    if (state.scene_id !== 'S0') {
      courtCtx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
      courtCtx.lineWidth = 1.5;
      courtCtx.beginPath();
      courtCtx.moveTo(W * 0.1, groundY);
      courtCtx.lineTo(W * 0.92, groundY);
      courtCtx.stroke();

      const netX = W * 0.46;
      courtCtx.strokeStyle = '#94a3b8';
      courtCtx.lineWidth = 2;
      courtCtx.beginPath();
      courtCtx.moveTo(netX, groundY);
      courtCtx.lineTo(netX, groundY - 38);
      courtCtx.stroke();
    }

    const hwOpen = state.hit_window?.open;
    courtCtx.strokeStyle = hwOpen ? '#4ade80' : 'rgba(56, 189, 248, 0.4)';
    courtCtx.lineWidth = hwOpen ? 3 : 1.5;
    courtCtx.beginPath();
    courtCtx.arc(humanX, humanY, hwOpen ? 28 + Math.sin(t * 18) * 4 : 22, 0, Math.PI * 2);
    courtCtx.stroke();
    courtCtx.fillStyle = hwOpen ? '#4ade80' : '#38bdf8';
    courtCtx.font = 'bold 11px sans-serif';
    courtCtx.fillText(hwOpen ? '👋 快挥拍击球!' : '真人接球区(点击可挥拍)', humanX - 42, humanY + 36);

    if (props.desk_visible || props.desk_stored) {
      const dx = props.desk_stored ? (W - 42) : (W * (props.desk_x || 0.66));
      courtCtx.fillStyle = '#774857';
      courtCtx.fillRect(dx - 28, groundY - 26, 56, 8);
      courtCtx.fillStyle = '#563943';
      courtCtx.fillRect(dx - 24, groundY - 18, 5, 18);
      courtCtx.fillRect(dx + 19, groundY - 18, 5, 18);
      if (props.laptop_open) {
        courtCtx.fillStyle = '#1e3740';
        courtCtx.fillRect(dx - 16, groundY - 46, 30, 20);
      }
    }

    const pose = char.pose || 'ready_wait';
    const isSport = char.outfit === 'sport';
    courtCtx.save();
    if (pose === 'screen_pancake') {
      const sp = char.screen_splat_progress || 0;
      const slideY = Math.max(0, (sp - 0.45) * 65);
      courtCtx.translate(charX, groundY - 55 + slideY);
      courtCtx.scale(1.65, 1.35);
      courtCtx.fillStyle = 'rgba(224, 242, 254, 0.35)';
      courtCtx.beginPath(); courtCtx.arc(0, 0, 28, 0, Math.PI * 2); courtCtx.fill();
      courtCtx.fillStyle = '#38bdf8';
      courtCtx.fillRect(-20, -6, 40, 20);
      courtCtx.fillStyle = '#392e48';
      courtCtx.fillRect(-18, -24, 36, 18);
      courtCtx.fillStyle = '#efb294';
      courtCtx.fillRect(-14, -21, 28, 15);
      courtCtx.fillStyle = '#f472b6';
      courtCtx.fillRect(-4, -14, 8, 5);
      courtCtx.fillStyle = '#fde047';
      courtCtx.font = 'bold 10px monospace';
      courtCtx.fillText('SPLAT!', -18, -28);
    } else {
      const bob = (pose === 'dive_fall' || pose === 'floor_press_stop') ? 14 : Math.sin(t * 8) * 2;
      courtCtx.translate(charX, groundY + bob);
      courtCtx.fillStyle = 'rgba(0,0,0,0.45)';
      courtCtx.beginPath(); courtCtx.ellipse(0, 0, 18, 4, 0, 0, Math.PI * 2); courtCtx.fill();
      courtCtx.fillStyle = isSport ? '#1e3a8a' : '#363751';
      courtCtx.fillRect(-10, -14, 8, 14);
      courtCtx.fillRect(2, -14, 8, 14);
      courtCtx.fillStyle = isSport ? '#f8fafc' : '#566f9b';
      courtCtx.fillRect(-13, -38, 26, 24);
      if (isSport) {
        courtCtx.fillStyle = '#0284c7';
        courtCtx.fillRect(-13, -38, 26, 6);
        courtCtx.fillStyle = '#ef4444';
        courtCtx.fillRect(-10, -28, 20, 3);
      }
      courtCtx.fillStyle = '#392e48';
      courtCtx.fillRect(-14, -60, 28, 22);
      courtCtx.fillStyle = '#63506b';
      courtCtx.fillRect(-12, -58, 24, 9);
      courtCtx.fillStyle = '#d99a88';
      courtCtx.fillRect(-6, -59, 12, 3);
      courtCtx.fillStyle = '#efb294';
      courtCtx.fillRect(-11, -52, 22, 14);
      if (isSport) {
        courtCtx.fillStyle = '#ef4444';
        courtCtx.fillRect(-14, -55, 28, 3);
      }
      courtCtx.fillStyle = '#09090d';
      courtCtx.fillRect(-7, -47, 4, 4);
      courtCtx.fillRect(3, -47, 4, 4);
      courtCtx.fillStyle = '#ffffff';
      courtCtx.fillRect(-7, -47, 1.5, 1.5);
      courtCtx.fillRect(3, -47, 1.5, 1.5);
      courtCtx.fillStyle = '#ffdc38';
      courtCtx.font = 'bold 11px monospace';
      courtCtx.fillText('codex', -16, -66);
    }
    courtCtx.restore();

    for (const s of state.shuttles || []) {
      const sx = W * s.x;
      const sy = H * s.y;
      const r = s.kind === 'giant_boss' ? 18 : 6;
      courtCtx.fillStyle = 'rgba(0,0,0,0.35)';
      courtCtx.beginPath(); courtCtx.ellipse(sx, groundY, r * 1.1, 3, 0, 0, Math.PI * 2); courtCtx.fill();
      courtCtx.save();
      courtCtx.translate(sx, sy);
      courtCtx.rotate(s.angle || 0);
      courtCtx.fillStyle = '#ffffff';
      courtCtx.beginPath();
      courtCtx.moveTo(0, 0);
      courtCtx.lineTo(-r * 2.2, -r * 1.1);
      courtCtx.lineTo(-r * 2.2, r * 1.1);
      courtCtx.closePath();
      courtCtx.fill();
      courtCtx.fillStyle = s.kind === 'giant_boss' ? '#ef4444' : '#fde047';
      courtCtx.beginPath();
      courtCtx.arc(2, 0, r * 0.75, 0, Math.PI * 2);
      courtCtx.fill();
      courtCtx.restore();
    }

    simHoloCtx.fillStyle = '#000000';
    simHoloCtx.fillRect(0, 0, 240, 180);
    const holo = state.hologram || {};
    const isCheat = holo.mode === 'cheat_red' || holo.red_led;
    const isJam = holo.mode === 'jammed';
    const vx = isJam ? Math.sin(now * 0.08) * 3 : 0;
    simHoloCtx.save();
    simHoloCtx.translate(125 + vx, 132);
    simHoloCtx.fillStyle = '#334155';
    simHoloCtx.fillRect(-28, -4, 56, 12);
    simHoloCtx.fillStyle = isCheat ? '#ef4444' : '#4ade80';
    simHoloCtx.fillRect(-18, 0, 8, 5);
    simHoloCtx.strokeStyle = '#38bdf8';
    simHoloCtx.strokeRect(-6, -68, 18, 34);
    for (let i = 0; i < (holo.shuttles_left || 4); i++) {
      simHoloCtx.fillStyle = '#ffffff';
      simHoloCtx.fillRect(-3, -40 - i * 6, 12, 4);
    }
    simHoloCtx.rotate(((holo.barrel_angle || 18) * Math.PI) / 180);
    simHoloCtx.fillStyle = '#64748b';
    simHoloCtx.fillRect(-36, -34, 50, 18);
    simHoloCtx.fillStyle = isCheat ? '#ef4444' : '#38bdf8';
    simHoloCtx.fillRect(-40, -36, 5, 22);
    simHoloCtx.restore();
  }

  // =========================================================================
  // 4. 多网卡局域网选择与标准可扫二维码绘制
  // =========================================================================
  function drawVisualQrCode(canvasEl, urlText) {
    if (!canvasEl || !urlText) return;
    const g = canvasEl.getContext('2d');
    const w = canvasEl.width;
    const h = canvasEl.height;

    g.fillStyle = '#ffffff';
    g.fillRect(0, 0, w, h);
    g.fillStyle = '#64748b';
    g.font = '11px sans-serif';
    g.textAlign = 'center';
    g.fillText('生成二维码中...', w / 2, h / 2);

    canvasEl.dataset.qrTarget = urlText;
    const img = new Image();
    img.onload = () => {
      if (canvasEl.dataset.qrTarget !== urlText) return;
      g.fillStyle = '#ffffff';
      g.fillRect(0, 0, w, h);
      g.drawImage(img, 0, 0, w, h);
    };
    img.onerror = () => {
      if (canvasEl.dataset.qrTarget !== urlText) return;
      g.fillStyle = '#ffffff';
      g.fillRect(0, 0, w, h);
      g.fillStyle = '#ef4444';
      g.font = '11px sans-serif';
      g.textAlign = 'center';
      g.fillText('二维码加载失败', w / 2, h / 2 - 6);
      g.fillStyle = '#334155';
      g.fillText('请直接复制下方网址', w / 2, h / 2 + 12);
    };
    img.src = `/api/qrcode?text=${encodeURIComponent(urlText)}&size=${w}&_=${Date.now()}`;
  }

  function updateDeviceUrls(ip) {
    const cleanIp = (ip || '127.0.0.1').trim();
    const port = getServerHttpPort();
    const holoUrl = `http://${cleanIp}:${port}/badminton/holo`;
    const ctrlUrl = `http://${cleanIp}:${port}/badminton/ctrl`;
    $('urlHoloText').textContent = holoUrl;
    $('urlCtrlText').textContent = ctrlUrl;
    $('linkHoloOpen').href = holoUrl;
    $('linkCtrlOpen').href = ctrlUrl;
    drawVisualQrCode($('qrHoloCanvas'), holoUrl);
    drawVisualQrCode($('qrCtrlCanvas'), ctrlUrl);
  }

  function populateLanIps(ips, preferred) {
    const sel = $('selLanIp');
    if (!sel) return;
    sel.innerHTML = '';
    ips.forEach((ip, idx) => {
      const opt = document.createElement('option');
      opt.value = ip;
      opt.textContent = idx === 0 ? `${ip} (推荐局域网主 Wi-Fi)` : ip;
      if (ip === preferred) opt.selected = true;
      sel.appendChild(opt);
    });
    updateDeviceUrls(preferred || ips[0]);
  }

  // =========================================================================
  // 5. 按钮、摄像头控制与参数滑块事件绑定
  // =========================================================================
  async function handleToggleCamera() {
    if (!liveState?.desktop_online) {
      await livePost('launch_overlay', { camera_enabled: true });
      return;
    }
    const cam = liveState.camera || 'offline';
    const shouldEnable = (!liveState.camera_enabled || cam === 'paused' || cam === 'error' || cam === 'offline');
    await livePost('camera_power', { enabled: shouldEnable });
  }

  if ($('btnCamToggle')) $('btnCamToggle').onclick = handleToggleCamera;
  if ($('btnCamQuickTop')) $('btnCamQuickTop').onclick = handleToggleCamera;

  if ($('btnCamRetry')) {
    $('btnCamRetry').onclick = async () => {
      if (!liveState?.desktop_online) {
        await livePost('launch_overlay', { camera_enabled: true });
        return;
      }
      await livePost('camera_retry', {});
    };
  }
  if ($('btnCamSwitch')) {
    $('btnCamSwitch').onclick = async () => {
      if (!liveState?.desktop_online) {
        await livePost('launch_overlay', { camera_enabled: true, camera_index: ((liveState?.camera_index || 0) + 1) % 3 });
        return;
      }
      await livePost('camera_switch', {});
    };
  }
  if ($('btnCamPreview')) {
    $('btnCamPreview').onclick = async () => {
      if (!liveState?.desktop_online) {
        await livePost('launch_overlay', { camera_enabled: true });
        return;
      }
      await livePost('camera_preview', { open: !liveState.preview_open });
    };
  }
  const showOverlayOrBar = async () => {
    await livePost('launch_overlay', {});
  };
  if ($('btnLaunchOverlay')) $('btnLaunchOverlay').onclick = showOverlayOrBar;
  if ($('btnShowBarTop')) $('btnShowBarTop').onclick = showOverlayOrBar;

  $('btnStartPlay').onclick = async () => {
    if (liveState?.desktop_online) {
      if (liveState.phase === 'desk') {
        await livePost('start', {});
      } else {
        await livePost('replay', {});
      }
    } else {
      await livePost('launch_overlay', { camera_enabled: true });
      apiPost('start_play', {});
    }
  };

  const triggerSwingAction = () => {
    if (liveState?.desktop_online) {
      livePost('swing', { x: 0.5, y: 0.5, power: 0.88, assisted: true, force_smash: true });
    } else {
      apiPost('manual_swing', { power: 42 });
    }
  };
  $('btnManualSwing').onclick = triggerSwingAction;

  async function toggleHandMode() {
    const nextMode = liveState?.hand_mode === 'racket' ? 'hands' : 'racket';
    await livePost('hand_mode', { mode: nextMode });
  }
  async function pokeCodexAction() {
    if (liveState?.desktop_online) {
      if (liveState.phase !== 'desk') {
        $('sceneDescText').textContent = '💡 只有在工位待机时才能在桌子旁戳 Codex 哦，点「🏠 收拍回工位」即可回工位！';
        return;
      }
      await livePost('poke', { x: 855, y: 520 });
    }
  }
  if ($('btnHandModeToggle')) $('btnHandModeToggle').onclick = toggleHandMode;
  if ($('btnHandModeCam')) $('btnHandModeCam').onclick = toggleHandMode;
  if ($('btnMobHandMode')) $('btnMobHandMode').onclick = toggleHandMode;
  if ($('btnPokeCodex')) $('btnPokeCodex').onclick = pokeCodexAction;
  if ($('btnMobPoke')) $('btnMobPoke').onclick = pokeCodexAction;

  if ($('btnMobStart')) {
    $('btnMobStart').onclick = () => $('btnStartPlay')?.click();
  }
  if ($('btnMobSmash')) {
    $('btnMobSmash').onclick = triggerSwingAction;
  }
  if ($('btnMobBarrage')) {
    $('btnMobBarrage').onclick = () => $('btnManualServe')?.click();
  }
  if ($('btnMobQuit')) {
    $('btnMobQuit').onclick = () => $('btnReturnDaily')?.click();
  }
  if ($('btnMobCam')) {
    $('btnMobCam').onclick = handleToggleCamera;
  }
  if ($('btnMobPreview')) {
    $('btnMobPreview').onclick = () => $('btnCamPreview')?.click();
  }

  $('btnManualServe').onclick = () => {
    if (liveState?.desktop_online) {
      if (liveState.phase === 'rally') {
        livePost('barrage', {});
      } else if (liveState.phase === 'desk') {
        livePost('start', {});
      }
    } else {
      apiPost('manual_serve', { fast: false });
    }
  };

  $('btnPauseResume').onclick = () => apiPost('set_paused', { paused: !state?.paused });
  $('btnReplayScene').onclick = () => {
    stopAllAudio();
    if (liveState?.desktop_online) {
      livePost('replay', {});
    }
    apiPost('replay_scene', {});
  };
  $('btnPrevScene').onclick = () => { stopAllAudio(); apiPost('prev_scene', {}); };
  $('btnNextScene').onclick = () => { stopAllAudio(); apiPost('next_scene', {}); };
  $('btnReturnDaily').onclick = () => {
    stopAllAudio();
    livePost('quit', {});
    apiPost('jump_scene', { scene_id: 'S0' });
  };
  if ($('btnResetAllBm')) {
    $('btnResetAllBm').onclick = () => {
      stopAllAudio();
      fetch('/api/pet/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope: 'all' }),
      }).catch(() => {});
    };
  }
  const switchPetSuite = target => {
    fetch('/api/pet/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: target, spawn: true }),
    }).then(() => {
      if (window.top === window.self) location.href = '/';
    }).catch(() => {});
  };
  if ($('btnSwitchCoffee')) $('btnSwitchCoffee').onclick = () => switchPetSuite('coffee');
  if ($('btnSwitchStrike')) $('btnSwitchStrike').onclick = () => switchPetSuite('strike');

  function closeDesktopOverlay() {
    livePost('close', {});
    apiPost('close_desktop', {}).then(snap => {
      if (snap) {
        $('sceneDescText').textContent = '✅ 已关闭电脑透明桌面图层；后台服务与当前控制台保持开启，可随时点击「🚀 启动/唤醒透明桌宠」恢复。';
      }
    });
  }

  function shutdownEntireSystem() {
    if (!confirm('确认退出透明桌面桌宠并停止本地后台同步服务？\n退出后如需再次体验，重新双击 0-一键启动 bat 即可。')) return;
    stopAllAudio();
    fetch('/api/system/shutdown', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    }).then(() => {
      $('curScenePill').textContent = '⏻ 已安全停止';
      $('sceneDescText').textContent = '✅ 本地桌面桌宠与后台同步服务已全部停止，您现在可以放心关闭此浏览器标签页。';
      setPill('devCtrlPill', '⏻ 服务已退出', false);
      setPill('devDesktopPill', '💻 透明桌宠：已退出', false);
      try { window.close(); } catch {}
    }).catch(() => {});
  }

  if ($('btnCloseDesktop')) $('btnCloseDesktop').onclick = closeDesktopOverlay;
  if ($('btnCloseDesktopTop')) $('btnCloseDesktopTop').onclick = closeDesktopOverlay;
  if ($('btnShutdownSystem')) $('btnShutdownSystem').onclick = shutdownEntireSystem;
  if ($('btnShutdownTop')) $('btnShutdownTop').onclick = shutdownEntireSystem;
  $('btnToggleEdit').onclick = () => {
    const cur = Boolean(state?.court?.desktop_edit_mode);
    apiPost('update_params', { court: { desktop_edit_mode: !cur } });
  };

  $('selSystemMode').onchange = e => apiPost('update_params', { system_mode: e.target.value });
  $('selVersionMode').onchange = e => apiPost('update_params', { compact_version: e.target.value === 'compact' });
  $('chkGuideLines').onchange = e => apiPost('update_params', { court: { show_guide_lines: e.target.checked } });

  $('selLanIp').onchange = e => {
    updateDeviceUrls(e.target.value);
    apiPost('update_params', { preferred_ip: e.target.value });
    fetch('/coffee/lan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ip: e.target.value }) }).catch(() => {});
  };
  $('btnApplyIp').onclick = () => {
    const custom = $('inpCustomIp').value.trim();
    if (custom) {
      updateDeviceUrls(custom);
      apiPost('update_params', { preferred_ip: custom });
      fetch('/coffee/lan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ip: custom }) }).catch(() => {});
    }
  };
  $('btnRefreshLan').onclick = () => {
    lastLanKey = '';
    apiPost('refresh_lan', {});
    fetch('/coffee/lan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh: true }) })
      .then(r => r.ok ? r.json() : null)
      .then(lan => { if (lan?.ips?.length) populateLanIps(lan.ips, lan.ip); })
      .catch(() => {});
  };
  $('btnTestHolo').onclick = () => apiPost('manual_serve', { fast: false });
  $('btnTestPing').onclick = () => {
    const t0 = performance.now();
    apiPost('heartbeat', { role: 'ctrl' }).then(() => {
      alert(`通信测试成功！电脑权威中枢响应延迟：${(performance.now() - t0).toFixed(1)} ms`);
    });
  };

  // 参数滑块实时绑定
  const bindSlider = (rngId, valId, paramKey, fmt) => {
    const rng = $(rngId);
    const valEl = $(valId);
    if (!rng) return;
    rng.addEventListener('input', e => {
      const v = Number(e.target.value);
      if (valEl) valEl.textContent = fmt(v);
      if (paramKey === 'master_volume') masterVol = v;
      apiPost('update_params', { params: { [paramKey]: v } });
    });
  };
  bindSlider('rngCharScale', 'valCharScale', 'char_scale', v => `${v.toFixed(2)}x`);
  bindSlider('rngShuttleSpeed', 'valShuttleSpeed', 'shuttle_speed', v => `${v.toFixed(2)}x`);
  bindSlider('rngArcHeight', 'valArcHeight', 'arc_height', v => `${v.toFixed(2)}x`);
  bindSlider('rngSmashSpeed', 'valSmashSpeed', 'smash_speed', v => `${v.toFixed(2)}x`);
  bindSlider('rngHitWindow', 'valHitWindow', 'hit_window_ms', v => `${v} ms`);
  bindSlider('rngCooldown', 'valCooldown', 'cooldown_ms', v => `${v} ms`);
  bindSlider('rngVolume', 'valVolume', 'master_volume', v => `${Math.round(v * 100)}%`);
  bindSlider('rngAudioOffset', 'valAudioOffset', 'audio_offset_ms', v => `${v} ms`);

  $('selPreset').onchange = e => apiPost('update_params', { preset: e.target.value });
  $('btnResetParams').onclick = () => {
    $('selPreset').value = 'daily';
    apiPost('update_params', { preset: 'daily' });
  };

  window.addEventListener('keydown', e => {
    if (e.code === 'Space' && document.activeElement?.tagName !== 'INPUT') {
      e.preventDefault();
      triggerSwingAction();
    }
  });
  courtCanvas.addEventListener('click', triggerSwingAction);

  function mainLoop(now) {
    renderCourtPreview(now);
    requestAnimationFrame(mainLoop);
  }
  requestAnimationFrame(mainLoop);
})();
