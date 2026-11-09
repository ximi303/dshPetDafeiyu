/* ════════════════════════════════════════════════════════════
 * overlay.js — 状态栏星级绘制 + 1.5 秒飘字（镜像固件 overlay 模块）
 *
 * · 星级：5 星 × 半星制 10 档；仅档位变化时重绘 DOM
 * · 飘字：showToast(text, tone)，CSS 动画 1.5s 自动移除
 * ════════════════════════════════════════════════════════════ */

const overlay = (() => {

  const STAR_D = 'M12 2.6l2.9 5.9 6.5 1-4.7 4.6 1.1 6.5L12 17.5l-5.8 3.1 1.1-6.5L2.6 9.5l6.5-1z';

  /* 每颗星的 clipPath 用唯一 id：5 个 SVG 共用同一 id 时，
   * 浏览器只认文档里第一个，跨 SVG 引用会把裁剪区算错 */
  let clipSeq = 0;
  function starSvg() {
    const id = 'star-half-clip-' + (++clipSeq);
    return '<svg viewBox="0 0 24 24">' +
      '<path class="star-fill" d="' + STAR_D + '"/>' +
      '<clipPath id="' + id + '"><rect x="0" y="0" width="12" height="24"/></clipPath>' +
      '<path class="star-half" clip-path="url(#' + id + ')" d="' + STAR_D + '"/></svg>';
  }

  let elRice, elMood, elToastLayer;
  let lastRiceStars = -1, lastMoodStars = -1;

  function begin() {
    elRice = document.getElementById('stars-rice');
    elMood = document.getElementById('stars-mood');
    elToastLayer = document.getElementById('toast-layer');
    drawStars(elRice, stats.starsRice());
    drawStars(elMood, stats.starsMood());
    lastRiceStars = stats.starsRice();
    lastMoodStars = stats.starsMood();
  }

  function drawStars(container, level) {          // level: 0~10（半星为奇数档）
    container.innerHTML = '';
    for (let i = 0; i < 5; i++) {
      const div = document.createElement('div');
      div.className = 'star';
      const need = (i + 1) * 2;                   // 该星全亮所需档位：2/4/6/8/10
      if (level >= need) div.classList.add('full');
      else if (level >= need - 1) div.classList.add('half');
      else div.classList.add('empty');
      div.innerHTML = starSvg();
      container.appendChild(div);
    }
  }

  /* 数值变化回调（stats.on('change') → main 挂进来） */
  function refresh() {
    const r = stats.starsRice(), m = stats.starsMood();
    if (r !== lastRiceStars) { drawStars(elRice, r); lastRiceStars = r; }
    if (m !== lastMoodStars) { drawStars(elMood, m); lastMoodStars = m; }
  }

  /* 飘字：tone = '' | 'gold' | 'cyan' | 'bad' */
  function showToast(text, tone) {
    const t = document.createElement('div');
    t.className = 'toast' + (tone ? ' ' + tone : '');
    t.textContent = text;
    elToastLayer.appendChild(t);
    setTimeout(() => t.remove(), 1500);           // 与固件 1.5s 消失一致
  }

  return { begin, refresh, showToast };
})();
