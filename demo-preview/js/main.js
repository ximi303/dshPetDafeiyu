/* ════════════════════════════════════════════════════════════
 * main.js — 事件循环（镜像固件 main：buttons→stats/animator/menus→overlay→sleep）
 *
 * · 按键：pointer 事件实现短按 / 长按 2s（与固件 input 判定参数一致）
 * · 连击：2 秒窗口计数，投喂 3 次「吃太饱」、打工 5 次「鱼鱼好累」
 * · 状态联动：双满星随机庆祝 / ≤2 星待机减速 / 0 值最慢发呆
 * · 倍速：1x/10x/60x 作用于衰减与休眠倒计时
 * ════════════════════════════════════════════════════════════ */

(() => {

  const LONG_PRESS_MS = 2000;      // 长按判定（与固件一致）
  const COMBO_WINDOW_MS = 2000;    // 连击窗口
  const COMBO_FEED = 3;            // 吃太饱所需连按
  const COMBO_WORK = 5;            // 鱼鱼好累所需连按

  let speed = 1;                   // 模拟倍速
  let overeatUntil = 0;            // 吃太饱锁定截止时间戳
  let tiredActive = false;         // 鱼鱼好累抗议中
  let celebrateTimer = null;

  const $ = id => document.getElementById(id);

  /* ════════ 按键系统（复刻固件 buttons：消抖/长按/连击） ════════ */

  const keys = {};                 // btnId -> { downMs, longFired, combo: {n, lastMs}, debounce }

  function bindKeys() {
    document.querySelectorAll('.key[data-btn]').forEach(btn => {
      const id = btn.dataset.btn;
      keys[id] = { downMs: 0, longFired: false, longTimer: null, combo: { n: 0, lastMs: 0 }, badge: null };

      btn.addEventListener('pointerdown', e => {
        e.preventDefault();
        const k = keys[id];
        const now = performance.now();
        if (now - k.debounce < 50) return;        // 30~50ms 消抖
        k.debounce = now;
        k.downMs = now;
        k.longFired = false;
        btn.classList.add('pressed');
        k.longTimer = setTimeout(() => {          // 长按 2s
          k.longFired = true;
          onLongPress(id);
        }, LONG_PRESS_MS);
      });

      const up = () => {
        const k = keys[id];
        if (!k.downMs) return;
        clearTimeout(k.longTimer);
        btn.classList.remove('pressed');
        if (!k.longFired) onShortPress(id);       // 未达长按 → 短按
        k.downMs = 0;
        k.longFired = false;
      };
      btn.addEventListener('pointerup', up);
      btn.addEventListener('pointerleave', up);
      btn.addEventListener('pointercancel', up);
    });
  }

  /* 连击计数（窗口 2s），返回当前连击数；附带键帽角标 */
  function combo(id, btnEl) {
    const k = keys[id];
    const now = performance.now();
    if (now - k.combo.lastMs > COMBO_WINDOW_MS) k.combo.n = 0;
    k.combo.lastMs = now;
    k.combo.n++;
    if (k.combo.n >= 2) {
      if (!k.badge) {
        k.badge = document.createElement('span');
        k.badge.className = 'combo-badge';
        btnEl.appendChild(k.badge);
      }
      k.badge.textContent = k.combo.n;
      setTimeout(() => { if (k.badge) { k.badge.remove(); k.badge = null; } }, COMBO_WINDOW_MS);
    }
    return k.combo.n;
  }
  function comboReset(id) { keys[id].combo.n = 0; }

  /* ════════ 短按路由 ════════ */

  function onShortPress(id) {
    if (sleepCtl.poke()) return;                   // 任意键唤醒；唤醒的那一次不触发互动

    if (menus.isOpen()) { menus.handleButton(); return; }   // 页面内短按 = 返回

    const btnEl = document.querySelector(`.key[data-btn="${id}"]`);

    if (id === 'feed') {
      /* 彩蛋①：连按 3 次 → 吃太饱 */
      if (combo('feed', btnEl) >= COMBO_FEED) {
        comboReset('feed');
        triggerOvereat();
        return;
      }
      if (performance.now() < overeatUntil) {
        overlay.showToast('吃太饱啦！摸鱼消消食', 'bad');
        return;                                    // 锁定期白饭不再上涨
      }
      if (stats.feed()) {
        animator.requestPool('feed');
        overlay.showToast('白饭+1', 'gold');
      }
    }

    else if (id === 'play') {
      stats.slack();
      animator.requestPool('slack');
      overlay.showToast('摸鱼开心', 'cyan');
    }

    else if (id === 'work') {
      /* 彩蛋②：连按 5 次 → 鱼鱼好累 */
      if (combo('work', btnEl) >= COMBO_WORK) {
        comboReset('work');
        triggerTired();
        return;
      }
      if (tiredActive) {
        overlay.showToast('鱼鱼好累，要摸鱼休息', 'bad');
        return;
      }
      stats.work();
      animator.requestPool('work');
      overlay.showToast('Token+10', 'bad');
    }

    else if (id === 'pet') {
      stats.pet();
      animator.requestPool('pet');
      overlay.showToast('贴贴~', 'cyan');
    }

    applyStateLinkage();
  }

  /* ════════ 长按路由（各键二级功能） ════════ */

  function onLongPress(id) {
    sleepCtl.poke();
    if (menus.isOpen()) { menus.handleButton(); return; }

    if (id === 'feed')      openMenu('Status');
    else if (id === 'play') {
      const name = stats.nextSkin();
      animator.returnIdle();
      /* 0 值时按需求保持最慢发呆动画，皮肤要等喂食后才显示——提示注明，避免以为没生效 */
      const zero = stats.starsRice() === 0 && stats.starsMood() === 0;
      overlay.showToast(zero ? `皮肤：${name}（喂食后生效）` : `皮肤：${name}`, 'cyan');
    }
    else if (id === 'work') openMenu('Stats');
    else if (id === 'pet')  openMenu('Settings');
  }

  /* 页面与动画互斥：打开页面 → 暂停视频与衰减；关闭 → 恢复 */
  function openMenu(page) {
    const video = $('pet-video');
    video.pause();
    stats.pauseDecay(true);
    menus.open(page, () => {
      stats.pauseDecay(false);
      animator.returnIdle();
    });
  }

  /* ════════ 彩蛋触发 ════════ */

  function triggerOvereat() {
    overeatUntil = performance.now() + 10000;      // 锁 10s
    stats.setOvereat(true);
    animator.requestPool('overeat');
    overlay.showToast('吃太饱啦！摸鱼消消食', 'gold');
    setTimeout(() => stats.setOvereat(false), 10000);
  }

  function triggerTired() {
    tiredActive = true;
    animator.requestPool('tired', { onDone: () => { tiredActive = false; } });
    overlay.showToast('鱼鱼好累，要摸鱼休息', 'bad');
  }

  /* ════════ 状态联动（满星庆祝 / 减速 / 发呆） ════════ */

  function applyStateLinkage() {
    const r = stats.starsRice(), m = stats.starsMood();

    if (r === 0 && m === 0) {
      animator.setIdleSpeed(0.25);                 // 0 值：最慢发呆
      /* 只在待机中才切发呆池：正在播互动/彩蛋时不能打断 */
      if (animator.state().pool === 'idle') animator.requestPool('empty');
      return;
    }
    if (r <= 4 || m <= 4) {
      animator.setIdleSpeed(0.5);                  // 2 星及以下：无精打采
      return;
    }
    animator.setIdleSpeed(1);

    /* 双 5 星：随机庆祝小动作（防抖：互动动画播放中不排） */
    if (r === 10 && m === 10 && animator.state().pool === 'idle' && !celebrateTimer) {
      celebrateTimer = setTimeout(() => {
        celebrateTimer = null;
        if (animator.state().pool === 'idle' && !menus.isOpen()) {
          animator.requestPool('celebrate');
        }
      }, 8000 + Math.random() * 15000);
    }
  }

  /* ════════ 主循环 ════════
   * 数值时钟用 setInterval 驱动：后台标签页 rAF 会被节流到停止，
   * 而衰减/休眠必须像固件一样持续走（这也是 demo 要验证的行为）。
   * rAF 只负责调试面板刷新（画面可见时才需要）。 */

  let lastT = performance.now();

  function clockTick() {
    const now = performance.now();
    const dtSec = Math.min((now - lastT) / 1000, 2);     // 防长间隔大跳
    lastT = now;
    stats.tick(dtSec, speed);
    sleepCtl.tick(dtSec, speed);
  }

  function loop() {
    renderDebug();
    requestAnimationFrame(loop);
  }

  /* 屏幕亮度（模拟固件 LEDC 背光调光：暗/中/亮） */
  function applyBrightness() {
    const bri = [0.55, 0.8, 1][stats.settings().brightness] ?? 1;
    $('screen').style.setProperty('--bri', bri);
  }

  /* ════════ 调试面板 ════════ */

  function renderDebug() {
    const a = animator.state();
    const poolNames = {
      idle: '待机', feed: '投喂', slack: '摸鱼', work: '打工', pet: '贴贴',
      overeat: '彩蛋·吃太饱', tired: '彩蛋·鱼鱼好累',
      lowMood: '联动·无精打采', empty: '联动·发呆', celebrate: '庆祝',
    };
    const nextDecay = Math.max(0, Math.ceil((1 - stats.decayProgress()) * 30 / speed));
    const r = stats.starsRice(), m = stats.starsMood();
    const moodState = (r === 0 && m === 0) ? '发呆(0.25x)'
                    : (r <= 4 || m <= 4) ? '无精打采(0.5x)'
                    : (r === 10 && m === 10) ? '满星庆祝待命' : '正常(1x)';
    $('debug-panel').innerHTML =
      `动画池    <b>${poolNames[a.pool] || a.pool}</b>\n` +
      `当前段    ${a.pack}\n` +
      `播放速率  <b>${a.rate}x</b>\n` +
      `白饭/心情 <b>${stats.starsRice()}/10 · ${stats.starsMood()}/10</b> 档\n` +
      `联动状态  ${moodState}\n` +
      `Token     <b>${stats.tokens()}</b> · 称号 ${stats.title() || '无'}\n` +
      `下次衰减  <span class="warn">${nextDecay}s</span>（${speed}× 速率）\n` +
      `休眠      ${sleepCtl.isSleeping() ? '<span class="warn">💤 休眠中</span>' : '清醒'}`;
  }

  /* ════════ 面板控件 ════════ */

  function bindPanel() {
    $('speed-group').querySelectorAll('.speed-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.speed-btn[data-speed]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        speed = Number(btn.dataset.speed);
      });
    });

    $('btn-reset').addEventListener('click', () => {
      if (!confirm('重置全部养成数据？')) return;
      stats.reset();
      overlay.refresh();
      if (sleepCtl.isSleeping()) sleepCtl.poke();   // 重置后顺手唤醒
      animator.returnIdle();
      overlay.showToast('存档已重置', 'cyan');
    });

    $('btn-wake-test').addEventListener('click', () => sleepCtl.forceSleep());

    /* 点击屏幕也能唤醒（对应固件任意键唤醒） */
    $('screen').addEventListener('pointerdown', () => sleepCtl.poke());
  }

  /* ════════ 启动 ════════ */

  function begin() {
    stats.begin();
    overlay.begin();
    menus.begin();
    sleepCtl.begin();
    animator.begin($('pet-video'));
    bindKeys();
    bindPanel();

    /* stats → overlay / 联动 */
    stats.on('change', () => { overlay.refresh(); applyStateLinkage(); });
    stats.on('setting', ({ key }) => { if (key === 'brightness') applyBrightness(); });
    animator.setIdleHook(() => applyStateLinkage());     // 回落待机后重评估
    applyBrightness();
    stats.on('milestone', t => {
      animator.requestPool('celebrate', { priority: true });   // 排到当前互动段之后播，不被覆盖
      overlay.showToast(`🎉 解锁称号：${t.name}`, 'gold');
    });
    sleepCtl.setWakeHandler(() => animator.returnIdle());

    applyStateLinkage();
    renderDebug();
    setInterval(clockTick, 250);                       // 数值/休眠时钟
    requestAnimationFrame(loop);                        // 调试面板刷新
  }

  document.addEventListener('DOMContentLoaded', begin);

})();
