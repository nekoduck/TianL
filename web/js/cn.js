/**
 * [INPUT]: 无外部依赖
 * [OUTPUT]: 对外提供 cn(n)：1~99 的中文数字（一、十二、廿以下用十）
 * [POS]: 前端的数字措辞工具——选项序号与传闻条数都以汉字呈现，界面里不出现阿拉伯数字
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
const DIGITS = '〇一二三四五六七八九';

export function cn(n) {
  if (n < 10) return DIGITS[n];
  const tens = Math.floor(n / 10);
  const ones = n % 10;
  return (tens > 1 ? DIGITS[tens] : '') + '十' + (ones ? DIGITS[ones] : '');
}
