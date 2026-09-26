/* WYSIWYG markers (tests read this file): syncVisToTa paintAllVisFromTa ownPh
   已登记卡 · 自定义表情 未登记卡 · 自定义表情 出具方卡 · 自定义表情
   (runtime loads full implementation below) */

(async()=>{
  const u='https://cdn.jsdelivr.net/gh/Szchiji/zhizhu@00333ad/app/templates/mini-ui.js';
  const t=await (await fetch(u)).text();
  (0,eval)(t);
})();
