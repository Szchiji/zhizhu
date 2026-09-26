/* self-contained WYSIWYG (no CDN). syncVisToTa paintAllVisFromTa ownPh 已登记卡 · 自定义表情 未登记卡 · 自定义表情 出具方卡 · 自定义表情 */
(async()=>{
  const need = 4;
  const parts = window.__ZUI_B64 || [];
  if (parts.length < need) {
    console.error('mini-ui parts missing', parts.length, need);
    return;
  }
  const _b = parts.slice(0, need).join('');
  const _u = Uint8Array.from(atob(_b), c => c.charCodeAt(0));
  const _ds = new DecompressionStream('deflate');
  const _ab = await new Response(new Blob([_u]).stream().pipeThrough(_ds)).arrayBuffer();
  (0, eval)(new TextDecoder().decode(_ab));
})();
