/* wave4: confirm dialogs for sensitive admin actions */
(function(){
  function confirmAct(title,message){
    return new Promise(function(resolve){
      try{
        if(window.Telegram && Telegram.WebApp && Telegram.WebApp.showPopup){
          Telegram.WebApp.showPopup({
            title: title||'确认',
            message: String(message||''),
            buttons:[{id:'cancel',type:'cancel',text:'取消'},{id:'ok',type:'destructive',text:'确认'}]
          }, function(id){ resolve(id==='ok'); });
          return;
        }
      }catch(e){}
      resolve(window.confirm(String(message||title||'确认？')));
    });
  }
  window.confirmAct = confirmAct;

  if(typeof userAct === 'function'){
    var _userAct = userAct;
    window.userAct = async function(action, tg_id){
      var labels = {user_delete:'删除用户及其登记', user_block:'拉黑用户', user_unblock:'解除拉黑'};
      if(labels[action]){
        var yes = await confirmAct('敏感操作', (labels[action]||action)+'：'+tg_id+'？');
        if(!yes) return;
      }
      return _userAct(action, tg_id);
    };
  }

  if(typeof savePlans === 'function'){
    var _savePlans = savePlans;
    window.savePlans = async function(){
      var yes = await confirmAct('确认改价','保存套餐将立即影响开通价格，确认？');
      if(!yes) return;
      return _savePlans();
    };
  }

  if(typeof confirmOrder === 'function'){
    var _confirmOrder = confirmOrder;
    window.confirmOrder = async function(){
      var yes = await confirmAct('确认开通','手动确认订单将立即开通会员，确认？');
      if(!yes) return;
      return _confirmOrder();
    };
  }
})();
