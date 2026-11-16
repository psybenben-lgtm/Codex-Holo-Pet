'use strict';

/**
 * 像素级渲染引擎 (Pixel v5.0)
 * 包含：
 * 1. 原生左向咖啡壶 (iPhone 端白底纯净渲染)
 * 2. 放大精致全息杯 + 细腻水滴抛物线水流 + 自然水体融合与波纹飞溅
 * 3. Codex 工位与小人动画 (带黄色黑边 codex 标识)
 * 4. 跨屏叹气握铲离场 + 电脑桌宠 100% 背面视角合规搓澡（深蓝小黄鸭短裤、纯白泡泡云、搞笑像素马赛克、受力弹性形变、搓头扭头弹出大黑问号❓、洗净冒金星）+ 屏幕湿泥爆裂挂壁流淌
 */
const Pixel = (() => {
  const mix = (a, b, t) => a + (b - a) * t;
  const clamp = (x, min = 0, max = 1) => Math.max(min, Math.min(max, x));
  const ease = t => (t = clamp(t), t * t * (3 - 2 * t));

  const box = (g, color, x, y, w, h) => {
    g.fillStyle = color;
    g.fillRect(Math.round(x), Math.round(y), Math.max(1, Math.round(w)), Math.max(1, Math.round(h)));
  };

  function poly(g, points, color) {
    g.fillStyle = color;
    g.beginPath();
    points.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y));
    g.closePath();
    g.fill();
  }

  function line(g, color, width, ...points) {
    g.strokeStyle = color;
    g.lineWidth = width;
    g.beginPath();
    points.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y));
    g.stroke();
  }

  function textWithOutline(g, text, x, y, fill = '#ffdc38', stroke = '#080909', size = 8) {
    g.font = `bold ${size}px Consolas, monospace`;
    g.fillStyle = stroke;
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        if (dx || dy) g.fillText(text, x + dx, y + dy);
      }
    }
    g.fillStyle = fill;
    g.fillText(text, x, y);
  }

  function ellipse(g, color, x, y, rx, ry) {
    g.beginPath();
    g.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), 0, 0, Math.PI * 2);
    g.fillStyle = color;
    g.fill();
  }

  // 原生左向咖啡壶几何定义
  const leftGlass = [
    [139,70],[87,70],[75,74],[58,74],[45,66],[47,78],[61,91],[73,94],[67,108],[59,127],
    [58,149],[63,166],[73,178],[87,183],[136,183],[153,176],[162,162],[164,145],[162,126],
    [157,111],[146,91]
  ];

  const leftInside = [
    [135,74],[88,74],[75,78],[57,78],[49,72],[51,77],[63,87],[78,90],[72,109],[64,127],
    [62,147],[66,162],[76,174],[88,178],[135,178],[149,172],[157,160],[159,145],[157,127],
    [152,112],[141,92]
  ];

  function lowerPolygon(points, level) {
    const out = [];
    for (let i = 0; i < points.length; i++) {
      const a = points[i], b = points[(i + 1) % points.length];
      if (a[1] >= level) out.push(a);
      if ((a[1] >= level) !== (b[1] >= level)) {
        out.push([mix(a[0], b[0], (level - a[1]) / (b[1] - a[1])), level]);
      }
    }
    return out;
  }

  // 1. iPhone 倒咖啡画面 (纯净白底，原生左向壶嘴)
  function pour(g, model, now) {
    g.fillStyle = '#ffffff';
    g.fillRect(0, 0, 220, 250);

    poly(g, [
      [142,84],[169,83],[181,89],[189,102],[191,121],[187,141],[177,157],[163,163],
      [158,152],[168,149],[175,138],[178,120],[176,104],[170,96],[145,96]
    ], '#36424e');
    poly(g, [
      [144,83],[169,83],[181,89],[189,103],[191,118],[186,115],[183,102],[176,93],[166,89],[145,89]
    ], '#8ca5a7');
    poly(g, [
      [188,131],[182,144],[172,152],[163,155],[161,160],[168,161],[177,157],[184,147]
    ], '#546673');

    poly(g, leftGlass, '#88afb0');
    const glassShine = g.createLinearGradient(65, 0, 165, 0);
    glassShine.addColorStop(0, '#e4eef0');
    glassShine.addColorStop(0.5, '#fbfdfd');
    glassShine.addColorStop(1, '#dce8ea');
    poly(g, leftInside, glassShine);

    if (model.fluid) {
      model.fluid.draw(g);

      if (model.fluid.drops.length > 0 || model.fluid.rate > 0.005) {
        const streamPower = Math.min(1.0, Math.max(0.2, model.fluid.rate * 2.5));
        const spoutX = 49, spoutY = 73;
        const arcLength = 45 + streamPower * 45;
        const cpX = spoutX - arcLength * 0.75;
        const cpY = spoutY - 6;
        const endX = spoutX - arcLength * 1.35;
        const endY = spoutY + arcLength * 1.15;

        g.strokeStyle = '#c88648';
        g.lineWidth = 3.2 * streamPower;
        g.lineCap = 'round';
        g.beginPath();
        g.moveTo(spoutX, spoutY);
        g.quadraticCurveTo(cpX, cpY, endX, endY);
        g.stroke();

        g.strokeStyle = '#f8d298';
        g.lineWidth = 1.6 * streamPower;
        g.beginPath();
        g.moveTo(spoutX, spoutY);
        g.quadraticCurveTo(cpX, cpY, endX, endY);
        g.stroke();

        for (let i = 0; i < 4; i++) {
          const u = ((now / 220 + i * 0.26) % 1);
          const px = (1 - u) * (1 - u) * spoutX + 2 * (1 - u) * u * cpX + u * u * endX;
          const py = (1 - u) * (1 - u) * spoutY + 2 * (1 - u) * u * cpY + u * u * endY;
          ellipse(g, '#d89452', px, py, 1.8 + (1 - u), 2.2);
          ellipse(g, '#fff0d2', px - 0.4, py - 0.4, 0.7, 0.9);
        }
      }
    }

    poly(g, [
      [137,74],[142,91],[153,115],[158,137],[156,157],[151,168],[147,167],[153,156],
      [155,137],[150,116],[138,90],[133,75]
    ], 'rgba(163, 201, 202, 0.45)');

    poly(g, [
      [66,128],[63,146],[67,161],[76,172],[83,174],[82,178],[72,175],[63,165],[59,151],[59,138]
    ], 'rgba(92, 130, 145, 0.5)');

    poly(g, [
      [147,172],[134,178],[86,178],[74,173],[77,179],[87,182],[135,182],[147,178]
    ], '#c3d5cc');

    poly(g, [
      [144,69],[139,63],[93,63],[85,66],[85,73],[144,73]
    ], '#3b4a57');
    poly(g, [
      [136,63],[120,63],[118,56],[106,56],[103,63],[93,63],[87,67],[141,67]
    ], '#94a4a3');

    poly(g, [
      [87,70],[73,73],[58,73],[45,66],[48,74],[61,81],[70,81],[84,76]
    ], '#dbebe0');
    poly(g, [
      [70,81],[59,80],[47,74],[52,80],[62,87],[74,89]
    ], '#586f7b');

    for (let i = 0; i < 3; i++) {
      const y = 145 - i * 14;
      line(g, 'rgba(187, 168, 144, 0.65)', 1.5, [118, y], [128, y]);
    }
  }

  // 2. 金字塔全息接水端
  function cup(g, x, y, fill, t, scale = 1.85, small = false, surfaceWaves = null) {
    g.save();
    g.translate(Math.round(x), Math.round(y));
    g.scale(scale, scale);

    poly(g, [
      [25,-2],[39,-1],[45,5],[44,14],[38,20],[24,22],[24,17],[35,15],[39,11],[39,6],[35,3],[25,3]
    ], '#77a4ad');
    line(g, '#c0e0d8', 1, [29,0],[37,1],[42,5],[42,11]);

    poly(g, [
      [-28,-5],[-24,-10],[24,-10],[28,-5],[27,10],[24,20],[16,28],[-16,28],[-23,23],[-27,14]
    ], '#87b8ba');

    const insideCup = [
      [-25,-5],[25,-5],[24,9],[21,18],[15,24],[-15,24],[-20,20],[-24,12]
    ];
    const glassBody = g.createLinearGradient(-23, 0, 23, 0);
    glassBody.addColorStop(0, '#2e434c');
    glassBody.addColorStop(0.5, '#121922');
    glassBody.addColorStop(1, '#2c4049');
    poly(g, insideCup, glassBody);

    if (fill > 0.0002) {
      const surface = 24 - Math.max(1, fill * 31);
      const liquid = lowerPolygon(insideCup, surface);
      const sides = liquid.filter(p => Math.abs(p[1] - surface) < 0.05);
      const left = sides.length ? Math.min(...sides.map(p => p[0])) : -18;
      const right = sides.length ? Math.max(...sides.map(p => p[0])) : 18;

      const coffee = g.createLinearGradient(0, surface, 0, 25);
      coffee.addColorStop(0, '#e8b476');
      coffee.addColorStop(0.35, '#c9884a');
      coffee.addColorStop(1, '#9e6231');
      poly(g, liquid, coffee);

      const waveLine = [];
      const steps = 30;
      for (let i = 0; i <= steps; i++) {
        const xx = left + (right - left) * i / steps;
        const wave = surfaceWaves ? (surfaceWaves[i] || 0) : Math.sin(xx * 0.4 + t / 80) * 0.4;
        waveLine.push([xx, surface + wave]);
      }

      poly(g, [...waveLine, [right, Math.min(24, surface + 4)], [left, Math.min(24, surface + 4)]], '#d89b5d');

      g.save();
      g.beginPath();
      g.ellipse(0, surface + 0.8, Math.max(1, (right - left) / 2), Math.min(3.5, 1 + fill * 3), 0, 0, Math.PI * 2);
      g.clip();
      g.fillStyle = '#fce4be';
      g.fillRect(left, surface - 4, right - left, 9);

      g.strokeStyle = '#fff5de';
      g.lineWidth = 0.7;
      g.beginPath();
      waveLine.forEach(([xx, yy], i) => i ? g.lineTo(xx, yy) : g.moveTo(xx, yy));
      g.stroke();
      g.restore();
    }

    g.beginPath();
    g.ellipse(0, -5, 26, 5, 0, 0, Math.PI * 2);
    g.lineWidth = 1.5;
    g.strokeStyle = '#bfdcd7';
    g.stroke();

    line(g, '#e0f4e6', 1.8, [-24,0],[-23,10],[-19,19],[-15,22]);
    line(g, '#6b9da6', 1.2, [24,2],[23,12],[19,20]);

    if (!small) {
      box(g, '#f7efdd', -26, -6, 4, 2);
      box(g, '#bbd4cc', -12, 25, 24, 2);
    }
    g.restore();
  }

  const trajectory = (u, targetX, targetY) => {
    const startX = targetX + 72;
    const startY = targetY - 110;
    const x = mix(startX, targetX, u);
    const y = startY + (targetY - startY) * (u * u);
    return [x, y];
  };

  function holo(g, model, t) {
    box(g, '#000000', 0, 0, 220, 160);

    const scale = 1.85;
    const transfer = ease(model.lift);
    const centerX = 110;
    const targetY = 96;
    const x = mix(centerX, -70, transfer);
    const y = mix(targetY, 55, transfer);

    const surfaceY = 24 - 31 * model.fill;
    const impactY = y + scale * surfaceY;
    const impactX = x;

    if (model.fill >= 0.78 && model.lift < 1) {
      const glowPulse = 0.5 + 0.5 * Math.sin(t / 140);
      g.save();
      g.strokeStyle = `rgba(248, 218, 150, ${0.45 * glowPulse})`;
      g.lineWidth = 2.5;
      g.beginPath();
      g.ellipse(x, y + scale * 8, 38 * scale, 22 * scale, 0, 0, Math.PI * 2);
      g.stroke();
      g.restore();
    }

    if (model.lift < 1) {
      ellipse(g, '#1a262c', x, y + scale * 26, 38 * (1 - transfer), 4);
      ellipse(g, '#2f454d', x, y + scale * 25.5, 33 * (1 - transfer), 2.5);
      cup(g, x, y, model.fill, t, scale, false, model.waves);
    }

    const sections = [];
    for (const [age, power] of [...model.flight].reverse()) {
      const end = clamp(age);
      const start = Math.max(0, end - 0.35);
      const last = sections[sections.length - 1];
      if (last && start <= last.end + 0.05) {
        last.end = end;
        last.power = Math.max(last.power, power);
      } else {
        sections.push({ start, end, power });
      }
    }

    for (const section of sections) {
      const end = (section.end > 0.65 && model.hit < 0.08) ? 1.0 : section.end;
      const thickness = 1.3 + 2.2 * Math.sqrt(section.power);

      for (let u = section.start; u < end; u += 0.016) {
        const [xx, yy] = trajectory(u, impactX, impactY);
        const stretch = 1.0 - 0.3 * u;
        const pulse = Math.sin(u * 50 - t / 35);
        const w = thickness * stretch * (0.85 + 0.15 * pulse);

        ellipse(g, '#b8763b', xx, yy, w * 0.9, 1.8);
        ellipse(g, '#e5aa65', xx, yy, w * 0.6, 1.4);
        if (Math.sin(u * 38 - t / 60) > 0.3) {
          ellipse(g, '#fff5dc', xx + w * 0.3, yy, 0.6, 1.0);
        }
      }

      for (let i = 0; i < 4; i++) {
        const offset = (t / 220 + i * 0.28) % 1;
        if (offset < section.start || offset > end) continue;
        const [xx, yy] = trajectory(offset, impactX, impactY);
        const sideJitter = Math.sin(i * 3 + t / 90) * 2.4;
        ellipse(g, '#c88448', xx + sideJitter, yy, 0.9, 1.2);
        ellipse(g, '#fff5dc', xx + sideJitter - 0.2, yy - 0.2, 0.45, 0.6);
      }
    }

    if (model.lift < 0.01) {
      for (const [age, energy, seed] of model.splash) {
        if (age < 0.35 && model.fill > 0.01) {
          const r = 2.5 + age * 48;
          const alpha = 0.65 * (1 - age / 0.35);
          g.strokeStyle = `rgba(248, 222, 175, ${alpha})`;
          g.lineWidth = 0.9;
          g.beginPath();
          g.ellipse(impactX, impactY, r, r * 0.22, 0, 0, Math.PI * 2);
          g.stroke();
        }

        for (let i = 0; i < 3; i++) {
          const vx = (i - 1) * 14 + Math.sin(seed + i) * 5;
          const vy = -(22 + energy * 18 + i * 4) * age + 150 * age * age;
          const px = impactX + vx * age;
          const py = impactY + vy;
          if (py > impactY + 1) continue;
          ellipse(g, i === 0 ? '#fff5dc' : '#d89b5d', px, py, 0.75, 0.95);
        }
      }

      if (model.hit < 0.1) {
        ellipse(g, '#8c5225', impactX, impactY + 0.6, 3.2, 1.1);
        g.strokeStyle = '#fae4c0';
        g.lineWidth = 0.8;
        g.beginPath();
        g.arc(impactX, impactY + 0.5, 2.6, 0.2, Math.PI - 0.2);
        g.stroke();
      }
    }
  }

  // 3. 工位小人背景与打字动画
  function room(g, t, working) {
    box(g, '#121421', 0, 0, 480, 270);
    for (let i = 0; i < 7; i++) {
      box(g, ['#161825','#191a28','#1d1d2b','#24202e','#2b222f','#332630','#3b2a31'][i], 0, i * 28, 480, 28);
    }
    box(g, '#514052', 0, 196, 480, 3);
    box(g, '#291d29', 0, 199, 480, 71);
    for (let y = 203; y < 270; y += 10) box(g, '#392633', 0, y, 480, 1);
    for (let x = -100; x < 580; x += 39) line(g, '#382432', 1, [240 + (x - 240) * 0.75, 199], [x, 270]);

    // 窗户与城市夜景
    box(g, '#47394a', 40, 46, 111, 94);
    box(g, '#1f2134', 43, 49, 105, 87);
    box(g, '#1d2439', 47, 53, 97, 76);
    box(g, '#33435c', 119, 62, 13, 14);
    box(g, '#d4cabb', 119, 61, 10, 11);
    box(g, '#26334c', 123, 60, 9, 7);
    for (let i = 0; i < 33; i++) {
      const x = 48 + (i * 73) % 94, y = 55 + (i * 47) % 63;
      box(g, i % 7 ? '#4b5064' : '#a29b8c', x, y, 1, 1);
    }
    for (let i = 0; i < 13; i++) {
      const x = 47 + i * 7, h = 8 + (i * 19) % 30;
      box(g, i % 2 ? '#30314a' : '#272940', x, 129 - h, 6, h);
      if (i % 3) box(g, '#696179', x + 2, 132 - h, 1, 2);
    }
    box(g, '#5d4956', 40, 92, 111, 2);
    box(g, '#67505a', 93, 47, 2, 89);
    box(g, '#8d6363', 36, 137, 119, 3);

    // 墙上海报
    box(g, '#594753', 294, 56, 108, 29);
    box(g, '#242132', 297, 59, 102, 23);
    textWithOutline(g, 'THE NIGHT SHIFT', 306, 75, '#e5ae89', '#242132', 9);
    box(g, '#7e565a', 294, 84, 108, 2);

    // 办公桌
    box(g, '#5b3944', 159, 154, 181, 12);
    box(g, '#a16357', 157, 153, 185, 4);
    box(g, '#79504d', 162, 159, 175, 6);
    box(g, '#563943', 164, 166, 7, 47);
    box(g, '#422e3d', 330, 166, 7, 47);
    box(g, '#5a3d46', 293, 168, 35, 32);
    box(g, '#714851', 295, 170, 31, 13);
    box(g, '#895855', 295, 185, 31, 13);
    box(g, '#c68b70', 306, 175, 9, 2);
    box(g, '#c68b70', 306, 190, 9, 2);

    // 显示器与支架
    box(g, '#805458', 239, 145, 24, 7);
    box(g, '#60434e', 248, 139, 6, 10);
    box(g, '#57475c', 221, 101, 65, 39);
    box(g, '#181d29', 224, 104, 59, 32);
    box(g, '#1e3740', 226, 106, 55, 28);
    box(g, '#344f54', 228, 108, 51, 4);
    box(g, '#e1ae72', 230, 109, 2, 2);
    box(g, '#6ba997', 235, 109, 2, 2);
    for (let i = 0; i < 4; i++) {
      box(g, '#426366', 230, 115 + 4 * i, 5, 1);
      box(g, i % 2 ? '#d4a883' : '#94c3a3', 238 + (i % 2) * 3, 115 + 4 * i, 15 + (i * 9) % 22, 1);
    }
    if (working && Math.floor(t / 320) % 2 === 0) {
      box(g, '#e6cf94', 262, 129, 4, 2);
    }

    // 键盘
    box(g, '#a38577', 226, 150, 47, 4);
    box(g, '#ddd0b2', 228, 149, 43, 1);
    for (let i = 0; i < 14; i++) box(g, '#64555b', 229 + i * 3, 151, 1, 1);

    // 台灯与柔和暖光
    line(g, '#af796a', 3, [176,152],[177,131],[185,113],[198,113]);
    poly(g, [[189,113],[202,113],[207,123],[185,123]], '#efb27c');
    box(g, '#ffd392', 186, 123, 20, 2);
    box(g, '#bb775b', 168, 151, 18, 2);
    poly(g, [[188,125],[205,125],[218,152],[176,152]], 'rgba(255,190,111,0.12)');

    // 室内绿植
    box(g, '#49424b', 414, 176, 33, 3);
    box(g, '#694c51', 419, 179, 23, 34);
    box(g, '#a15f58', 417, 176, 27, 4);
    poly(g, [[425,178],[424,153],[419,147],[412,145],[416,155],[423,161],[424,178]], '#7b9f8c');
    poly(g, [[427,176],[432,150],[435,143],[443,139],[440,153],[432,160],[430,176]], '#588377');
    poly(g, [[432,178],[442,157],[450,154],[447,163],[438,168],[435,178]], '#96a28b');

    box(g, '#352735', 12, 241, 149, 17);
    textWithOutline(g, 'CODEX / WORKSTATION 01', 19, 253, '#b69395', '#352735', 8);
  }

  function person(g, x, y, t, pose, working, carryShovel = false) {
    g.save();
    g.translate(Math.round(x), Math.round(y));

    const back = pose === 'back', walk = pose === 'walk', receive = pose === 'receive', sip = pose === 'sip', sigh = pose === 'sigh';
    const step = walk ? Math.sin(t / 68) * 4 : 0;
    const breathe = sigh ? -3 : (Math.floor(t / 580) % 2);

    ellipse(g, '#1e1928', 0, 2, 23, 4);

    if (back) {
      box(g, '#312533', -15, -30, 29, 34);
      box(g, '#79505a', -16, -33, 31, 17);
      box(g, '#9a6063', -14, -34, 27, 3);
      box(g, '#583945', -11, -12, 24, 14);
      box(g, '#493240', -9, 1, 3, 7);
      box(g, '#493240', 8, 1, 3, 7);
    } else {
      box(g, '#272a3e', -11, -19, 11, 16 + step);
      box(g, '#37354b', 3, -19, 9, 16 - step);
      box(g, '#936c73', -13, -4 + step, 13, 4);
      box(g, '#ad837e', 3, -4 - step, 13, 4);
    }

    g.translate(0, -breathe);

    // 上衣身躯
    poly(g, [[-16,-39],[-10,-44],[10,-44],[17,-38],[15,-16],[-14,-16]], '#586e94');
    box(g, '#7a9abe', -12, -41, 22, 4);
    box(g, '#405578', -13, -22, 26, 5);
    box(g, '#394461', -8, -36, 16, 5);
    box(g, '#a2b9c9', -4, -34, 8, 1);

    if (back) {
      const tap = working && Math.floor(t / 105) % 2;
      box(g, '#6d86aa', -19, -38, 6, 14);
      box(g, '#7897b4', 13, -38, 6, 14);
      box(g, '#dca789', -21, -43 + tap * 2, 5, 5);
      box(g, '#e9b496', 17, -43 + (working && !tap ? 2 : 0), 5, 5);
    } else {
      box(g, '#687fa5', -19, -37, 7, 16);
      box(g, '#c88d76', -19, -22, 6, 5);
      line(g, '#7894b6', 7, [13,-36], [18,-27], [receive ? 30 : 20, sip ? -37 : -27]);
      box(g, '#e0ac8b', receive ? 29 : 19, sip ? -40 : -30, 6, 6);
      if (carryShovel) {
        // 起身离场时手持铁铲
        line(g, '#211c2c', 5, [10, -28], [36, -20]);
        line(g, '#d9a362', 3, [10, -28], [35, -20]);
        poly(g, [[34,-24],[45,-26],[47,-16],[34,-15]], '#9babaf');
      }
    }

    // 头部与发型
    poly(g, [[-15,-66],[-10,-72],[9,-72],[15,-67],[17,-55],[13,-47],[-11,-47],[-16,-54]], '#312a40');
    poly(g, [[-13,-65],[-9,-70],[9,-70],[14,-66],[13,-61],[-13,-60]], '#56445c');
    box(g, '#7b596e', -9, -69, 15, 2);
    box(g, '#47394e', -14, -59, 28, 7);
    box(g, '#d49a82', -5, -48, 10, 4);
    box(g, '#d9a58c', -17, -58, 4, 7);
    box(g, '#f0b995', 13, -58, 4, 7);

    if (!back) {
      poly(g, [[5,-62],[14,-63],[15,-57],[19,-54],[15,-51],[14,-47],[6,-48]], '#e2ac90');
      box(g, '#342b3d', 11, -57, 2, 2);
      box(g, sigh ? '#6c3d47' : '#ad6e6f', 12, -50, 3, sigh ? 2 : 1);
    }

    if (sigh) {
      // 嘴里呼出一小团白色叹气像素团
      for (let i = 0; i < 3; i++) {
        const p = ((t / 400) + i * 0.25) % 1;
        ellipse(g, 'rgba(226, 232, 240, 0.85)', 22 + p * 18, -50 - p * 10 + i * 2, 3 + i, 2 + i * 0.6);
      }
    }

    textWithOutline(g, 'codex', -17, -78, '#ffdc38', '#080909', 11);
    g.restore();
  }

  function drawDeskScrubbing(g, x, y, t, strikeState, nowMs) {
    /**
     * 网页端工位预览同步绘制 100% 背对镜头合规搓澡与问号微表情
     */
    const bath = strikeState.bath || {};
    const cleanPct = Number(bath.clean_progress || 0);
    const dirtyRatio = Math.max(0, 1 - cleanPct / 100);
    const zone = bath.scrub_zone || 'none';
    const isQuestion = zone === 'head' || nowMs < (bath.question_until || 0);
    const isScrubBack = zone === 'back' && nowMs < (bath.scrub_active_until || 0);
    const isCleanDone = strikeState.state === 'CLEAN_DONE';

    let dxShift = 0, dySquish = 0;
    if (isQuestion) {
      dxShift = 0; dySquish = 0;
    } else if (isCleanDone) {
      dySquish = -Math.abs(Math.sin(t / 110)) * 9;
    } else if (isScrubBack) {
      dxShift = Math.round((bath.scrub_dx || 0) * 8 + Math.sin(t / 35) * 3.5);
      dySquish = Math.round((bath.scrub_dy || 0) * 5 + Math.cos(t / 35) * 2.5);
    }

    g.save();
    g.translate(Math.round(x + dxShift), Math.round(y + dySquish));

    // 地面水洼
    ellipse(g, '#243b53', 0, 3, 28, 6);
    ellipse(g, '#38bdf8', 0, 3, 20, 3.5);

    // 1. 双腿与深蓝色带小黄鸭图案的宽松卡通平角大短裤 (PG 合规铁律)
    box(g, '#dca58e', -13, -14, 8, 15);
    box(g, '#dca58e', 5, -14, 8, 15);
    box(g, '#102242', -20, -30, 40, 19);
    box(g, '#1d3b6e', -19, -29, 38, 17);
    box(g, '#2e5aa6', -19, -29, 38, 4);
    box(g, '#102242', -1, -22, 2, 10);
    // 左右裤腿小黄鸭图案
    for (const [dx, dy] of [[-11, -20], [9, -20]]) {
      box(g, '#facc15', dx - 3, dy, 6, 4);
      box(g, '#fde047', dx - 2, dy - 3, 4, 3);
      box(g, '#f97316', dx + 2, dy - 2, 2, 2);
    }

    // 2. 100% 背向微胖短躯干
    poly(g, [[-18,-50],[-13,-56],[13,-56],[18,-50],[17,-26],[-17,-26]], '#e5ad8b');
    box(g, '#ca8e7e', -1, -52, 2, 20);

    // 双臂
    const armWave = isScrubBack ? Math.round(Math.sin(t / 55) * 3) : 0;
    box(g, '#e5ad8b', -24, -49 + armWave, 7, 17);
    box(g, '#e5ad8b', 17, -49 - armWave, 7, 17);

    // 背部泥斑 (随擦拭进度减少)
    const patches = [[-11,-50,8,6],[4,-51,9,6],[-5,-42,9,5],[-13,-37,7,5],[6,-38,8,5]];
    const visibleCount = Math.ceil(patches.length * dirtyRatio);
    for (let i = 0; i < visibleCount; i++) {
      const [px, py, pw, ph] = patches[i];
      box(g, '#5c3824', px, py, pw, ph);
      box(g, '#3b2214', px + 1, py + 1, pw - 2, ph - 2);
    }

    // 3. 胸部以下膨胀纯白肥皂泡泡云团 + 腰部搞笑像素马赛克方块
    for (const [bx, by, br] of [[-17,-27,8],[-9,-30,9],[0,-31,9],[9,-30,9],[17,-27,8],[-13,-21,8],[13,-21,8]]) {
      ellipse(g, '#f8fafc', bx, by, br, br * 0.9);
      ellipse(g, '#ffffff', bx - 2, by - 2, br * 0.4, br * 0.4);
    }
    const mosaicPalette = ['#f8dfa1', '#d4957a', '#f3c69f', '#b87b64', '#fae8c8', '#c78870'];
    const stepSeed = Math.floor(t / 150);
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 5; c++) {
        box(g, mosaicPalette[(r * 5 + c + stepSeed) % mosaicPalette.length], -12 + c * 5, -29 + r * 4, 5, 4);
      }
    }

    // 4. 经典地中海微秃后脑勺与两侧卷发
    poly(g, [[-15,-74],[-10,-80],[10,-80],[15,-74],[17,-62],[13,-55],[-13,-55],[-17,-62]], '#392e48');
    poly(g, [[-13,-73],[-9,-78],[9,-78],[13,-73],[12,-67],[-13,-67]], '#63506b');
    box(g, '#d99a88', -7, -77, 14, 4); // 地中海微秃发旋
    box(g, '#d99a88', -18, -67, 4, 7);
    box(g, '#e1a589', 14, -67, 4, 7);

    if (isQuestion) {
      // 【核心微表情】：搓错头部 —— 动作一僵，脑袋猛扭回头，圆眼无语瞪视 + 头顶超大黑色问号【❓】
      poly(g, [[-2,-74],[14,-74],[16,-57],[-2,-56]], '#e9b296');
      box(g, '#111118', 1, -69, 4, 4);
      box(g, '#ffffff', 1, -69, 1, 1);
      box(g, '#111118', 9, -69, 4, 4);
      box(g, '#ffffff', 9, -69, 1, 1);
      box(g, '#6c3d47', 4, -60, 6, 2);
      box(g, '#7dd3fc', -5, -70, 2, 6);
      // 头顶弹出大大的黑色问号【❓】
      const qBounce = Math.round(Math.sin(t / 45) * 3);
      box(g, '#111118', -14, -116 + qBounce, 28, 28);
      box(g, '#fff9db', -12, -114 + qBounce, 24, 24);
      textWithOutline(g, '?', -5, -96 + qBounce, '#09090d', '#facc15', 20);
    } else if (isScrubBack) {
      box(g, '#f472b6', -18, -62, 4, 3);
      box(g, '#f472b6', 14, -62, 4, 3);
      textWithOutline(g, '~ ♪ 舒服哼哼', 18, -82 - Math.round((t / 60) % 8), '#fde047', '#080909', 10);
    }

    // 5. 海绵擦与白色雪花泡沫星光
    if (nowMs < (bath.scrub_active_until || 0) + 180 && !isCleanDone) {
      const sx = Math.round(((bath.scrub_x ?? 0.5) - 0.5) * 34);
      const sy = isQuestion ? -68 : Math.round(-42 + ((bath.scrub_y ?? 0.55) - 0.55) * 22);
      box(g, '#ca8a04', sx - 12, sy - 8, 24, 16);
      box(g, '#facc15', sx - 11, sy - 7, 22, 11);
      box(g, '#16a34a', sx - 11, sy + 4, 22, 4);
      for (let i = 0; i < 6; i++) {
        const a = t / 90 + i * 1.05;
        ellipse(g, '#ffffff', sx + Math.cos(a) * 15, sy + Math.sin(a) * 11, 3, 3);
      }
    }

    if (isCleanDone) {
      for (const [ox, oy] of [[-30,-65],[30,-65],[-34,-35],[34,-35],[0,-88]]) {
        textWithOutline(g, '★', ox - 4, oy, '#fde047', '#080909', 12);
      }
      textWithOutline(g, '100% 满血洗净!', -36, -98, '#4ade80', '#080909', 11);
    } else if (!isQuestion) {
      textWithOutline(g, `codex · 去污 ${Math.round(cleanPct)}%`, -36, -86, '#ffdc38', '#080909', 10);
    }

    g.restore();
  }

  function drawScreenMudSplat(g, mud, nowMs) {
    if (!mud || nowMs < mud.impact_time_ms) return;
    const age = (nowMs - mud.impact_time_ms) / 1000;
    const cleanRatio = Number(mud.clean_ratio || 0);
    if (age > (mud.linger_sec || 45) || cleanRatio >= 1) return;

    const remain = Math.max(0.15, 1 - cleanRatio * 0.85);
    const cx = 240, cy = 128;
    const rx = 74 * remain, ry = 52 * remain;
    g.save();
    g.globalAlpha = Math.min(1, remain + 0.1);
    // 重力向下挂壁流淌的黏液流痕与尾部下坠水滴
    for (let i = -4; i <= 4; i++) {
      const dx = i * 13 * remain;
      const len = (22 + ((i * i * 7) % 34)) * Math.min(1, age * 1.2) * remain;
      box(g, '#3e2115', cx + dx - 3, cy + ry * 0.4, 6, len);
      ellipse(g, '#24120b', cx + dx, cy + ry * 0.4 + len, 4.5, 5.5);
      // 断开下坠的独立小泥滴
      const dropP = ((age * 0.95 + Math.abs(i) * 0.23) % 1);
      ellipse(g, '#633b25', cx + dx, cy + ry * 0.4 + len + dropP * 42, 3, 4.2);
    }
    ellipse(g, '#24120b', cx, cy + 4, rx * 1.05, ry * 1.05);
    ellipse(g, '#3e2115', cx, cy, rx * 0.96, ry * 0.96);
    ellipse(g, '#633b25', cx - 3, cy - 3, rx * 0.82, ry * 0.80);
    ellipse(g, '#8f5834', cx - 10, cy - 8, rx * 0.52, ry * 0.46);
    ellipse(g, '#c48d56', cx - 18, cy - 14, rx * 0.25, ry * 0.16);
    g.restore();
  }

  function desk(g, t, model) {
    const { since, working, strikeState } = model;
    room(g, t, working);

    if (strikeState && strikeState.state && !['OFFICE_IDLE', 'OFFICE_WORK'].includes(strikeState.state)) {
      const st = strikeState.state;
      const nowMs = strikeState.now_ms || Date.now();
      const cross = strikeState.cross;
      if (st === 'LEAVING') {
        const elapsed = nowMs - strikeState.since;
        const sighMs = strikeState.config?.OFFICE_SIGH_MS || 420;
        if (elapsed < sighMs) {
          person(g, 251, 188, t, 'sigh', false, false);
        } else if (cross && nowMs < cross.end) {
          const p = clamp((nowMs - strikeState.since - sighMs) / Math.max(1, cross.end - strikeState.since - sighMs));
          person(g, mix(251, 495, p), mix(188, 212, p), t, 'walk', false, true);
        }
      } else if (st === 'RETURNING' || st === 'BATH_RETURN') {
        if (cross && nowMs >= cross.start) {
          const p = clamp((nowMs - cross.start) / Math.max(1, cross.arrive - cross.start));
          const x = mix(495, 290, ease(p));
          g.save();
          g.translate(x * 2, 0);
          g.scale(-1, 1);
          person(g, x, 205, t, 'walk', false, false);
          g.restore();
        }
      } else if (st === 'SCRUBBING' || st === 'CLEAN_DONE') {
        drawDeskScrubbing(g, 295, 212, t, strikeState, nowMs);
      }
      if (strikeState.mud) {
        drawScreenMudSplat(g, strikeState.mud, nowMs);
      }
      textWithOutline(g, `MODE: ${st}`, 355, 251, '#fde047', '#1f2134', 8);
      return;
    }

    const going = since >= -1430 && since < 30;
    const carrying = since >= 30 && since < 1280;
    const sip = since >= 1280 && since < 2120;

    if (going) {
      const x = mix(251, 422, ease((since + 1420) / 1120));
      person(g, x, mix(188, 222, ease((since + 1420) / 1120)), t, since < -240 ? 'walk' : 'receive', working);
      if (since >= -120) cup(g, mix(499, 453, ease((since + 120) / 150)), 193, 0.8, t, 0.45, true);
    } else if (carrying) {
      const progress = ease((since - 80) / 1200);
      const x = mix(422, 251, progress);
      const y = mix(222, 188, progress);
      g.save();
      g.translate(x * 2, 0);
      g.scale(-1, 1);
      person(g, x, y, t, 'walk', working);
      g.restore();
      cup(g, x - 25, y - 32, 0.8, t, 0.45, true);
    } else if (sip) {
      person(g, 251, 188, t, 'sip', working);
      g.save();
      g.translate(274, 143);
      g.rotate(-0.47 * ease((since - 1280) / 240));
      cup(g, 0, 0, 0.57, t, 0.45, true);
      g.restore();
    } else {
      person(g, 251, 188, t, 'back', working);
      if (since >= 2120) cup(g, 284, 147, 0.57, t, 0.45, true);
    }

    if (since >= 1520 && since < 2750) {
      box(g, '#ebc5a3', 278, 85, 54, 21);
      box(g, '#ebc5a3', 280, 105, 4, 4);
      textWithOutline(g, 'Thanks.', 283, 99, '#3a2430', '#ebc5a3', 10);
    }

    textWithOutline(g, working ? 'WORKING' : 'ON STANDBY', 389, 251, working ? '#a2dec3' : '#aa8b9b', '#1f2134', 8);
    box(g, working ? '#a2dec3' : '#9a788e', 380, 246, 4, 4);
  }

  return {
    clamp,
    ease,
    pour,
    holo,
    desk,
    liquidOutline: leftInside
  };
})();
