/* ════════════════════════════════════════════════════════════
 * stats.js — 数值系统（镜像固件 stats 模块）
 *
 * 口径（与固件计划一致）：
 *   白饭/心情 0~100，每 10 分 = 半星档（1 档），100 = 5 星满
 *   feed  = 白饭+10 心情+10           bowls+1（两边同涨半星）
 *   slack = 白饭不动 心情+10
 *   work  = 白饭-10 心情-10 Token+10（两边同跌半星）
 *   pet   =          心情+10
 *   衰减  = 每 30s（模拟 2h）白饭-10 心情-10，0 封底无惩罚
 *
 * localStorage 模拟 NVS：掉电（刷新）不丢数值；
 * 跨掉电时间差不补衰减（无 RTC 的取舍，与固件一致）。
 * ════════════════════════════════════════════════════════════ */

const stats = (() => {

  const SAVE_KEY = 'feiyu-demo-save-v1';

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  /* 内部状态 */
  let s = null;
  let decayAccumSec = 0;      // 衰减累计计时（模拟时间，秒）
  let overeatLock = false;    // 吃太饱彩蛋中：白饭封顶不涨

  function fresh() {
    return {
      rice: 50, mood: 50,
      tokens: 0, bowls: 0,
      skin: 0,
      unlockedTitle: '',                       // 已解锁的最高称号名
      settings: { brightness: 2, autoSleep: true, sound: false },  // brightness 0暗/1中/2亮
    };
  }

  function load() {
    try {
      const raw = localStorage.getItem(SAVE_KEY);
      if (raw) {
        const d = JSON.parse(raw);
        return { ...fresh(), ...d, settings: { ...fresh().settings, ...(d.settings || {}) } };
      }
    } catch (e) { /* 存档损坏则重置 */ }
    return fresh();
  }

  function save() {
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(s)); } catch (e) { /* 隐私模式忽略 */ }
  }

  /* ── 对外事件：数值/星级/里程碑/设置变化通知 ── */
  const listeners = { change: [], milestone: [], setting: [] };
  function on(evt, fn) { listeners[evt].push(fn); }
  function emit(evt, payload) { listeners[evt].forEach(fn => fn(payload)); }

  /* ── 通用增减 + 事件 ── */
  function apply(d) {
    const before = { riceStars: starsRice(), moodStars: starsMood() };
    if (!overeatLock || (d.rice ?? 0) <= 0) {
      s.rice = clamp(s.rice + (d.rice ?? 0), 0, 100);
    }
    s.mood = clamp(s.mood + (d.mood ?? 0), 0, 100);
    if (d.tokens) {
      s.tokens += d.tokens;
      checkMilestone();
    }
    if (d.bowls) s.bowls += d.bowls;
    save();

    if (before.riceStars !== starsRice() || before.moodStars !== starsMood()) {
      emit('change', { riceStars: starsRice(), moodStars: starsMood() });
    }
  }

  /* ── Token 里程碑：100/500/1000 ── */
  function checkMilestone() {
    let hit = null;
    for (const t of MAPPING.titles) {
      if (s.tokens >= t.at && titleRank(t.name) > titleRank(s.unlockedTitle)) {
        s.unlockedTitle = t.name;
        hit = t;
      }
    }
    if (hit) { save(); emit('milestone', hit); }
  }
  function titleRank(name) {
    return MAPPING.titles.findIndex(t => t.name === name);
  }

  /* ════════ 对外接口（与固件 stats.h 同名同义） ════════ */

  function begin() {
    s = load();
    decayAccumSec = 0;
    // 注意：跨刷新（模拟掉电）不按离线时长补衰减——与固件 NVS 取舍一致
  }

  /* 每帧调用；dtSec 为真实经过秒数，speed 为模拟倍速 */
  function tick(dtSec, speed) {
    if (!s || s._paused) return;
    decayAccumSec += dtSec * speed;
    const every = RULES.decay.everySec;                 // 模拟 2h
    while (decayAccumSec >= every) {
      decayAccumSec -= every;
      const before = { riceStars: starsRice(), moodStars: starsMood() };
      s.rice = clamp(s.rice + RULES.decay.rice, 0, 100);
      s.mood = clamp(s.mood + RULES.decay.mood, 0, 100);
      save();
      if (before.riceStars !== starsRice() || before.moodStars !== starsMood()) {
        emit('change', { riceStars: starsRice(), moodStars: starsMood() });
      }
      emit('decay');                                    // 供调试面板
    }
  }

  /* 四互动入口（彩蛋锁定时拒绝由 main 层决定，这里只做数值） */
  function feed()  { if (overeatLock) return false; apply({ ...RULES.feed,  bowls: 1 }); return true; }
  function slack() { apply(RULES.slack); return true; }
  function work()  { apply(RULES.work);  return true; }
  function pet()   { apply(RULES.pet);   return true; }

  /* 吃太饱彩蛋：期间白饭不再上涨 */
  function setOvereat(on) { overeatLock = on; }
  function isOvereat() { return overeatLock; }

  /* 查询 */
  const rice       = () => s.rice;
  const mood       = () => s.mood;
  const tokens     = () => s.tokens;
  const bowls      = () => s.bowls;
  const starsRice  = () => Math.round(s.rice / 10);     // 0~10 半星档
  const starsMood  = () => Math.round(s.mood / 10);
  const title      = () => s.unlockedTitle || '';
  const skin       = () => s.skin;
  const settings   = () => s.settings;
  const decayProgress = () => decayAccumSec / RULES.decay.everySec;   // 调试面板用

  /* 设置项（设置菜单用） */
  function setSetting(key, val) {
    s.settings[key] = val;
    save();
    emit('setting', { key, val });      // 亮度等需要立即作用到屏幕
  }

  /* 皮肤（长按摸鱼键循环切换） */
  function setSkinIdx(idx) {
    const n = MAPPING.idle.skins.length;
    s.skin = ((idx % n) + n) % n;
    save();
    return MAPPING.idle.skins[s.skin].name;
  }
  function nextSkin() { return setSkinIdx(s.skin + 1); }

  /* 页面互斥：进入长按页面时暂停衰减结算 */
  function pauseDecay(on) { s && (s._paused = on); }

  function reset() {
    s = fresh();
    decayAccumSec = 0;
    save();
    emit('change', { riceStars: starsRice(), moodStars: starsMood() });
  }

  return {
    begin, tick, feed, slack, work, pet,
    rice, mood, tokens, bowls, starsRice, starsMood, title,
    skin, nextSkin, setSkinIdx, settings, setSetting,
    setOvereat, isOvereat, pauseDecay, decayProgress,
    reset, on,
  };
})();
