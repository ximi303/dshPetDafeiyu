/* ════════════════════════════════════════════════════════════
 * sleep.js — 5 分钟无操作低亮度休眠（镜像固件 sleep 行为）
 *
 * · 无操作 sleepAfterMs（5 分钟）后进入休眠：屏幕压暗
 * · 任意按键（含短按）唤醒；唤醒的那次按键不触发互动
 * · 倒计时受模拟倍速影响（60× 下约 5 秒可实际观察）
 * · 设置菜单「自动休眠」关闭后不进入休眠
 * ════════════════════════════════════════════════════════════ */

const sleepCtl = (() => {

  let idleSec = 0;
  let sleeping = false;
  let maskEl, screenEl;
  let onWake = null;             // 唤醒回调（供 main 恢复动画播放）

  function begin() {
    maskEl = document.getElementById('sleep-mask');
    screenEl = document.getElementById('screen');
    maskEl.hidden = true;
  }

  /* 每帧调用：dtSec 真实秒，speed 倍速 */
  function tick(dtSec, speed) {
    if (sleeping || !stats.settings().autoSleep) return;
    idleSec += dtSec * speed;
    if (idleSec * 1000 >= RULES.sleepAfterMs) enter();
  }

  /* 按键活动喂狗：重置无操作计时。
   * 返回 true 表示「这次操作是唤醒」——上层据此跳过本次互动
   * （与固件一致：唤醒的那一下只唤醒，不触发功能） */
  function poke() {
    idleSec = 0;
    if (sleeping) { wake(); return true; }
    return false;
  }

  function enter() {
    sleeping = true;
    idleSec = 0;
    screenEl.classList.add('sleeping');
    maskEl.hidden = false;
  }

  function wake() {
    sleeping = false;
    idleSec = 0;
    screenEl.classList.remove('sleeping');
    maskEl.hidden = true;
    onWake && onWake();
  }

  /* 测试按钮：立即休眠 */
  function forceSleep() {
    if (!sleeping) enter();
  }

  const isSleeping = () => sleeping;

  return { begin, tick, poke, forceSleep, isSleeping, setWakeHandler: fn => { onWake = fn; } };
})();
