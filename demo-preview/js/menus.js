/* ════════════════════════════════════════════════════════════
 * menus.js — 三个长按二级页面（镜像固件 menus 模块）
 *
 * · Status   状态详情页：当前星级 / 累计干饭碗数 / 累计 Token
 * · Stats    累计数据页：历史总 Token / 总干饭碗数 / 称号
 * · Settings 设置菜单：屏幕亮度（调节）、自动休眠（开关）、
 *            提示音效（本期置灰占位，音频硬件下期做）
 *
 * · 页面打开时暂停动画与衰减结算（互斥），退出恢复——
 *   提前在 demo 验证「页面下动画不刷掉 UI」的手感
 * · 页面内 4 键导航：任意短按 = 关闭返回（简化导航，菜单项用鼠标
 *   直接点；固件版可扩展为上下选择模式）
 * ════════════════════════════════════════════════════════════ */

const menus = (() => {

  let layer, pageEl;
  let cur = 'None';               // None | Status | Stats | Settings
  let onClose = null;             // 关闭回调（恢复动画/衰减）

  function begin() {
    layer = document.getElementById('menu-layer');
    pageEl = document.getElementById('menu-page');
    layer.hidden = true;
  }

  const isOpen = () => cur !== 'None';
  const current = () => cur;

  function open(page, onCloseCb) {
    cur = page;
    onClose = onCloseCb || null;
    layer.hidden = false;
    render();
  }

  function close() {
    if (cur === 'None') return;
    cur = 'None';
    layer.hidden = true;
    onClose && onClose();
    onClose = null;
  }

  /* 页面内任意短按关闭（长按 2s 计时器中断由 main 层处理） */
  function handleButton() {
    if (isOpen()) close();
  }

  /* ── 渲染 ── */
  function render() {
    if (cur === 'Status')   renderStatus();
    else if (cur === 'Stats') renderStats();
    else if (cur === 'Settings') renderSettings();
  }

  function starText(level) {                       // 0~10 半星档 → ★ 显示
    const full = Math.floor(level / 2), half = level % 2;
    const empty = 5 - full - (half ? 1 : 0);
    return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty) +
           '  ' + (level / 2).toFixed(level % 2 ? 1 : 0) + ' 星';
  }

  function renderStatus() {
    const r = stats.starsRice(), m = stats.starsMood();
    pageEl.innerHTML =
      '<div class="menu-title">📋 状态详情</div>' +
      '<div class="menu-row"><span class="k">🍚 白饭能量</span><span class="v" style="color:var(--gold)">' + starText(r) + '</span></div>' +
      '<div class="menu-row"><span class="k">🐟 摸鱼心情</span><span class="v" style="color:var(--cyan)">' + starText(m) + '</span></div>' +
      '<div class="menu-row"><span class="k">🍚 累计干饭</span><span class="v">' + stats.bowls() + ' 碗</span></div>' +
      '<div class="menu-row"><span class="k">⚡ 累计 Token</span><span class="v">' + stats.tokens() + '</span></div>' +
      '<div class="menu-foot">长按投喂键打开 · 任意短按返回</div>';
  }

  function renderStats() {
    pageEl.innerHTML =
      '<div class="menu-title">📈 累计数据</div>' +
      '<div class="menu-row"><span class="k">历史总 Token</span><span class="v">' + stats.tokens() + '</span></div>' +
      '<div class="menu-row"><span class="k">总干饭碗数</span><span class="v">' + stats.bowls() + '</span></div>' +
      '<div class="menu-row"><span class="k">当前称号</span><span class="v" style="color:var(--gold)">' + (stats.title() || '—— 未解锁 ——') + '</span></div>' +
      '<div class="menu-foot">里程碑：100 实习码鱼 · 500 摸鱼组长 · 1000 首席干饭官<br>长按打工键打开 · 任意短按返回</div>';
  }

  function renderSettings() {
    const st = stats.settings();
    const soundDisabled = true;                     // 本期音效硬件未实现
    pageEl.innerHTML =
      '<div class="menu-title">⚙ 系统设置</div>' +
      '<div class="menu-adjust"><span class="k">☀ 屏幕亮度</span>' +
      '<span><button class="speed-btn" data-act="bri-" style="padding:2px 14px">−</button>' +
      '<span class="adjust-val">' + ['暗', '中', '亮'][st.brightness] + '</span>' +
      '<button class="speed-btn" data-act="bri+" style="padding:2px 14px">＋</button></span></div>' +
      '<div class="menu-adjust"><span class="k">🌙 自动休眠</span>' +
      '<span><button class="speed-btn ' + (st.autoSleep ? 'active' : '') + '" data-act="sleep">' + (st.autoSleep ? '开' : '关') + '</button></span></div>' +
      '<div class="menu-adjust menu-item disabled"><span class="k">🔔 提示音效<span class="tag">下期硬件</span></span>' +
      '<span><button class="speed-btn active" disabled>开</button></span></div>' +
      '<div class="menu-foot">长按撸鱼键打开 · 点按项目调整 · 任意短按返回</div>';

    pageEl.querySelectorAll('[data-act]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();                        // 不触发页面关闭
        const act = btn.dataset.act;
        if (act === 'bri-') stats.setSetting('brightness', Math.max(0, st.brightness - 1));
        if (act === 'bri+') stats.setSetting('brightness', Math.min(2, st.brightness + 1));
        if (act === 'sleep') stats.setSetting('autoSleep', !stats.settings().autoSleep);
        render();
      });
    });
  }

  return { begin, open, close, current, isOpen, handleButton, render };
})();
