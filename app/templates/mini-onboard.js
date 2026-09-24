/* wave5: show profile onboarding banner on 我的 tab */
(function(){
  function ensureBanner(){
    var host=document.getElementById('tab-me');
    if(!host) return null;
    var el=document.getElementById('onboard-banner');
    if(el) return el;
    el=document.createElement('div');
    el.id='onboard-banner';
    el.className='card';
    el.style.display='none';
    el.innerHTML='<div class="kicker">完善资料</div><p class="sub" id="onboard-text"></p>';
    host.insertBefore(el, host.firstChild);
    return el;
  }
  var _loadMe=window.loadMe;
  if(typeof _loadMe==='function'){
    window.loadMe=async function(){
      await _loadMe.apply(this, arguments);
      try{
        var user=(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initDataUnsafe&&Telegram.WebApp.initDataUnsafe.user)||null;
        var initData=(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.initData)||'';
        if(!user) return;
        var j=await fetch('/api/mini/me?user_id='+user.id+'&init_data='+encodeURIComponent(initData)).then(function(r){return r.json();});
        var banner=ensureBanner();
        if(!banner) return;
        if(j&&j.need_profile&&j.onboarding_banner){
          document.getElementById('onboard-text').textContent=j.onboarding_banner;
          banner.style.display='block';
        }else{
          banner.style.display='none';
        }
      }catch(e){}
    };
  }
})();
