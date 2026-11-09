/* ════════════════════════════════════════════════════════════
 * animator.js — 分池抽签动画调度（镜像固件 animator 重构方案）
 *
 * · 待机池按皮肤循环播放（loop），速度随状态联动：
 *     正常 1x / 2 星以下无精打采 0.5x / 0 值发呆 0.25x
 * · 互动/彩蛋池：loop=false，随机抽一段（不与上一段重复），
 *   播完（ended）自动回落待机池——与固件 requestPool 行为一致
 * · 彩蛋段可带 speed（吃太饱 1.5x 加速）与 holdMs（鱼鱼好累循环 10s）
 *
 * 素材路径健壮性（浏览器环境比固件复杂，这里做了三层兜底）：
 *   1. 多候选根路径自动探测：file:// 双击、http:// 根在项目根、
 *      http:// 根在 demo-preview、把 demo 拷到别处 —— 都能找到素材
 *   2. 单段加载失败只跳过该段并换同池其它段，不再一失败就弹全局「素材缺失」
 *   3. 所有候选根都探测失败才降级：画一个占位鱼 + 修复指引，交互仍可玩
 * ════════════════════════════════════════════════════════════ */

const animator = (() => {

  /* 候选素材根目录（按顺序探测，第一个能加载成功的胜出） */
  const WEBM_ROOTS = [
    '../assets/source-webm/',      // 标准：项目根/demo-preview/index.html（file:// 与 http 都适用）
    '/assets/source-webm/',        // http server 根正好在项目根（绝对路径）
    'assets/source-webm/',         // 页面位于站点根一级目录时
    '../../assets/source-webm/',   // demo 被放进更深一层目录
    './assets/source-webm/',       // 把 assets 拷进 demo-preview 里
  ];

  const PROBE_TIMEOUT_MS = 2500;   // 单根探测超时（有些浏览器失败不触发 error）
  const CUSTOM_ROOT_KEY = 'feiyu-demo-asset-root';   // 用户手动指定的素材根（降级页可填）

  /* 用户手动指定过素材根就优先用它（支持 ?assets=xxx 一次性注入） */
  function customRoot() {
    const q = new URLSearchParams(location.search).get('assets');
    if (q) {
      try { localStorage.setItem(CUSTOM_ROOT_KEY, q); } catch (e) {}
      return q;
    }
    try { return localStorage.getItem(CUSTOM_ROOT_KEY) || ''; } catch (e) { return ''; }
  }

  function roots() {
    const c = customRoot();
    return c ? [c].concat(WEBM_ROOTS) : WEBM_ROOTS.slice();
  }

  let video = null;
  let root = null;             // 探测成功的素材根，null = 未确定
  let probing = false;
  let curPool = 'idle';
  let curPackPath = '';
  let idleSpeed = 1;
  let holdTimer = null;
  let onReturnIdle = null;
  let onIdleHook = null;
  let pendingPool = null;

  const badPacks = new Set();  // 已知加载失败的段，抽签时跳过
  let failStreak = 0;          // 连续失败次数
  let degraded = false;        // 是否已进入降级占位模式

  /* ──────────── 启动与根路径探测 ──────────── */

  function begin(el) {
    video = el;
    video.addEventListener('ended', onEnded);
    video.addEventListener('error', onMediaError);
    video.addEventListener('loadeddata', () => { failStreak = 0; });   // 成功播上才清零失败计数
    video.addEventListener('canplay', () => { if (video.paused && root) resume(); });
    document.addEventListener('pointerdown', () => { if (video.paused && root) resume(); }, { once: true });

    showLoading();
    probeRoot();
  }

  function probeRoot() {
    probing = true;
    let i = 0;
    const probePath = MAPPING.idle.skins[0].packs[0];    // 用待机首段探测
    const pv = document.createElement('video');
    pv.muted = true;
    pv.preload = 'metadata';

    let timer = null;

    const list = roots();

    const tryNext = () => {
      clearTimeout(timer);
      if (i >= list.length) {
        probing = false;
        degrade('所有候选路径都加载不到 webm 素材');
        return;
      }
      const cand = list[i++];
      timer = setTimeout(() => { pv.onerror = pv.onloadedmetadata = null; tryNext(); }, PROBE_TIMEOUT_MS);

      pv.onloadedmetadata = () => {
        clearTimeout(timer);
        pv.onerror = pv.onloadedmetadata = null;
        root = cand;
        probing = false;
        hideLoading();
        console.info('[animator] 素材根路径：' + cand);
        playIdle();
      };
      pv.onerror = () => { pv.onerror = pv.onloadedmetadata = null; tryNext(); };
      pv.src = toUrl(cand + probePath);
    };
    tryNext();
  }

  /* 相对路径 → 绝对 URL（中文文件名显式编码，避免个别浏览器的歧义） */
  function toUrl(relPath) {
    try {
      return new URL(encodeURI(relPath), location.href).href;
    } catch (e) {
      return encodeURI(relPath);
    }
  }

  /* ──────────── 播放核心 ──────────── */

  function resume() {
    const pr = video.play();
    if (pr && pr.catch) pr.catch(() => {});
  }

  function pickPack(packs) {
    /* 跳过已知坏段；全坏则返回 null */
    const alive = packs.filter(p => !badPacks.has(p));
    if (alive.length === 0) return null;
    if (alive.length === 1) return alive[0];
    let p = alive[Math.floor(Math.random() * alive.length)];
    let guard = 0;
    while (p === curPackPath && guard++ < 6) {
      p = alive[Math.floor(Math.random() * alive.length)];
    }
    return p;
  }

  function playPack(path, { rate = 1, loop = false } = {}) {
    if (!root || !path) return false;
    curPackPath = path;
    video.loop = loop;
    const url = toUrl(root + path);
    if (video.src !== url) video.src = url;   // 用解析后的绝对 URL 比较，避免重复加载同一段
    video.playbackRate = rate;
    resume();
    return true;
  }

  /* 待机池：按当前皮肤循环（当前皮肤段坏了就退到其它皮肤，全坏才降级） */
  function playIdle() {
    clearTimeout(holdTimer);
    curPool = 'idle';
    const skins = MAPPING.idle.skins;
    let path = pickPack((skins[stats.skin()] || skins[0]).packs);
    if (!path) {
      for (const s of skins) { path = pickPack(s.packs); if (path) break; }
    }
    if (!path) { degrade('待机动画段全部加载失败'); return; }
    if (!playPack(path, { rate: idleSpeed, loop: true })) return;
    onIdleHook && onIdleHook();
  }

  /* 请求互动/彩蛋/联动池：该段播完自动回落 idle
   * priority=true：若正在播其它非待机段，排队到该段播完再播（里程碑庆祝用） */
  function requestPool(key, { onDone, priority } = {}) {
    const pool = MAPPING[key];
    if (!pool) return;
    if (priority && curPool !== 'idle') {
      pendingPool = { key, onDone };
      return;
    }
    const path = pickPack(pool.packs);
    if (!path) {                       // 该池全部段都坏了 → 保持当前状态，不黑屏
      curPool = key;
      onReturnIdle = onDone || null;
      setTimeout(() => { if (curPool === key) { onReturnIdle = null; playIdle(); } }, 600);
      return;
    }
    curPool = key;
    onReturnIdle = onDone || null;
    playPack(path, { rate: pool.speed || 1, loop: pool.loop === true });
  }

  function onEnded() {
    if (curPool === 'idle') { playIdle(); return; }

    const pool = MAPPING[curPool];
    if (pool && pool.holdMs) {        // 鱼鱼好累：循环抗议 holdMs 后回落
      video.loop = true;
      const done = onReturnIdle;
      holdTimer = setTimeout(() => {
        onReturnIdle = null;
        nextAfterSegment();
        done && done(curPool);
      }, pool.holdMs);
      return;
    }
    const done = onReturnIdle;
    const wasPool = curPool;
    onReturnIdle = null;
    nextAfterSegment();
    done && done(wasPool);
  }

  /* 一段播完后的去向：有排队的高优先级池就先播它，否则回落待机 */
  function nextAfterSegment() {
    if (pendingPool) {
      const p = pendingPool;
      pendingPool = null;
      requestPool(p.key, { onDone: p.onDone });
      return;
    }
    playIdle();
  }

  /* 手动强制回落待机（长按页面互斥 / 休眠唤醒用），丢弃排队中的池 */
  function returnIdle() {
    clearTimeout(holdTimer);
    pendingPool = null;
    onReturnIdle = null;
    playIdle();
  }

  /* ──────────── 加载失败处理 ──────────── */

  function onMediaError() {
    /* error 事件可能在切段瞬间由上一次请求触发，延迟确认当前 src 确实坏了 */
    const pack = curPackPath;
    const poolKey = curPool;
    setTimeout(() => {
      if (!video.error) return;              // 只是旧请求的残留错误，忽略
      if (pack) badPacks.add(pack);
      failStreak++;

      if (failStreak >= 3 || !root) {
        degrade('连续 ' + failStreak + ' 段 webm 加载失败');
        return;
      }
      console.warn('[animator] 段加载失败，跳过：' + pack);

      /* 换同池的其它段；同池全坏就回落待机 */
      const pool = MAPPING[poolKey];
      if (pool && poolKey !== 'idle') {
        const alt = pickPack(pool.packs);
        if (alt && playPack(alt, { rate: pool.speed || 1, loop: pool.loop === true })) return;
      }
      playIdle();
    }, 60);
  }

  function maybeDegrade() {
    if (badPacks.size >= 3) degrade('可用段不足');
  }

  /* ──────────── 占位与降级 ──────────── */

  function showLoading() {
    const screen = document.getElementById('screen');
    if (!screen || screen.querySelector('.asset-loading')) return;
    const el = document.createElement('div');
    el.className = 'asset-loading';
    el.innerHTML = '<div class="loading-fish">🐟</div><div class="loading-text">素材加载中…</div>';
    screen.appendChild(el);
  }

  function hideLoading() {
    const el = document.querySelector('.asset-loading');
    el && el.remove();
  }

  /* 所有候选路径都失败：显示占位鱼 + 修复指引 + 手动指定素材路径，交互/数值仍可继续体验 */
  function degrade(reason) {
    if (degraded) return;
    degraded = true;
    hideLoading();

    const screen = document.getElementById('screen');
    if (!screen) return;

    const box = document.createElement('div');
    box.className = 'asset-fallback';
    box.innerHTML =
      '<div class="fallback-fish">🐳</div>' +
      '<div class="fallback-title">动画素材未加载</div>' +
      '<div class="fallback-msg">' + reason + '</div>' +
      '<div class="fallback-hint">' +
        '已尝试：' + roots().slice(0, 3).map(r => '<code>' + r + '</code>').join(' · ') +
          (roots().length > 3 ? ' 等 ' + roots().length + ' 个' : '') + '<br>' +
        '① 确认 <code>assets/source-webm/</code> 存在（106 段 webm）<br>' +
        '② 本地服务器必须从 <b>项目根</b> 启动：<code>tools/start-demo.ps1</code><br>' +
        '&nbsp;&nbsp;&nbsp;（<b>不要</b> cd 进 demo-preview 再 http.server，会找不到 ../assets）' +
      '</div>' +
      '<div class="fallback-path">' +
        '<input id="asset-path-input" class="asset-path-input" spellcheck="false" ' +
          'placeholder="或在这里填素材目录，如 E:\\...\\assets\\source-webm">' +
        '<button id="asset-path-apply" class="asset-path-btn">用这个路径</button>' +
      '</div>' +
      '<div class="fallback-reset"><a href="#" id="asset-path-reset">清除自定义路径，恢复自动探测</a></div>' +
      '<div class="fallback-tip">按键与数值逻辑仍可正常体验（无动画）</div>';
    screen.appendChild(box);

    const input = box.querySelector('#asset-path-input');
    input.value = guessRoot();          // 先按当前页面位置猜一个，用户可直接点按钮
    box.querySelector('#asset-path-apply').addEventListener('click', () => {
      const fixed = normalizeRoot(input.value);
      if (!fixed) { input.classList.add('is-bad'); input.focus(); return; }
      try { localStorage.setItem(CUSTOM_ROOT_KEY, fixed); } catch (e) {}
      location.reload();
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') box.querySelector('#asset-path-apply').click();
    });
    box.querySelector('#asset-path-reset').addEventListener('click', e => {
      e.preventDefault();
      try { localStorage.removeItem(CUSTOM_ROOT_KEY); } catch (err) {}
      location.reload();
    });

    video.style.opacity = '0';
    console.warn('[animator] 降级为占位模式：' + reason);
  }

  /* 按当前页面位置猜素材根（file:///…/demo-preview/index.html → file:///…/assets/source-webm/） */
  function guessRoot() {
    try { return new URL('../assets/source-webm/', location.href).href; } catch (e) { return ''; }
  }

  /* 用户输入 → 可用根：Windows 路径转 file:///，补末尾斜杠 */
  function normalizeRoot(v) {
    let s = (v || '').trim().replace(/\\/g, '/');
    if (!s) return '';
    if (/^[a-zA-Z]:\//.test(s)) s = 'file:///' + s;          // E:/xxx → file:///E:/xxx
    if (/^(https?:|file:)\/\//i.test(s) || /^\.{0,2}\//.test(s)) {
      return s.endsWith('/') ? s : s + '/';
    }
    return '';
  }

  /* ──────────── 其它 ──────────── */

  function setSkin(idx) {
    stats.setSkinIdx(idx);
    if (curPool === 'idle') playIdle();
  }

  function setIdleSpeed(x) {
    idleSpeed = x;
    if (curPool === 'idle' && video) video.playbackRate = x;
  }

  function state() {
    return {
      pool: curPool,
      pack: curPackPath,
      rate: video ? video.playbackRate : 1,
      root: root || '',
      bad: badPacks.size,
      degraded,
    };
  }

  /* 某池是否还有可播的段（防止坏段池反复回落形成空转循环） */
  function canPlay(key) {
    const pool = MAPPING[key];
    if (!pool) return false;
    return pool.packs.some(p => !badPacks.has(p));
  }

  return {
    begin, requestPool, playIdle, returnIdle, setSkin, setIdleSpeed, state, canPlay,
    setIdleHook: fn => { onIdleHook = fn; },
  };
})();
