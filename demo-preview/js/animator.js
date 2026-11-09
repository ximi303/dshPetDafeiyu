/* ════════════════════════════════════════════════════════════
 * animator.js — 分池抽签动画调度（镜像固件 animator 重构方案）
 *
 * · 待机池按皮肤循环播放（loop），速度随状态联动：
 *     正常 1x / 2 星以下无精打采 0.5x / 0 值发呆 0.25x
 * · 互动/彩蛋池：loop=false，随机抽一段（不与上一段重复），
 *   播完（ended）自动回落待机池——与固件 requestPool 行为一致
 * · 彩蛋段可带 speed（吃太饱 1.5x 加速）与 holdMs（鱼鱼好累循环 10s）
 * ════════════════════════════════════════════════════════════ */

const animator = (() => {

  let video = null;
  let curPool = 'idle';       // 当前池：idle / feed / slack / work / pet / easter / lowMood / empty / celebrate
  let curPackPath = '';
  let idleSpeed = 1;          // 待机状态联动速度
  let holdTimer = null;
  let onReturnIdle = null;    // 彩蛋/互动播完回落时回调（供 main 恢复状态）
  let onIdleHook = null;      // 每次回落到待机后的钩子（供 main 重新评估状态联动）
  let pendingPool = null;     // 排队中的高优先级池（里程碑庆祝等）
  let missingShown = false;

  function begin(el) {
    video = el;
    video.addEventListener('ended', onEnded);
    video.addEventListener('error', () => showMissing());
    /* 自动播放兜底：就绪后仍是暂停态就重播；用户首次触碰也补一次 */
    video.addEventListener('canplay', () => { if (video.paused) resume(); });
    document.addEventListener('pointerdown', () => { if (video.paused) resume(); }, { once: true });
    playIdle();
  }

  function resume() {
    const pr = video.play();
    if (pr && pr.catch) pr.catch(() => {});
  }

  function pickPack(packs) {
    if (packs.length === 1) return packs[0];
    let p = packs[Math.floor(Math.random() * packs.length)];
    let guard = 0;
    while (p === curPackPath && guard++ < 4) {
      p = packs[Math.floor(Math.random() * packs.length)];
    }
    return p;
  }

  function playPack(path, { rate = 1, loop = false } = {}) {
    curPackPath = path;
    video.loop = loop;
    const src = WEBM_BASE + path;
    if (!video.src.endsWith(src)) video.src = src;
    video.playbackRate = rate;
    const pr = video.play();
    if (pr && pr.catch) pr.catch(() => {});     // 自动播放策略兜底（已 muted）
  }

  /* 待机池：按当前皮肤循环 */
  function playIdle() {
    clearTimeout(holdTimer);
    curPool = 'idle';
    const skin = MAPPING.idle.skins[stats.skin()] || MAPPING.idle.skins[0];
    playPack(pickPack(skin.packs), { rate: idleSpeed, loop: true });
    onIdleHook && onIdleHook();       // 回落待机后让 main 重评估联动（如 0 值切发呆）
  }

  /* 请求互动/彩蛋/联动池：该段播完自动回落 idle
   * priority=true：若正在播其它非待机段，排队到该段播完再播（里程碑庆祝用），
   * 避免「打工第 10 次 → 解锁称号庆祝」被同一次按键的打工动画盖掉 */
  function requestPool(key, { onDone, priority } = {}) {
    const pool = MAPPING[key];
    if (!pool) return;
    if (priority && curPool !== 'idle') {
      pendingPool = { key, onDone };
      return;
    }
    curPool = key;
    onReturnIdle = onDone || null;
    playPack(pickPack(pool.packs), {
      rate: pool.speed || 1,
      loop: pool.loop === true,        // empty 发呆池循环；互动池播完靠 ended 回落
    });
  }

  function onEnded() {
    if (curPool === 'idle') {
      // 待机段理论上 loop 不会 ended；保险起见重播
      playIdle();
      return;
    }
    /* 彩蛋「鱼鱼好累」：循环播放保持抗议状态，holdMs 后由计时器回落 */
    const pool = MAPPING[curPool];
    if (pool && pool.holdMs) {
      video.loop = true;
      const done = onReturnIdle;
      holdTimer = setTimeout(() => {
        const cb = done;
        onReturnIdle = null;
        nextAfterSegment();
        cb && cb(curPool);
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

  /* 待机皮肤切换（长按摸鱼键） */
  function setSkin(idx) {
    stats.setSkinIdx(idx);
    if (curPool === 'idle') playIdle();
  }

  /* 状态联动速度（stats 星级变化时由 main 调用） */
  function setIdleSpeed(x) {
    idleSpeed = x;
    if (curPool === 'idle') video.playbackRate = x;
  }

  /* 素材缺失降级提示 */
  function showMissing() {
    if (missingShown) return;
    missingShown = true;
    const bar = document.createElement('div');
    bar.className = 'asset-missing';
    bar.textContent = '⚠ webm 素材缺失：请先准备 ../assets/source-webm/ 下的西米素材';
    document.getElementById('screen').appendChild(bar);
  }

  /* 调试面板查询 */
  function state() {
    return { pool: curPool, pack: curPackPath, rate: video ? video.playbackRate : 1 };
  }

  return { begin, requestPool, playIdle, returnIdle, setSkin, setIdleSpeed, state,
           setIdleHook: fn => { onIdleHook = fn; } };
})();
