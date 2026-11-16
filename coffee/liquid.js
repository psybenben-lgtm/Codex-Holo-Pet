'use strict';

/**
 * 咖啡水体物理引擎 (CoffeeLiquid v4.0)
 * 采用原生左向壶嘴坐标系（无需镜像），原生支持 iPhone 陀螺仪与滑条倾倒。
 * 包含：Verlet 粒子流体模拟、碰撞检测、向左倾斜流出统计、以及深色咖啡水体渲染。
 */
class CoffeeLiquid {
  constructor(outline) {
    this.width = 220;
    this.height = 250;
    // 原生左向壶嘴多边形 (壶嘴在左 X~49..51, 把手在右 X~159)
    this.outline = outline || [
      [135, 74], [88, 74], [75, 78], [57, 78], [49, 72], [51, 77], [63, 87], [78, 90],
      [72, 109], [64, 127], [62, 147], [66, 162], [76, 174], [88, 178], [135, 178],
      [149, 172], [157, 160], [159, 145], [157, 127], [152, 112], [141, 92]
    ];
    this.field = new Float32Array(this.width * this.height * 3);
    this.edges = new Uint8Array(this.width * this.height);
    this.makeBoundary();

    // 用于 Metaball 渲染的离屏画布
    this.mask = document.createElement('canvas');
    this.mask.width = this.width;
    this.mask.height = this.height;
    this.paint = this.mask.getContext('2d', { willReadFrequently: true });

    // 粒子软核模糊贴图
    this.kernel = document.createElement('canvas');
    this.kernel.width = this.kernel.height = 18;
    const k = this.kernel.getContext('2d');
    const fade = k.createRadialGradient(9, 9, 0, 9, 9, 9);
    fade.addColorStop(0, 'rgba(255,255,255,1)');
    fade.addColorStop(0.5, 'rgba(255,255,255,0.7)');
    fade.addColorStop(1, 'rgba(255,255,255,0)');
    k.fillStyle = fade;
    k.fillRect(0, 0, 18, 18);

    this.reset(0);
  }

  contains(x, y) {
    let inside = false;
    const points = this.outline;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const [ax, ay] = points[i], [bx, by] = points[j];
      if ((ay > y) !== (by > y) && x < (bx - ax) * (y - ay) / (by - ay) + ax) {
        inside = !inside;
      }
    }
    return inside;
  }

  makeBoundary() {
    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        let distance = Infinity, normalX = 0, normalY = 0, edge = 0;
        const inside = this.contains(x, y);
        for (let i = 0; i < this.outline.length; i++) {
          const [ax, ay] = this.outline[i], [bx, by] = this.outline[(i + 1) % this.outline.length];
          const dx = bx - ax, dy = by - ay, length = Math.hypot(dx, dy);
          const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (length * length)));
          const ex = x - ax - t * dx, ey = y - ay - t * dy, d = Math.hypot(ex, ey);
          if (d < distance) {
            distance = d;
            edge = i;
            normalX = d > 0.001 ? ex / d * (inside ? 1 : -1) : -dy / length;
            normalY = d > 0.001 ? ey / d * (inside ? 1 : -1) : dx / length;
          }
        }
        const index = y * this.width + x;
        this.field[index * 3] = (inside ? 1 : -1) * distance;
        this.field[index * 3 + 1] = normalX;
        this.field[index * 3 + 2] = normalY;
        this.edges[index] = edge;
      }
    }
  }

  reset(amount = 0) {
    this.particles = [];
    this.drops = [];
    this.elapsed = 0;
    this.total = 0;
    this.emitted = 0;

    const spacing = 3.8;
    // 初始粒子填充壶内（壶底 Y 从 175 向上排布）
    for (let row = 0, y = 175; y > 100; y -= spacing * 0.88, row++) {
      for (let x = 65 + (row % 2) * spacing / 2; x < 155; x += spacing) {
        const index = Math.round(y) * this.width + Math.round(x);
        if (this.field[index * 3] > 2.5) {
          this.particles.push({ x, y, vx: 0, vy: 0, px: x, py: y, out: false });
        }
      }
    }

    this.total = this.particles.length;
    // 满杯阈值：倒出约 68% 水体即可达到目标 80% 满杯，倾倒过程更畅快
    this.targetFull = Math.max(1, Math.round(this.total * 0.68));
    this.emitted = Math.min(this.targetFull, Math.round(this.targetFull * (amount / 0.8)));
    this.transferred = this.emitted;
    if (this.emitted > 0) {
      this.particles.splice(this.total - this.emitted);
    }
    this.amount = Math.min(0.8, (this.emitted / this.targetFull) * 0.8);
    this.transferAmount = this.amount;
    this.rate = 0;
  }

  collide(p, allowOut) {
    const x = Math.max(0, Math.min(this.width - 1, Math.round(p.x)));
    const y = Math.max(0, Math.min(this.height - 1, Math.round(p.y)));
    const index = y * this.width + x;
    const d = this.field[index * 3];

    // 壶嘴开口区域判定（放宽判定范围，X <= 58 且 Y 在 62..94，出水更顺畅灵敏）
    if ((this.edges[index] === 4 || (p.x <= 58 && p.y >= 62 && p.y <= 94)) && allowOut) {
      if (d < 0.25 || p.x < 53) {
        p.out = true;
        return;
      }
      return;
    }

    // 与壶壁碰撞排斥
    if (d < 1.4) {
      p.x += this.field[index * 3 + 1] * (1.4 - d);
      p.y += this.field[index * 3 + 2] * (1.4 - d);
    }
  }

  step(dt, gx, gy, allowOut) {
    const size = 4.0, diameter = 3.65, grid = new Map();

    // 1. 速度阻尼与重力加速度更新
    for (const p of this.particles) {
      p.px = p.x;
      p.py = p.y;
      p.vx = (p.vx + gx * dt) * 0.996;
      p.vy = (p.vy + gy * dt) * 0.996;
      const speed = Math.hypot(p.vx, p.vy);
      if (speed > 420) {
        p.vx *= 420 / speed;
        p.vy *= 420 / speed;
      }
      p.x += p.vx * dt;
      p.y += p.vy * dt;
    }

    // 2. 粒子间排斥与松弛（保持液体不可压缩性）
    for (let pass = 0; pass < 2; pass++) {
      grid.clear();
      this.particles.forEach((p, i) => {
        const key = Math.floor(p.x / size) + Math.floor(p.y / size) * 128;
        if (!grid.has(key)) grid.set(key, []);
        grid.get(key).push(i);
      });

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        const cx = Math.floor(p.x / size), cy = Math.floor(p.y / size);
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            for (const j of grid.get(cx + dx + (cy + dy) * 128) || []) {
              if (j <= i) continue;
              const q = this.particles[j];
              const vx = q.x - p.x, vy = q.y - p.y;
              const d = Math.hypot(vx, vy);
              if (d > 0.001 && d < diameter) {
                const push = (diameter - d) * 0.5;
                p.x -= vx / d * push;
                p.y -= vy / d * push;
                q.x += vx / d * push;
                q.y += vy / d * push;
              }
            }
          }
        }
        this.collide(p, allowOut);
      }
    }

    // 3. 统计脱离壶嘴的液滴，赋予强劲向左初速度形成清晰抛物线
    let escaped = 0;
    this.particles = this.particles.filter(p => {
      if (p.out) {
        // 从左向壶嘴喷出：给予充沛的向左水平冲量与微弱扬角，形成优雅抛物线
        this.drops.push({
          x: p.x,
          y: p.y,
          vx: -130 - Math.random() * 60,
          vy: -25 + Math.random() * 35,
          age: 0
        });
        escaped++;
        return false;
      }
      p.vx = (p.x - p.px) / dt * 0.992;
      p.vy = (p.y - p.py) / dt * 0.992;
      return true;
    });

    this.emitted += escaped;
    this.amount = Math.min(0.8, (this.emitted / this.targetFull) * 0.8);

    // 4. 自由飞行的喷落水滴更新（自然受重力加速，划出抛物线弧度）
    for (const p of this.drops) {
      p.vx += (gx * 0.45) * dt;
      p.vy += (Math.max(gy, 380)) * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.age += dt;
    }

    // 离开屏幕或寿命到达的水滴计入送达
    this.drops = this.drops.filter(p => {
      if (p.x < -15 || p.x > this.width + 15 || p.y > this.height + 15 || p.age > 1.8) {
        this.transferred++;
        return false;
      }
      return true;
    });
    this.transferAmount = Math.min(0.8, (this.transferred / this.targetFull) * 0.8);

    return escaped;
  }

  update(ms, gx, gy, allowOut) {
    this.elapsed += Math.min(ms, 40) / 1000;
    let escaped = 0;
    while (this.elapsed >= 1 / 120) {
      escaped += this.step(1 / 120, gx, gy, allowOut);
      this.elapsed -= 1 / 120;
    }
    const instantaneous = this.total ? (escaped / this.total) / (Math.max(ms, 1) / 1000) * 3 : 0;
    this.rate += (Math.min(1, instantaneous) - this.rate) * (1 - Math.exp(-ms / 100));
    return escaped;
  }

  draw(g) {
    const m = this.paint;
    m.clearRect(0, 0, this.width, this.height);

    // 绘制流体核
    for (const p of [...this.particles, ...this.drops]) {
      m.drawImage(this.kernel, p.x - 9, p.y - 9);
    }

    const image = m.getImageData(0, 0, this.width, this.height);
    const data = image.data;
    const alpha = new Uint8Array(this.width * this.height);
    for (let i = 0; i < alpha.length; i++) {
      alpha[i] = data[i * 4 + 3];
    }

    // 真实黑咖啡色阶调色板（纯黑带微暗琥珀与焦糖高光边缘）
    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        const index = y * this.width + x;
        const i = index * 4;
        const a = alpha[index];
        if (a < 140) {
          data[i + 3] = 0;
          continue;
        }

        // 阈值分割形成紧致的流体表面
        const opacity = Math.min(255, (a - 140) * 4);
        const isSurface = alpha[Math.max(0, index - this.width * 2)] < 165;
        const depth = Math.max(0, Math.min(1, (y - 85) / 95));

        if (isSurface) {
          // 液面浅金白奶泡高光，极其通透
          data[i] = 252;
          data[i + 1] = 232;
          data[i + 2] = 188;
          data[i + 3] = opacity;
        } else {
          // 浅摩卡/焦糖拿铁棕黄（明度大幅提升，上层焦糖金，底层柔和暖棕黄，投影清晰明亮）
          data[i] = Math.round(218 - depth * 48);
          data[i + 1] = Math.round(152 - depth * 38);
          data[i + 2] = Math.round(86 - depth * 22);
          data[i + 3] = opacity;
        }
      }
    }

    m.putImageData(image, 0, 0);
    g.drawImage(this.mask, 0, 0);
  }
}
