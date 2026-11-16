'use strict';

/**
 * 3D 全息端「电子打工仔挖土罢工 & 全息木桶泡澡」渲染控制器 (StrikeHoloController v5.0)
 * 严格遵循：
 * 1. 100% 沿用经典 Codex 地中海微秃、两侧卷发、呆萌大黑豆圆眼、微胖短躯干像素原型；
 * 2. 打工仔变装：歪戴黄色安全帽（露出地中海两侧卷发与圆耳）、橙黄工装背带裤、手持铁铲；
 * 3. 严禁任何机械进度条/加载条，所有状态通过姿态、动作节奏、残影、汗水、十字青筋与微表情呈现；
 * 4. 900ms 跨端半身匀速接力、300ms 停打即停铲喘气、挖土随机彩蛋（旧球鞋/易拉罐/小金币）；
 * 5. 愤怒 5 阶段演化：插铲看双手颤抖 -> 黑豆眼圆睁/倒竖眉/红脸颊/十字青筋发抖 -> 深蹲抱泥蓄力 -> 4.5倍景深迎面甩泥 -> 浑身泥污叉腰跺脚；
 * 6. 全息木桶泡澡（PG 合规）：推入木桶浴缸、高出边缘的彩色肥皂泡沫、漂浮晃悠的黄色橡皮小鸭子、仅露头肩享受眯眼、过烫变红龙虾哇呀乱叫跳出水面！
 */
class StrikeHoloController {
  constructor(onState) {
    this.state = null;
    this.offset = 0;
    this.lastContact = null;
    this.lastSigh = null;
    this.lastThrow = null;
    this.lastBathEnter = null;
    this.lastHotJump = null;
    this.lastDiscovery = null;
    this.sounds = null;
    this.clockGeneration = 0;
    this.connectSSE(onState);
    setInterval(() => {
      if (this.events?.readyState === EventSource.OPEN) this.calibrate();
    }, 25000);
  }

  connectSSE(onState) {
    if (this.events) {
      try { this.events.close(); } catch {}
    }
    const events = new EventSource('/api/strike/stream');
    this.events = events;
    events.onopen = () => this.calibrate();
    events.onmessage = ({ data }) => {
      try {
        const next = JSON.parse(data).data;
        if (!next || (this.state?.epoch === next.epoch && next.seq < this.state.seq)) return;
        if (this.state?.epoch !== next.epoch) {
          this.lastContact = null;
          this.offset = next.now_ms - this.wall();
          this.calibrate();
        }
        this.state = next;
        onState?.(next);
      } catch {}
    };
    events.onerror = () => {
      // 自动重连兜底轮询
      setTimeout(() => {
        fetch('/api/strike/status', { cache: 'no-store' })
          .then(r => r.json())
          .then(snap => {
            if (snap) {
              this.state = snap;
              onState?.(snap);
            }
          })
          .catch(() => {});
      }, 600);
    };
  }

  wall() {
    return performance.timeOrigin + performance.now();
  }

  async calibrate() {
    const generation = ++this.clockGeneration;
    let best = Infinity;
    for (let i = 0; i < 3; i++) {
      const start = this.wall();
      try {
        const reply = await fetch('/api/strike/clock', { cache: 'no-store' });
        const { now } = await reply.json();
        const elapsed = this.wall() - start;
        if (generation !== this.clockGeneration) return;
        if (elapsed < best) {
          this.offset = now - start - elapsed / 2;
          best = elapsed;
        }
      } catch {
        return;
      }
    }
  }

  unlock() {
    if (this.sounds) return;
    const makeAudio = (file, vol) => {
      const a = new Audio('/coffee/' + file);
      a.volume = vol;
      return a;
    };
    this.sounds = {
      dig: makeAudio('dig_dirt.wav', 0.25),
      sigh: makeAudio('relax_sigh.wav', 0.38),
      throw: makeAudio('mud_throw.wav', 0.55),
      splat: makeAudio('mud_splat.wav', 0.60),
      slide: makeAudio('pour_slide.wav', 0.45),
      hot: makeAudio('hot_jump.wav', 0.50),
      coin: makeAudio('coin_unearth.wav', 0.40),
      sparkle: makeAudio('clean_sparkle.wav', 0.50),
    };
  }

  sound(name) {
    const audio = this.sounds?.[name];
    if (!audio) return;
    try {
      audio.currentTime = 0;
      audio.play().catch(() => {});
    } catch {}
  }

  render(ctx) {
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, 220, 160);
    let state = this.state;
    if (!state || ['OFFICE_IDLE', 'OFFICE_WORK', 'SCRUBBING', 'CLEAN_DONE'].includes(state.state)) {
      return;
    }

    const now = this.wall() + this.offset;
    if (state.state === 'THROWING' && state.mud && now >= state.mud.impact_time_ms) {
      state = { ...state, state: 'STRIKE', since: state.mud.impact_time_ms };
    }

    const t = Math.max(0, (now - state.since) / 1000);
    const scale = state.config?.HOLO_SCALE || 1.24;
    const side = state.config?.HOLO_ENTRY_SIDE || -1;

    ctx.save();
    ctx.translate(110, 123);
    ctx.scale(scale * -side, scale);
    ctx.translate(-110, -123);

    // =========================================================================
    // 浴缸入场与全息木桶泡澡分支 (BATH_ENTER / BATH_SOAK)
    // =========================================================================
    if (state.state === 'BATH_ENTER' || state.state === 'BATH_SOAK') {
      const bath = state.bath || {};
      const enterStart = bath.enter_start_ms || state.since;
      const enterEnd = bath.enter_end_ms || (enterStart + 800);
      const enterP = state.state === 'BATH_ENTER' ? smooth((now - enterStart) / Math.max(1, enterEnd - enterStart)) : 1.0;

      if (state.state === 'BATH_ENTER' && this.lastBathEnter !== enterStart) {
        this.lastBathEnter = enterStart;
        this.sound('slide');
      }
      if (bath.hot_jump && this.lastHotJump !== state.epoch + ':hot') {
        this.lastHotJump = state.epoch + ':hot';
        this.sound('hot');
      } else if (!bath.hot_jump) {
        this.lastHotJump = null;
      }

      renderHologramBath(ctx, state, bath, enterP, now / 1000);
      ctx.restore();
      return;
    }

    // =========================================================================
    // 跨端走位转场与挖土/愤怒/甩泥/跺脚分支
    // =========================================================================
    const cross = state.cross;
    const returning = state.state === 'RETURNING' || state.state === 'BATH_RETURN';

    if (state.state !== 'LEAVING' || now > (cross?.end || Infinity) - 90) {
      let reveal = state.state === 'LEAVING' ? unit((now - cross.end + 90) / 300) : 1;
      if (returning && cross) reveal = 1 - unit((now - cross.start) / Math.max(1, cross.end - cross.start));
      ground(ctx, reveal, state.contacts || 0);
    }

    if (returning && cross) {
      if (now < cross.end) {
        const seam = 1 - unit((now - cross.start) / Math.max(1, cross.end - cross.start));
        const fromGround = 1 - smooth((now - state.since) / Math.max(1, cross.start - state.since));
        const x = 25 - 16 + 32 * seam + 63 * fromGround;
        ctx.save();
        ctx.beginPath();
        ctx.rect(25, 0, 195, 160);
        ctx.clip();
        ctx.translate(Math.round(x), 0);
        ctx.scale(-1, 1);
        worker(ctx, 0, 122, walkPose((now - cross.start) / 1000), now / 1000, false, false, false, 0);
        ctx.restore();
      }
      ctx.restore();
      return;
    }

    if (state.state === 'LEAVING' && cross) {
      if (now >= cross.arrive) {
        worker(ctx, 104, 122, breathPose((now - cross.arrive) / 1000, false), now / 1000, false, false, false, 0);
      } else if (now >= cross.start) {
        // 跨端半身拼接：从左侧虚空边界 (x=25) 同步迈出（先露铁铲尖与歪戴安全帽，逐步走出全身）
        const p = unit((now - cross.start) / Math.max(1, cross.end - cross.start));
        const q = unit((now - cross.end) / Math.max(1, cross.arrive - cross.end));
        const x = 25 - 16 + 32 * p + (104 - 41) * smooth(q);
        ctx.save();
        // 虚空传送微光门框
        ctx.fillStyle = `rgba(255, 200, 110, ${0.28 * (1 - q)})`;
        ctx.fillRect(24, 58, 2, 66);
        ctx.beginPath();
        ctx.rect(25, 0, 195, 160);
        ctx.clip();
        worker(ctx, x, 122, walkPose((now - cross.start) / 1000), now / 1000, false, false, false, 0);
        ctx.restore();
      }
      ctx.restore();
      return;
    }

    let pose = REST_POSE.slice();
    let x = 104;
    let parked = false;
    let angryStage = 0;
    const { dig_phase, dig_rate, stop_dig_at } = state;
    const phase = dig_phase + Math.max(0, Math.min(now, stop_dig_at) - state.now_ms) * dig_rate / 1000;
    const isDigging = ['WORKING', 'TIRED'].includes(state.state) && now < stop_dig_at;
    const tired = state.fatigue >= (state.config?.TIRED_THRESHOLD || 32);
    const fastBlur = isDigging && (state.energy >= 4.5 || dig_rate >= 2.6);
    const stroke = Math.floor(phase);
    const p = phase - stroke;

    // 检查是否正在触发挖土随机彩蛋（愣神低头看一眼 -> 一脚踢开）
    const found = state.discovery;
    const foundAgeMs = found ? (now - found.at) : Infinity;

    if (found && foundAgeMs >= 0 && foundAgeMs < 1350 && ['WORKING', 'TIRED', 'RESTING'].includes(state.state)) {
      if (this.lastDiscovery !== found.serial) {
        this.lastDiscovery = found.serial;
        this.sound('coin');
      }
      pose = discoveryPose(foundAgeMs / 1000);
    } else if (isDigging) {
      pose = digPose(p, tired, stroke);
      const contact = state.epoch + ':' + stroke;
      if (p >= 0.48 && p < 0.73 && this.lastContact !== contact) {
        this.lastContact = contact;
        this.sound('dig');
      }
    } else if (['RESTING', 'WORKING', 'TIRED'].includes(state.state)) {
      // 停打超过 300ms 立即停铲，双手扶木柄，身体前倾大口喘气，胸口剧烈起伏
      const rest = state.state === 'RESTING' ? t : Math.max(0, now - stop_dig_at) / 1000;
      pose = mixPose(digPose(p, tired, stroke), breathPose(rest, tired), smooth(rest / 0.14));
      if (rest > 0.10) {
        breath(ctx, 118, 76 + (tired ? 3 : 0), (rest * 0.9) % 1.0);
        if (this.lastSigh !== stop_dig_at) {
          this.lastSigh = stop_dig_at;
          this.sound('sigh');
        }
      }
    } else if (state.state === 'ANGRY') {
      const lookMs = (state.config?.LOOK_AT_HANDS_MS || 1100) / 1000;
      angryStage = (state.angry_stage === 2 || t >= lookMs) ? 2 : 1;
      pose = angryPose(t, lookMs, state.fatigue / (state.config?.STRIKE_THRESHOLD || 100));
      parked = t >= 0.18;
    } else if (state.state === 'THROWING') {
      angryStage = 3;
      pose = throwPose(now, state.mud, state.since);
      parked = true;
      if (state.mud && now >= state.mud.launch_time_ms) {
        angryStage = 4;
        if (this.lastThrow !== state.mud.serial) {
          this.lastThrow = state.mud.serial;
          this.sound('throw');
        }
        x -= 8 * smooth((now - state.mud.launch_time_ms + 60) / 160);
      }
    } else if (state.state === 'STRIKE') {
      angryStage = 5;
      pose = strikePose(t);
      parked = true;
      x -= 8;
      // 气急败坏原地跺脚溅起泥点
      const stompPhase = (t * 2.2) % 1.0;
      for (const beat of [0.26, 0.72]) {
        if (stompPhase >= beat && stompPhase < beat + 0.25) {
          dust(ctx, x + 6, 122, (stompPhase - beat) / 0.25, 8, Math.floor(t * 5));
        }
      }
    }

    const strikeDirty = state.state === 'STRIKE' || (state.mud && now >= state.mud.launch_time_ms + 120);

    // 若把铁铲插在地上（怀疑人生 / 怒火中烧 / 甩泥 / 罢工跺脚）
    if (parked) {
      shovel(ctx, 136, 98, 1.26, false, 0);
    }

    // 绘制打工仔小人（含高速挥铲像素残影、看双手颤抖、圆睁黑豆眼、红脸颊、十字青筋、抱大泥团、全身污泥）
    worker(ctx, x, 122, pose, now / 1000, strikeDirty, parked, fastBlur, angryStage, state.mud, now);

    // 挥铲扬起泥块粒子（高速快打时泥块密集飞起）
    const dustProgress = isDigging ? (p - 0.46) / 0.52 : (p - 0.46 + t * 1.1) / 0.52;
    if ((isDigging || (state.state === 'RESTING' && t < 0.34)) && dustProgress >= 0 && dustProgress < 1) {
      const particleCount = fastBlur ? 18 : (tired ? 8 : 11);
      dust(ctx, 144, 119, dustProgress, particleCount, stroke);
    }

    // 绘制挖出的随机彩蛋（破烂旧球鞋 / 压扁易拉罐 / 小金币）
    if (found && foundAgeMs >= 0 && foundAgeMs < 1350) {
      treasure(ctx, found.kind, unit(foundAgeMs / 1350));
    }

    // 阶段 4：向用户镜头迎面暴怒甩泥（伴随 4.5 倍景深逐帧放大与呼啸破风线！）
    if (state.mud) {
      flyingMudZoom(ctx, state.mud, now);
    }

    ctx.restore();
  }
}

const unit = p => Math.max(0, Math.min(1, p));
const smooth = p => unit(p) ** 2 * (3 - 2 * unit(p));
const lerp = (a, b, p) => a + (b - a) * p;
const pick = (seed, i) => {
  const n = Math.sin((seed + 1) * 91.61 + i * 17.17) * 41283.81;
  return n - Math.floor(n);
};

// 严格对齐 coffee_pet.py 与 pixel.js 的经典 Codex 地中海小人配色 + 安全帽背带裤配色
const PAL = {
  outline: '#211c2c',
  hair: '#392e48',       // 经典地中海两侧卷发深紫棕
  hairLight: '#63506b',  // 卷发高光
  baldSpot: '#d99a88',   // 地中海微秃发旋肤色
  skin: '#efb294',
  cheek: '#bc786f',
  rageRed: '#ef4444',    // 怒火中烧双颊通红与青筋红
  amber: '#ffbe55',
  hat: '#f59e0b',        // 略微歪戴的亮黄色安全帽
  hatLight: '#fde047',
  hatShade: '#b45309',
  darkOrange: '#c2410c',
  orange: '#ea580c',     // 工装背带裤深橙
  vest: '#fb923c',       // 橙黄色工装背带裤主体
  hiVis: '#fef08a',      // 工装背带与胸前口袋亮黄高光
  shirtBlue: '#566f9b',  // 原版 Codex 蓝色内衬上衣
  navy: '#3e537b',       // 原版深蓝裤腿打底
  boot: '#55415a',
  steel: '#9babaf',
  soilDark: '#382016',
  soil: '#714327',
  soilRidge: '#ad7442',
  soilLight: '#d6a268',
};

function rect(ctx, c, x, y, w, h) {
  ctx.fillStyle = c;
  ctx.fillRect(Math.round(x), Math.round(y), Math.max(1, Math.round(w)), Math.max(1, Math.round(h)));
}

function poly(ctx, c, points) {
  ctx.fillStyle = c;
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(Math.round(x), Math.round(y)) : ctx.moveTo(Math.round(x), Math.round(y))));
  ctx.closePath();
  ctx.fill();
}

function limb(ctx, color, width, points) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = 'square';
  ctx.lineJoin = 'bevel';
  ctx.beginPath();
  points.forEach(([x, y], i) => (i ? ctx.lineTo(Math.round(x), Math.round(y)) : ctx.moveTo(Math.round(x), Math.round(y))));
  ctx.stroke();
}

// [crouch, lean, head pitch, back foot x/y, front foot x/y, grip x/y, shaft angle, free hand x/y, face]
const REST_POSE = [0, 1, 0, -9, 0, 9, 0, 19, -31, 1.05, -9, -20, 1];
const DIG = [
  [0, [1, 1, 1, -11, 0, 10, 0, 8, -31, -0.62, 2, -27, 1]],
  [0.22, [-3, -2, 0, -12, 0, 10, 0, 7, -45, -0.55, 3, -36, 1]],
  [0.37, [0, 5, 3, -11, 0, 12, 0, 16, -37, 0.38, 12, -29, 1]],
  [0.48, [7, 9, 8, -10, 0, 12, 0, 21, -19, 0.75, 15, -24, 1]],
  [0.60, [7, 6, 6, -10, 0, 12, 0, 22, -20, 0.65, 15, -24, 1]],
  [0.77, [1, -2, 1, -11, 0, 11, 0, 15, -35, -0.56, 9, -29, 1]],
  [1, [1, 1, 1, -11, 0, 10, 0, 8, -31, -0.62, 2, -27, 1]],
];

function mixPose(a, b, p) {
  return a.map((v, i) => lerp(v, b[i], p));
}

function keyPose(keys, t) {
  const i = keys.findIndex(([at]) => at >= t);
  if (i < 0) return keys[keys.length - 1][1].slice();
  if (i === 0) return keys[0][1].slice();
  const [start, from] = keys[i - 1], [end, to] = keys[i];
  return mixPose(from, to, smooth((t - start) / Math.max(0.0001, end - start)));
}

function walkPose(t) {
  const cycle = Math.sin(t * 20);
  const lift = Math.cos(t * 20);
  return [
    Math.abs(cycle) * -2, 2, 0,
    -5 - cycle * 11, Math.min(0, -lift * 7),
    5 + cycle * 11, Math.min(0, lift * 7),
    11 + cycle * 7, -21, -1.84,
    -9 - cycle * 7, -19, 1,
  ];
}

function digPose(p, tired, stroke) {
  const pose = keyPose(DIG, p);
  if (tired) {
    pose[0] += 3;
    pose[2] += 2;
    if (stroke % 4 === 3 && p < 0.30) {
      const wipe = Math.sin((p / 0.3) * Math.PI);
      pose[10] = lerp(pose[10], -44, wipe);
      pose[9] = lerp(pose[9], 7, wipe);
    }
  }
  return pose;
}

function discoveryPose(t) {
  // 0..0.65s: 愣神低头看一眼彩蛋；0.65..1.25s: 抬起右脚随手踢到旁边
  if (t < 0.65) {
    return [3, 6, 9, -10, 0, 10, 0, 14, -28, 0.95, 8, -24, 1];
  }
  const kickP = Math.sin(unit((t - 0.65) / 0.45) * Math.PI);
  return [
    1, 2 - kickP * 4, 4,
    -11, 0,
    10 + kickP * 18, -kickP * 10,
    12, -30, 0.85, 6, -25, 1,
  ];
}

function breathPose(t, tired) {
  // 双手扶着木柄，身体前倾大口喘气，胸口剧烈起伏
  const heave = Math.sin(t * (tired ? 9.5 : 7.0));
  const p = REST_POSE.slice();
  p[0] += (tired ? 5 : 3.5) + 2.8 * heave; // 胸口与躯干明显起伏
  p[1] += 4.5 + 1.2 * heave;               // 身体前倾扶铲
  p[2] += 6 + 2.0 * heave;                 // 低头大口喘气
  p[7] = 17;                               // 右手扶铲柄顶端
  p[8] = -28 + heave * 1.5;
  p[9] = 1.22;                             // 铲子竖直支撑地面
  p[10] = 13;                              // 左手也扶在木柄上
  p[11] = -25 + heave * 1.5;
  return p;
}

function angryPose(t, lookSec, intensity) {
  if (t < lookSec) {
    // 阶段 1（怀疑人生）：铁铲插地，呆立原地，举起两只肉乎乎的小手翻来覆去地看，双手微微颤抖
    const flip = Math.sin(t * 10.0);
    const tremor = Math.sin(t * 48.0) * 1.2;
    return [
      1, 1, 5,
      -10, 0, 10, 0,
      11 + flip * 3 + tremor, -30 + tremor * 0.5, 1.25,
      5 - flip * 3 - tremor, -31 - tremor * 0.5,
      0.35,
    ];
  }
  // 阶段 2（怒火中烧）：正面转向镜头，黑豆眼圆睁，眼角倒竖，双颊通红，头顶冒出红色十字青筋，浑身发抖
  const tremble = Math.sin(t * 55.0) * (1.8 + intensity * 1.5);
  return [
    2 + Math.abs(Math.sin(t * 14)) * 1.5,
    tremble,
    -1,
    -11, 0, 11, 0,
    14 + tremble, -25, 1.25,
    -14 + tremble, -25,
    0.0, // 正面直视用户镜头 (face = 0)
  ];
}

function throwPose(now, mud, since) {
  if (!mud || now < mud.launch_time_ms) {
    // 阶段 3（蓄力大招）：恶狠狠深蹲，双手抱起一大团超大湿泥巴
    const p = mud ? unit((now - since) / Math.max(1, mud.launch_time_ms - since)) : 0.5;
    return keyPose([
      [0.0, [2, 0, 0, -11, 0, 11, 0, 12, -26, 1.25, -12, -26, 0]],
      [0.45, [9, 6, 6, -13, 0, 13, 0, 8, -16, 1.25, -8, -16, 0]],
      [0.85, [10, 4, 4, -14, 0, 14, 0, 6, -18, 1.25, -6, -18, 0]],
      [1.0, [-3, -4, -3, -15, 0, 15, -3, 10, -38, 1.25, -10, -38, 0]],
    ], p);
  }
  // 阶段 4（脱手甩出瞬间）
  const after = (now - mud.launch_time_ms) / 1000;
  return keyPose([
    [0.0, [-3, -4, -3, -15, 0, 15, -3, 14, -36, 1.25, -14, -36, 0]],
    [0.18, [4, -5, 2, -13, 0, 13, 0, 15, -24, 1.25, -15, -24, 0]],
    [0.52, [2, 0, 0, -11, 0, 11, 0, 12, -22, 1.25, -12, -22, 0]],
  ], after);
}

function strikePose(t) {
  // 阶段 5（全身泥污双手叉腰原地跺脚跳脚）
  const cycle = (t * 2.2) % 1.0;
  let leftFootY = 0;
  let rightFootY = 0;
  let bodyBounce = Math.sin(t * 14) * 1.2;
  if (cycle < 0.35) {
    rightFootY = -Math.sin((cycle / 0.35) * Math.PI) * 11;
    bodyBounce -= 2;
  } else if (cycle >= 0.50 && cycle < 0.85) {
    leftFootY = -Math.sin(((cycle - 0.50) / 0.35) * Math.PI) * 11;
    bodyBounce -= 2;
  }
  // 双手叉腰 (gx=12, gy=-22, hx=-12, hy=-22)，正面气呼呼瞪眼 (face=0)
  return [
    2 + bodyBounce,
    Math.sin(t * 11) * 1.8,
    -1,
    -11, leftFootY,
    11, rightFootY,
    12, -22, 1.25,
    -12, -22,
    0.0,
  ];
}

function ground(ctx, reveal, contacts) {
  ctx.save();
  ctx.globalAlpha = reveal;
  poly(ctx, '#21150f', [
    [45, 123], [65, 116], [89, 115], [118, 113], [150, 113], [168, 118],
    [178, 122], [171, 130], [144, 136], [96, 137], [66, 134], [46, 129],
  ]);
  poly(ctx, PAL.soilDark, [
    [52, 123], [76, 118], [104, 119], [127, 114], [155, 115], [173, 123],
    [165, 128], [140, 132], [88, 133], [60, 130],
  ]);
  poly(ctx, '#92582e', [
    [119, 122], [125, 116], [135, 116], [141, 110], [150, 110],
    [157, 114], [163, 116], [171, 121], [163, 125], [137, 126],
  ]);
  poly(ctx, '#b47840', [
    [130, 117], [141, 111], [150, 110], [157, 115], [149, 115], [142, 118],
  ]);
  poly(ctx, '#4a2719', [
    [119, 123], [132, 120], [147, 121], [157, 125], [148, 128], [127, 127],
  ]);
  const mound = Math.min(10, contacts) * 1.25;
  if (mound > 0) {
    poly(ctx, '#7a4c30', [
      [67, 128], [73, 125], [80, 127 - mound], [87, 128 - mound],
      [93, 124], [100, 129], [89, 132], [75, 132],
    ]);
    poly(ctx, '#a06c3d', [
      [73, 126], [80, 127 - mound], [87, 128 - mound], [91, 126], [85, 124], [78, 127],
    ]);
  }
  for (let i = 0; i < 30; i++) {
    const x = 57 + pick(11, i) * 108, y = 121 + pick(5, i) * 9;
    rect(ctx, [PAL.soil, '#583620', '#986138'][i % 3], x, y, i % 4 + 1, 1);
  }
  ctx.restore();
}

function shovel(ctx, gx, gy, angle, motionBlur = false, clock = 0) {
  // 高速快打 (>5 键/秒) 时，铲头带像素残影 (afterimage)
  if (motionBlur) {
    for (let ghost = 2; ghost >= 1; ghost--) {
      ctx.save();
      ctx.globalAlpha = ghost === 1 ? 0.38 : 0.18;
      ctx.translate(Math.round(gx), Math.round(gy));
      ctx.rotate(angle - ghost * 0.24);
      rect(ctx, '#fde047', -8, -2, 26, 3);
      poly(ctx, '#bae6fd', [[18, -4], [24, -6], [33, -3], [33, 3], [24, 6], [18, 4]]);
      ctx.restore();
    }
  }
  ctx.save();
  ctx.translate(Math.round(gx), Math.round(gy));
  ctx.rotate(angle);
  rect(ctx, PAL.outline, -10, -3, 32, 6);
  rect(ctx, '#a87951', -9, -1, 29, 2);
  rect(ctx, '#ebba73', -9, -1, 25, 1);
  poly(ctx, '#333646', [[18, -4], [23, -6], [29, -6], [34, -3], [34, 3], [29, 6], [23, 6], [18, 4]]);
  poly(ctx, PAL.steel, [[21, -3], [25, -5], [29, -5], [33, -2], [33, 2], [29, 4], [24, 4], [21, 2]]);
  rect(ctx, '#dce5dc', 25, -4, 5, 1);
  poly(ctx, '#775034', [[27, 4], [32, 0], [34, 2], [30, 5]]);
  ctx.restore();
}

function drawRedCrossVein(ctx, x, y, clock) {
  // 阶段 2（怒火中烧）：头顶跳动的红色十字青筋 💢
  const pulse = Math.floor(clock * 10) % 2;
  const s = pulse ? 1 : 0;
  ctx.save();
  ctx.translate(Math.round(x), Math.round(y - s));
  rect(ctx, '#111118', -6, -6, 13, 13);
  // 四个愤怒直角折线构成经典像素十字青筋 💢
  rect(ctx, '#ef4444', -5, -5, 4, 2);
  rect(ctx, '#ef4444', -5, -5, 2, 4);
  rect(ctx, '#ef4444', 2, -5, 4, 2);
  rect(ctx, '#ef4444', 4, -5, 2, 4);
  rect(ctx, '#ef4444', -5, 4, 4, 2);
  rect(ctx, '#ef4444', -5, 2, 2, 4);
  rect(ctx, '#ef4444', 2, 4, 4, 2);
  rect(ctx, '#ef4444', 4, 2, 2, 4);
  rect(ctx, '#fecaca', -1, -1, 3, 3);
  ctx.restore();
}

function worker(ctx, x, y, pose, clock, dirty = false, parked = false, fastBlur = false, angryStage = 0, mud = null, now = 0) {
  const [drop, lean, pitch, ax, ay, bx, by, gx, gy, angle, hx, hy, face] = pose;
  ctx.save();
  ctx.translate(Math.round(x), Math.round(y));

  // 脚底阴影
  rect(ctx, '#1d1312', -18, 0, 36, 3);
  const mid = lean * 0.48;

  // 1. 双腿与工装靴（微胖短腿，蓝色裤底 + 工装背带裤腿）
  limb(ctx, PAL.outline, 11, [[mid - 6, -19 + drop], [ax, ay - 5]]);
  limb(ctx, PAL.navy, 7, [[mid - 6, -18 + drop], [ax, ay - 7]]);
  limb(ctx, PAL.outline, 11, [[mid + 7, -19 + drop], [bx, by - 5]]);
  limb(ctx, '#566f9b', 7, [[mid + 7, -18 + drop], [bx, by - 7]]);
  for (const [fx, fy] of [[ax, ay], [bx, by]]) {
    rect(ctx, PAL.outline, fx - 6, fy - 6, 14, 7);
    rect(ctx, PAL.boot, fx - 5, fy - 5, 12, 3);
    rect(ctx, '#825a58', fx + 1, fy - 4, 5, 2);
  }

  const shoulderY = -41 + drop;

  // 2. 后侧手臂（原版蓝色袖子）
  limb(ctx, PAL.outline, 9, [[lean - 9, shoulderY], [hx - 2, hy + 5], [hx, hy]]);
  limb(ctx, PAL.shirtBlue, 6, [[lean - 9, shoulderY], [hx - 2, hy + 5], [hx, hy]]);
  rect(ctx, PAL.skin, hx - 3, hy - 2, 6, 5);

  // 3. 微胖短躯干：原版蓝色内衬 + 橙黄色工装背带裤 (Overalls)
  poly(ctx, PAL.outline, [
    [lean - 13, shoulderY - 4], [lean + 10, shoulderY - 5], [lean + 15, shoulderY + 3],
    [mid + 13, -15 + drop], [mid - 12, -15 + drop], [lean - 15, shoulderY + 3],
  ]);
  // 蓝色内衬上衣肩部
  poly(ctx, PAL.shirtBlue, [
    [lean - 11, shoulderY - 3], [lean + 9, shoulderY - 3], [lean + 13, shoulderY + 5],
    [lean - 12, shoulderY + 5],
  ]);
  // 橙黄色工装背带裤主体（围胸肚兜 + 两条橙黄肩带 + 金色背带扣）
  poly(ctx, PAL.vest, [
    [lean - 9, shoulderY + 3], [lean + 8, shoulderY + 3],
    [mid + 11, -17 + drop], [mid - 10, -17 + drop],
  ]);
  // 左右两条背带裤肩带
  poly(ctx, PAL.orange, [
    [lean - 8, shoulderY - 3], [lean - 4, shoulderY - 3],
    [lean - 4, shoulderY + 6], [lean - 8, shoulderY + 6],
  ]);
  poly(ctx, PAL.orange, [
    [lean + 3, shoulderY - 3], [lean + 7, shoulderY - 3],
    [lean + 7, shoulderY + 6], [lean + 3, shoulderY + 6],
  ]);
  // 背带金属扣与胸前工装口袋
  rect(ctx, PAL.hiVis, lean - 7, shoulderY + 2, 2, 2);
  rect(ctx, PAL.hiVis, lean + 4, shoulderY + 2, 2, 2);
  rect(ctx, PAL.darkOrange, mid - 5, -31 + drop, 10, 7);
  rect(ctx, PAL.hiVis, mid - 4, -30 + drop, 8, 2);
  rect(ctx, '#6d413c', mid - 10, -20 + drop, 21, 2);

  // 4. 铁铲与前侧手臂
  if (!parked) {
    shovel(ctx, gx, gy, angle, fastBlur, clock);
  }
  limb(ctx, PAL.outline, 9, [[lean + 7, shoulderY + 3], [(gx + lean + 7) / 2 + 3, gy + 5], [gx, gy]]);
  limb(ctx, '#779abc', 6, [[lean + 7, shoulderY + 3], [(gx + lean + 7) / 2 + 3, gy + 5], [gx, gy]]);
  rect(ctx, PAL.skin, gx - 3, gy - 3, 7, 5);
  rect(ctx, '#ffe0ab', gx - 2, gy - 3, 3, 1);

  // 阶段 1（怀疑人生）：双手举在胸前翻来覆去地看，绘制肉乎乎颤抖的双手掌心/手背细节
  if (angryStage === 1) {
    const palmFlip = Math.sin(clock * 10) > 0;
    for (const [px, py] of [[hx, hy], [gx, gy]]) {
      rect(ctx, PAL.outline, px - 5, py - 5, 9, 8);
      rect(ctx, PAL.skin, px - 4, py - 4, 7, 6);
      if (palmFlip) {
        rect(ctx, '#d48c72', px - 2, py - 2, 3, 2); // 掌心纹路
      } else {
        rect(ctx, '#ffe0ab', px - 3, py - 4, 5, 2); // 手背指节
      }
    }
  }

  // 阶段 3（蓄力大招）：深蹲时双手在身前抱起一大团超大湿泥巴
  if (angryStage === 3 && mud && now < mud.launch_time_ms) {
    const windP = unit((now - mud.windup_start_ms) / Math.max(1, mud.launch_time_ms - mud.windup_start_ms));
    const mr = 8 + windP * 7;
    const mx = (gx + hx) / 2;
    const my = Math.min(gy, hy) - 2;
    poly(ctx, PAL.soilDark, [
      [mx - mr, my], [mx - mr * 0.7, my - mr * 0.8], [mx + mr * 0.7, my - mr * 0.85],
      [mx + mr, my], [mx + mr * 0.7, my + mr * 0.7], [mx - mr * 0.7, my + mr * 0.7],
    ]);
    poly(ctx, PAL.soil, [
      [mx - mr * 0.8, my - 1], [mx - mr * 0.5, my - mr * 0.65], [mx + mr * 0.5, my - mr * 0.65],
      [mx + mr * 0.8, my - 1], [mx + mr * 0.5, my + mr * 0.5], [mx - mr * 0.5, my + mr * 0.5],
    ]);
    rect(ctx, PAL.soilLight, mx - mr * 0.4, my - mr * 0.45, mr * 0.6, 2);
  }

  // 5. 头部与微表情（100% 经典 Codex 地中海两侧卷发 + 呆萌大黑豆圆眼 + 略微歪戴的黄色安全帽！）
  const h = -54 + drop + pitch * 0.47;
  ctx.save();
  ctx.translate(Math.round(lean + face * 2), Math.round(h));
  if (face < 0) ctx.scale(-1, 1);

  // 原版 Codex 标志性地中海两侧与后部深紫棕卷发（安全帽下明显露出两侧卷发蓬松轮廓！）
  poly(ctx, PAL.hair, [[-14, -9], [10, -9], [14, -4], [14, 8], [8, 13], [-8, 13], [-15, 6]]);
  rect(ctx, PAL.hairLight, -14, -4, 5, 7); // 左侧蓬松卷发团
  rect(ctx, PAL.hairLight, 10, -4, 4, 6);  // 右侧蓬松卷发团
  rect(ctx, PAL.baldSpot, -5, -10, 9, 3);  // 微微露出的地中海前额微秃发际

  // 圆润呆萌脸型与大耳朵
  poly(ctx, PAL.skin, [[-6, -3], [9, -4], [14, 0], [16, 5], [13, 10], [9, 12], [-5, 11], [-8, 5]]);
  rect(ctx, '#d99a88', -12, 1, 5, 6); // 圆耳朵

  const front = Math.abs(face) < 0.60;
  if (front) {
    // 正面视角（怀疑人生 / 怒火中烧 / 蓄力甩泥 / 罢工跺脚）
    if (angryStage >= 2) {
      // 【阶段 2~5 怒火中烧】：黑豆眼圆睁（外圈眼白衬托大黑豆眼珠）、眼角倒竖、双颊通红！
      rect(ctx, '#ffffff', -5, -1, 5, 5);
      rect(ctx, '#ffffff', 6, -1, 5, 5);
      rect(ctx, '#09090d', -4, 0, 4, 4);
      rect(ctx, '#09090d', 6, 0, 4, 4);
      // 眼角倒竖的粗黑怒眉
      limb(ctx, PAL.outline, 2, [[-6, -3], [0, 0]]);
      limb(ctx, PAL.outline, 2, [[12, -3], [5, 0]]);
      // 双颊通红
      rect(ctx, PAL.rageRed, -7, 5, 4, 3);
      rect(ctx, PAL.rageRed, 9, 5, 4, 3);
      // 怒吼或气呼呼的嘴巴
      if (angryStage === 4 || angryStage === 5) {
        rect(ctx, '#7f1d1d', 0, 6, 6, 4);
        rect(ctx, '#fca5a5', 1, 7, 4, 2);
      } else {
        rect(ctx, '#7f1d1d', 0, 7, 6, 2);
      }
    } else {
      // 阶段 1（怀疑人生）：呆萌大黑豆圆眼低头看手
      rect(ctx, '#09090d', -3, 1, 3, 3);
      rect(ctx, '#09090d', 7, 1, 3, 3);
      rect(ctx, '#ffffff', -3, 1, 1, 1);
      rect(ctx, '#ffffff', 7, 1, 1, 1);
      rect(ctx, PAL.cheek, -6, 5, 3, 2);
      rect(ctx, PAL.cheek, 9, 5, 3, 2);
      rect(ctx, '#81474e', 2, 8, 4, 2);
    }
  } else {
    // 侧面挖土 / 喘气 / 看彩蛋：经典呆萌大黑豆圆眼
    const eyeY = 1 + (pitch > 4 ? 1 : 0);
    rect(ctx, '#09090d', 8, eyeY, 3, 3);
    rect(ctx, '#ffffff', 8, eyeY, 1, 1);
    rect(ctx, PAL.cheek, 4, 5, 3, 2);
    if (pitch > 3) {
      // 停铲大口喘气时微张的嘴巴
      rect(ctx, '#874a50', 9, 7, 4, 3);
    } else {
      rect(ctx, '#b57473', 9, 8, 4, 1);
    }
  }

  // 略微歪戴的黄色安全帽（向上微抬并倾斜 1~2px，清晰露出下方两侧的地中海卷发！）
  ctx.save();
  ctx.translate(0, -2);
  ctx.rotate(-0.08);
  poly(ctx, PAL.outline, [
    [-16, -6], [-14, -10], [-11, -18], [-6, -21], [5, -21],
    [11, -18], [14, -10], [18, -8], [18, -4], [-16, -4],
  ]);
  poly(ctx, PAL.hat, [
    [-13, -8], [-10, -17], [-6, -20], [5, -20], [10, -16],
    [13, -9], [16, -7], [15, -5], [-14, -5],
  ]);
  poly(ctx, PAL.hatLight, [[-9, -16], [-5, -19], [3, -19], [6, -17], [6, -10], [-10, -10]]);
  rect(ctx, '#ffffff', -4, -18, 5, 2);
  rect(ctx, PAL.hatShade, -14, -8, 29, 2);
  ctx.restore();

  // 阶段 2（怒火中烧）：头顶冒出跳动的红色十字青筋 💢
  if (angryStage === 2 || angryStage === 3) {
    drawRedCrossVein(ctx, 11, -22, clock);
  }

  // 阶段 5（罢工跺脚）：浑身沾满污泥脏透（头部与安全帽泥斑）
  if (dirty) {
    for (const [dx, dy, w, ht] of [
      [-10, -17, 8, 4], [-3, -13, 4, 3], [8, -18, 5, 7],
      [1, -7, 7, 3], [-6, 4, 6, 5], [7, 5, 5, 3], [11, -2, 3, 3],
    ]) {
      rect(ctx, PAL.soil, dx, dy, w, ht);
      rect(ctx, PAL.soilDark, dx + 1, dy + ht - 2, w - 1, 2);
    }
  }
  ctx.restore();

  // 阶段 5（罢工跺脚）：身体与背带裤浑身泥斑
  if (dirty) {
    for (const [dx, dy, w, ht] of [
      [-10, -41, 9, 5], [-7, -36, 5, 8], [3, -34, 7, 4],
      [-8, -25, 11, 5], [5, -23, 6, 4],
    ]) {
      rect(ctx, PAL.soil, mid + dx, dy + drop, w, ht);
      rect(ctx, PAL.soilDark, mid + dx, dy + drop + ht - 2, w - 1, 2);
    }
    rect(ctx, PAL.soil, ax - 2, ay - 10, 6, 4);
    rect(ctx, PAL.soilRidge, bx + 1, by - 5, 5, 2);
  }

  // 疲累时的汗水滴落
  if (pitch > 3 && drop >= 3 && Math.sin(clock * 12) > 0.35) {
    rect(ctx, '#7dd3fc', lean - 13, h + 4, 2, 4);
  }

  ctx.restore();
}

function breath(ctx, x, y, p) {
  // 停打喘气时嘴里呼出的白色喘气像素云团
  ctx.save();
  for (let i = 0; i < 3; i++) {
    const q = unit(p * 1.25 - i * 0.15);
    ctx.globalAlpha = (1 - q) * 0.88;
    rect(ctx, '#e2e8f0', x + q * 22, y - q * 11 + i * 2, 3 + q * 6, 2 + q * 2);
  }
  ctx.restore();
}

function dust(ctx, x, y, p, count, seed) {
  for (let i = 0; i < count; i++) {
    const q = unit(p * 1.12 - pick(seed, i) * 0.08);
    const px = x + (pick(seed + 7, i) - 0.39) * 66 * q;
    const py = y - (12 + pick(seed + 14, i) * 50) * 4 * q * (1 - q) + 4 * q;
    const width = 1.5 + pick(seed + 1, i) * 5.5;
    rect(ctx, [PAL.soil, PAL.soilRidge, PAL.soilLight][i % 3], px, py, width, width * 0.72);
  }
}

function treasure(ctx, kind, p) {
  // 挖土随机彩蛋：0=破烂旧球鞋, 1=压扁易拉罐, 2=闪亮小金币
  // p < 0.48: 从土坑铲出落在土堆旁，小人低头愣神看它；p >= 0.48: 被小人一脚踢飞到画面右侧！
  ctx.save();
  let x, y;
  if (p < 0.48) {
    const dropP = unit(p / 0.25);
    x = 138 - dropP * 14;
    y = 114 - 16 * 4 * dropP * (1 - dropP) + 4 * dropP;
  } else {
    const kickP = unit((p - 0.48) / 0.52);
    x = 124 + kickP * 68;
    y = 118 - 32 * 4 * kickP * (1 - kickP) - kickP * 6;
    ctx.globalAlpha = Math.min(1, (1 - kickP) * 2.5);
  }

  ctx.translate(Math.round(x), Math.round(y));
  if (p >= 0.48) {
    ctx.rotate((p - 0.48) * 14);
  }

  if (kind === 0) {
    // 0: 破烂旧球鞋 (Old Worn Sneaker)
    rect(ctx, '#f8fafc', -7, 2, 15, 3);        // 白色脏鞋底
    poly(ctx, '#b91c1c', [[-7, 2], [-6, -5], [0, -5], [5, -1], [8, 0], [8, 2]]); // 红色破鞋面
    rect(ctx, '#fde047', -3, -3, 3, 1);        // 鞋带横条
    rect(ctx, '#714327', 2, 0, 4, 2);          // 鞋头泥巴斑
    limb(ctx, '#cbd5e1', 1, [[0, -4], [3, -7], [5, -5]]); // 散开的鞋带
  } else if (kind === 1) {
    // 1: 压扁易拉罐 (Crushed Soda Can)
    poly(ctx, '#94a3b8', [[-6, -3], [6, -4], [7, 3], [-7, 4]]);
    poly(ctx, '#ef4444', [[-5, -2], [1, -3], [3, 0], [5, 2], [-5, 3]]); // 压瘪的红白罐身
    rect(ctx, '#f8fafc', -2, -1, 5, 2);        // 易拉罐白色条纹
    rect(ctx, '#cbd5e1', -7, -3, 2, 6);        // 金属罐底
    rect(ctx, '#e2e8f0', 5, -3, 2, 6);         // 金属拉环口
  } else {
    // 2: 闪亮小金币 (Shiny Gold Coin)
    poly(ctx, '#b45309', [[-6, 0], [-3, -6], [3, -6], [6, 0], [3, 6], [-3, 6]]);
    poly(ctx, '#facc15', [[-4, 0], [-2, -5], [2, -5], [4, 0], [2, 5], [-2, 5]]);
    rect(ctx, '#fef08a', -1, -3, 2, 6);
    // 闪耀十字星芒
    rect(ctx, '#ffffff', -8, -7, 3, 1);
    rect(ctx, '#ffffff', -7, -8, 1, 3);
  }
  ctx.restore();
}

function flyingMudZoom(ctx, mud, now) {
  // 阶段 4：将大团湿泥笔直朝镜头（用户脸部）猛甩过来，伴随 4.5 倍景深逐帧放大与呼啸破风线！
  const { launch_time_ms: launch, impact_time_ms: impact } = mud;
  const flyDuration = Math.max(1, impact - launch); // 严格 520ms
  const p = (now - launch) / flyDuration;
  if (p < 0 || p > 1.06) return;

  const clampedP = unit(p);
  // 从小人手部位置 (104, 86) 笔直迎面冲向全息镜头正中心 (110, 78)
  const x = lerp(104, 110, clampedP);
  const y = lerp(86, 78, clampedP) - Math.sin(clampedP * Math.PI) * 10;

  // 1.0x -> 4.5x 景深逐帧指数放大！
  const zoom = 1.0 + 3.5 * (clampedP ** 1.45);
  const r = 9.0 * zoom;

  ctx.save();
  // 呼啸破风速度线（从中心向外辐射）
  for (let i = 0; i < 10; i++) {
    const ang = (i / 10) * Math.PI * 2 + clampedP * 2.5;
    const rIn = r * 0.95;
    const rOut = r * (1.35 + (i % 3) * 0.22);
    ctx.strokeStyle = i % 2 === 0 ? 'rgba(255, 248, 220, 0.55)' : 'rgba(214, 162, 104, 0.45)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x + Math.cos(ang) * rIn, y + Math.sin(ang) * rIn);
    ctx.lineTo(x + Math.cos(ang) * rOut, y + Math.sin(ang) * rOut);
    ctx.stroke();
  }

  // 四周伴飞的泥浆碎块粒子
  for (let i = 0; i < 12; i++) {
    const ang = i * 0.52 + clampedP * 3.1;
    const dist = r * (1.05 + pick(mud.serial, i) * 0.45);
    const px = x + Math.cos(ang) * dist;
    const py = y + Math.sin(ang) * dist * 0.85;
    const pr = 1.5 + zoom * 0.9;
    rect(ctx, i % 2 ? PAL.soil : PAL.soilRidge, px - pr / 2, py - pr / 2, pr, pr);
  }

  // 超大浓稠湿泥巴本体（多层高光与凹凸质感）
  const lobes = [0.92, 1.12, 0.86, 1.08, 0.91, 1.04, 1.13, 0.88, 1.06, 0.93].map((v, i) => {
    const angle = (i * Math.PI) / 5 + clampedP * 2.2;
    return [Math.cos(angle) * v, Math.sin(angle) * v];
  });
  poly(ctx, '#24120b', lobes.map(([dx, dy]) => [x + r * dx, y + r * dy * 0.85]));
  poly(ctx, PAL.soilDark, lobes.map(([dx, dy]) => [x + r * dx * 0.90, y + r * dy * 0.76 - 1]));
  poly(ctx, PAL.soil, lobes.map(([dx, dy]) => [x + r * dx * 0.74, y + r * dy * 0.62 - 2]));
  poly(ctx, PAL.soilRidge, lobes.map(([dx, dy]) => [x + r * dx * 0.45 - r * 0.1, y + r * dy * 0.38 - r * 0.15]));
  // 湿润泥浆反光条
  limb(ctx, PAL.soilLight, Math.max(2, Math.round(zoom * 1.4)), [
    [x - r * 0.48, y - r * 0.18],
    [x - r * 0.20, y - r * 0.42],
    [x + r * 0.32, y - r * 0.34],
  ]);
  ctx.restore();
}

function renderHologramBath(ctx, state, bath, enterP, clock) {
  /**
   * 全息端木桶浴缸泡澡场景（100% 遵循 PG 级健康合规标准）：
   * 1. 木桶浴缸从下方平滑推入全息中心；
   * 2. 木桶内填满高出边缘的彩色肥皂泡沫（Bubble Foam）；
   * 3. 小人跳入后仅露出圆圆的地中海小脑勺/呆萌脸与双肩，下半身完全淹没在泡泡与木桶中；
   * 4. 水面漂浮着一只晃晃悠悠的黄色橡皮小鸭子（Rubber Duck）；
   * 5. 若水温拧到过烫 (>72°C)，小人浑身烫红像煮熟龙虾一样哇呀乱叫跳出水面（腰部以下依然包裹厚泡泡与小黄鸭短裤）！
   */
  const tubX = 110;
  // 推入浴缸入场滑动动画
  const tubY = lerp(175, 118, enterP);
  const isHot = Boolean(bath.hot_jump);
  const foamRatio = Math.max(0.3, (bath.foam ?? 70) / 100);

  ctx.save();
  ctx.translate(tubX, Math.round(tubY));

  // 入场滑入时的水花飞溅粒子
  if (enterP < 0.98) {
    for (let i = 0; i < 10; i++) {
      const ang = -Math.PI * 0.85 + (i / 9) * Math.PI * 0.7;
      const dist = 28 + Math.sin(enterP * Math.PI) * 26;
      const sx = Math.cos(ang) * dist * 1.3;
      const sy = -18 + Math.sin(ang) * dist;
      rect(ctx, i % 2 ? '#7dd3fc' : '#e0f2fe', sx, sy, 3, 3);
    }
  }

  // 底部水洼投影
  poly(ctx, '#0f2942', [[-48, 8], [48, 8], [54, 14], [-54, 14]]);

  // 1. 绘制如果水温过烫跳出水面时的下半身遮挡（深蓝小黄鸭短裤 + 腰部纯白泡泡环）
  const jumpOffset = isHot ? (18 + Math.abs(Math.sin(clock * 18)) * 14) : 0;
  const charY = -20 - jumpOffset;
  const skinColor = isHot ? '#ef4444' : PAL.skin; // 过烫时变成煮熟龙虾红！

  if (isHot) {
    // 龙虾烫跳时的双腿与深蓝小黄鸭大短裤（杜绝任何无着装状态）
    rect(ctx, skinColor, -9, charY + 12, 5, 8);
    rect(ctx, skinColor, 4, charY + 12, 5, 8);
    rect(ctx, '#1d3b6e', -13, charY + 3, 26, 10);
    rect(ctx, '#facc15', -8, charY + 6, 3, 3);
    rect(ctx, '#facc15', 5, charY + 6, 3, 3);
    // 挥舞乱叫的双臂
    const wave = Math.sin(clock * 28) * 6;
    limb(ctx, '#b91c1c', 6, [[-12, charY - 6], [-22, charY - 18 + wave]]);
    limb(ctx, '#b91c1c', 6, [[12, charY - 6], [22, charY - 18 - wave]]);
    // 腰部随身包裹的厚实纯白肥皂泡泡云团
    for (const [bx, by, bw] of [[-12, charY + 2, 9], [-4, charY + 1, 10], [5, charY + 2, 9]]) {
      rect(ctx, '#f8fafc', bx, by, bw, 7);
    }
  }

  // 2. 绘制泡在浴缸里的地中海小人双肩与头部（正常仅露出圆圆的地中海脑袋与双肩！）
  // 双肩（仅露在泡沫上方一点点）
  poly(ctx, PAL.outline, [[-15, charY - 7], [15, charY - 7], [17, charY + 4], [-17, charY + 4]]);
  poly(ctx, skinColor, [[-13, charY - 6], [13, charY - 6], [15, charY + 3], [-15, charY + 3]]);

  // 头部（摘下安全帽，100% 展现经典地中海微秃头顶与两侧深紫棕卷发！）
  const headY = charY - 19 + (isHot ? 0 : Math.sin(clock * 4) * 1.2);
  ctx.save();
  ctx.translate(0, Math.round(headY));
  // 地中海两侧蓬松卷发
  poly(ctx, PAL.hair, [[-14, -9], [14, -9], [16, -2], [15, 9], [9, 13], [-9, 13], [-15, 9], [-16, -2]]);
  rect(ctx, PAL.hairLight, -15, -5, 5, 9);
  rect(ctx, PAL.hairLight, 10, -5, 5, 9);
  // 圆润脸庞与微秃头顶
  poly(ctx, skinColor, [[-10, -10], [10, -10], [12, 2], [9, 11], [-9, 11], [-12, 2]]);
  // 头顶一撮呆萌小泡泡皇冠
  rect(ctx, '#ffffff', -5, -14, 10, 5);
  rect(ctx, '#bae6fd', -3, -16, 6, 3);

  if (isHot) {
    // 过烫龙虾表情：黑豆眼惊恐瞪圆 + 哇呀乱叫大张嘴 + 滚烫蒸汽
    rect(ctx, '#ffffff', -7, -2, 5, 5);
    rect(ctx, '#ffffff', 2, -2, 5, 5);
    rect(ctx, '#09090d', -6, -1, 3, 3);
    rect(ctx, '#09090d', 3, -1, 3, 3);
    rect(ctx, '#450a0a', -3, 5, 6, 5);
    rect(ctx, '#fca5a5', -2, 6, 4, 3);
    // 头顶冒出滚烫蒸汽团
    for (let i = 0; i < 3; i++) {
      const sy = -20 - ((clock * 22 + i * 7) % 14);
      const sx = -10 + i * 10 + Math.sin(clock * 8 + i) * 3;
      rect(ctx, '#fecaca', sx, sy, 5, 4);
    }
  } else {
    // 温暖泡澡舒服享受的眯眼表情 (^  ^) + 粉红脸颊 + 音符
    limb(ctx, PAL.outline, 2, [[-7, 1], [-4, -2], [-1, 1]]);
    limb(ctx, PAL.outline, 2, [[1, 1], [4, -2], [7, 1]]);
    rect(ctx, '#f472b6', -9, 3, 4, 2);
    rect(ctx, '#f472b6', 5, 3, 4, 2);
    rect(ctx, '#9f1239', -2, 6, 4, 2);
  }
  ctx.restore();

  // 3. 【浴缸场景合规处理】：高出木桶边缘的彩色肥皂泡沫云团 (Bubble Foam) —— 完全淹没下半身！
  const bubbleColors = ['#ffffff', '#fce7f3', '#e0f2fe', '#dcfce7', '#fef3c7', '#f3e8ff'];
  const foamHeight = 4 + foamRatio * 7;
  for (let i = 0; i < 15; i++) {
    const bx = -36 + i * 5.2;
    const by = -18 - Math.sin(i * 0.9 + clock * 3) * 3 - (i % 2) * (foamHeight * 0.45);
    const bw = 9 + (i % 3) * 2;
    const bh = 8 + (i % 2) * 3;
    const col = bubbleColors[i % bubbleColors.length];
    rect(ctx, col, bx - bw / 2, by - bh / 2, bw, bh);
    rect(ctx, '#ffffff', bx - bw / 4, by - bh / 3, 2, 2);
  }

  // 4. 【浴缸场景合规处理】：水面上漂浮着一只晃晃悠悠的黄色橡皮小鸭子 (Rubber Duck)！
  const duckX = 22 + Math.sin(clock * 2.6) * 4;
  const duckY = -21 + Math.cos(clock * 3.4) * 1.8;
  ctx.save();
  ctx.translate(Math.round(duckX), Math.round(duckY));
  // 橡皮小鸭子身体与翘尾巴
  poly(ctx, '#111118', [[-8, 3], [-7, -4], [0, -9], [6, -8], [8, -2], [9, 3]]);
  rect(ctx, '#facc15', -6, -2, 13, 5);   // 亮黄鸭身
  rect(ctx, '#fde047', -4, -7, 8, 6);    // 圆圆鸭头
  rect(ctx, '#eab308', -2, 0, 6, 3);     // 小翅膀
  rect(ctx, '#f97316', -8, -5, 4, 3);    // 橘色扁鸭嘴
  rect(ctx, '#09090d', -2, -5, 2, 2);    // 小黑豆鸭眼
  ctx.restore();

  // 5. 精致像素木桶浴缸本体（加厚橡木桶壁 + 两道金色铜箍）
  poly(ctx, PAL.outline, [[-44, -16], [44, -16], [39, 11], [-39, 11]]);
  poly(ctx, '#92400e', [[-42, -14], [42, -14], [37, 9], [-37, 9]]);
  // 木桶竖条纹理
  for (let x = -34; x <= 34; x += 9) {
    rect(ctx, '#78350f', x, -14, 2, 23);
    rect(ctx, '#b45309', x + 2, -14, 4, 22);
  }
  // 木桶顶部宽厚圆润木沿
  rect(ctx, PAL.outline, -46, -18, 92, 5);
  rect(ctx, '#d97706', -45, -17, 90, 3);
  rect(ctx, '#fde68a', -43, -17, 86, 1);
  // 两道金属铜箍
  rect(ctx, '#fbbf24', -40, -7, 80, 3);
  rect(ctx, '#fbbf24', -38, 2, 76, 3);

  // 漂浮上升的彩色肥皂小气泡
  for (let i = 0; i < 6; i++) {
    const p = ((clock * 0.65 + i * 0.19) % 1.0);
    const bx = -28 + i * 11 + Math.sin(clock * 4 + i) * 4;
    const by = -24 - p * 34;
    const bc = bubbleColors[(i + 2) % bubbleColors.length];
    rect(ctx, bc, bx, by, 4, 4);
    rect(ctx, '#ffffff', bx, by, 1, 1);
  }

  ctx.restore();
}
