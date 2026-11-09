/* ════════════════════════════════════════════════════════════
 * mapping.js — 动画映射数据（与固件 config.h 映射数组同构）
 *
 * 每个池 = 玩法动作 → 西米 webm 相对路径（相对项目根 assets/source-webm/）。
 * 段名已对照 assets/source-webm/ 实际文件逐一核实（2026-11-09）。
 * 换角色 / 换动画：只改本文件，固件侧对应 config.h 的映射数组。
 * ════════════════════════════════════════════════════════════ */

/* 素材根路径由 animator.js 的 WEBM_ROOTS 自动探测（file:// / http / 目录迁移都能命中），
 * 这里的 packs 一律写「分类/段名.webm」相对路径，不含根。 */

const MAPPING = {

  /* 待机池：皮肤可切换（长按摸鱼键循环） */
  idle: {
    skins: [
      { name: '发呆',   packs: ['待机/待机呼吸休闲.webm'] },
      { name: '吐泡泡', packs: ['随机-玩耍/鲸鱼吐泡泡特效.webm'] },
      { name: '晃尾巴', packs: ['转向/东张西望.webm'] },
    ],
  },

  /* 四个互动池（短按触发） */
  feed:  { label: '白饭+1',      toast: 'gold', packs: ['随机-吃什么/吃白饭.webm', '随机-吃什么/大口吃零食.webm'] },
  slack: { label: '摸鱼开心',    toast: 'cyan', packs: ['随机-玩耍/动物环绕.webm', '随机-玩耍/蝴蝶蜜蜂环绕头顶开花.webm'] },
  work:  { label: '打工烧Token', toast: 'bad',  packs: ['随机-小动作/写代码.webm', '事件-工作状态/工作状态-忙碌点按.webm'] },
  pet:   { label: '贴贴~',       toast: 'cyan', packs: ['随机-玩耍/轻快摇摆舞.webm', '随机-小动作/小幅度原地360度旋转展示.webm'] },

  /* 彩蛋池（连按触发，顶层键供 animator.requestPool 直接使用） */
  overeat: { toast: 'gold', packs: ['随机-小动作/小幅度原地360度旋转展示.webm'], speed: 1.5 },   // 吃太饱：加速转圈
  tired:   { toast: 'bad',  packs: ['移动/螃蟹走路.webm'],                    speed: 0.5, holdMs: 10000 }, // 鱼鱼好累：循环抗议 10s

  /* 状态联动池 */
  lowMood:   { packs: ['随机-小动作/哈欠连天.webm', '随机-小动作/打瞌睡被惊醒.webm'], speed: 0.5 },  // 2 星及以下：无精打采
  empty:     { packs: ['随机-小动作/原地小憩沉眠.webm'], speed: 0.25, loop: true },                   // 0 值：最慢发呆（循环，直到互动）
  celebrate: { packs: ['事件-工作状态/工作状态-雀跃庆祝.webm', '随机-玩耍/拆礼物.webm'], toast: 'gold' }, // 满星随机 / 里程碑庆祝

  /* Token 里程碑称号（累计 Token 达到即解锁，只升不降） */
  titles: [
    { at: 100,  name: '实习码鱼' },
    { at: 500,  name: '摸鱼组长' },
    { at: 1000, name: '首席干饭官' },
  ],
};

/* 数值规则（与固件 stats 模块口径一致）
 * 统一口径：半星 = 1 档 = 10 分。每次按键两边都以「半星」为单位变化，
 * 且方向一致——不出现一边涨一边跌 */
const RULES = {
  feed:  { rice: +10, mood: +10 },                  // 投喂：两边同涨半星
  slack: { rice: 0,   mood: +10 },                  // 摸鱼：心情+半星，白饭不动
  work:  { rice: -10, mood: -10, tokens: +10 },     // 打工：两边同跌半星，Token+10
  pet:   { rice: 0,   mood: +10 },                  // 贴贴：心情+半星，白饭不动
  decay: { rice: -10, mood: -10, everySec: 30 },    // 自然衰减：demo 每 30s = 模拟 2h 各掉半星
  sleepAfterMs: 5 * 60 * 1000,                      // 5 分钟无操作休眠
};
