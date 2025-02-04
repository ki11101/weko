$(document).ready(function () {
  let curDate = new Date();
  let curDateStr = curDate.getFullYear() + '-' + (curDate.getMonth() + 1) + '-' + curDate.getDate();
  $('#btn_back').on('click', function () {
    window.history.back();
  });
  $('#btn_pop_action').on('click', function () {
    $('#myModal').modal('show');
  });
  function isApproval(action){
    return action && action.name == 'Approval';
  }
  $('.btn_apply').on('click', function () {
    let actionId = $(this).data('action-id');
    let actionName = $('#action_name_' + actionId).text();
    let actionVer = $('#action_ver_' + actionId).text();
    let apply_action_list = JSON.parse(localStorage.getItem('apply_action_list'));
    let apply_action = apply_action_list.find(function (element) {
      return element.id == actionId;
    });
    if (!apply_action || isApproval(apply_action)) {
      apply_action = {
        id: actionId,
        name: actionName,
        date: curDateStr,
        version: actionVer,
        user: 0,
        user_deny: false,
        role: 0,
        role_deny: false,
        workflow_flow_action_id: -1,
        send_mail_setting : {"inform_reject": false, "inform_approval": false, "request_approval": false},
        action: 'ADD'
      };
      apply_action_list.push(apply_action);
    } else {
      Object.assign(apply_action, { action: 'ADD' });
    }
    localStorage.setItem('apply_action_list', JSON.stringify(apply_action_list));
    if(!isApproval(apply_action)){
      $(this).removeClass('btn-primary');
      $(this).prop('disabled', true);
    }
    $('#btn_unusable_' + actionId).addClass('btn-primary');
    $('#btn_unusable_' + actionId).removeProp('disabled');
    init_action_list(apply_action);
    $('#myModal').modal('hide');
  });
  $('.btn_unusable').on('click', function () {
    let actionId = $(this).data('action-id');
    apply_action_list = JSON.parse(localStorage.getItem('apply_action_list'));
    let apply_action = {};
    let count = 0;
    for (let index = 0; index < apply_action_list.length; index++) {
      if (apply_action_list[index].id == actionId && apply_action_list[index].action != 'DEL') {
        count++;
        apply_action = apply_action_list[index];
      }
    }
    Object.assign(apply_action, { action: 'DEL' });
    localStorage.setItem('apply_action_list', JSON.stringify(apply_action_list));
    if(!isApproval(apply_action)){
      $(this).removeClass('btn-primary');
      $(this).prop('disabled', true);
      $('#btn_apply_' + actionId).addClass('btn-primary');
      $('#btn_apply_' + actionId).removeProp('disabled');
    }
    else{
      if (count == 1) {
        $(this).removeClass('btn-primary');
        $(this).prop('disabled', true);
      }
    }
    init_action_list(apply_action);
    $('#myModal').modal('hide');
  });
  $('#tb_action_list').on('click', '.sortable_up', function () {
    let cur_row = $(this).parents('tr');
    cur_row.after(cur_row.prev());
    initSortedBtn();
  });
  $('#tb_action_list').on('click', '.sortable_down', function () {
    cur_row = $(this).parents('tr');
    cur_row.before(cur_row.next());
    initSortedBtn();
  });
  $('#tb_action_list').on('change', '.td_action_role', function () {
    initSortedBtn();
  });
  $('#tb_action_list').on('change', '.td_action_role_deny', function () {
    initSortedBtn();
  });
  $('#myModalActionUser').on('click', '#btnSettingActionUser', function () {
    let selectedOption = $( "#myModalActionUser #cbxActionUser option:selected");
    let val = selectedOption.val();
    if (val) {
      let txt = selectedOption.text();
      let order = $("#myModalActionUser .action-order").text();
      let $cbbActionUser = $('select[data-row-order="'+order+'"]');
      $("#cbxActionUser > option").each(function() {
        $('select[data-row-order="'+order+'"] option[value="'+this.value+'"]').each(function() {
          $(this).remove();
        });
      });
      $cbbActionUser.append(new Option(txt, val));
      $cbbActionUser.val(val);
      apply_action_list = JSON.parse(localStorage.getItem('apply_action_list'));
      apply_action = apply_action_list[order - 1]

      Object.assign(apply_action, { user: val });
      localStorage.setItem('apply_action_list', JSON.stringify(apply_action_list));
      $("#myModalActionUser").modal("hide");
    }
  });
  $('#tb_action_list').on('change', '.td_action_user', function () {
    if($(this).val() == -1){
      let order = $(this).attr('data-row-order');
      $("#myModalActionUser .my-modal-action-user").text(order);
      $("#myModalActionUser").modal("show");
    }
    initSortedBtn();
  });
  $('#tb_action_list').on('change', '.td_action_user_deny', function () {
    initSortedBtn();
  });

  $('#btn_submit').on('click', function () {
    initSortedBtn();
    $.ajax({
      url: $(this).data('uri'),
      method: 'POST',
      async: true,
      contentType: 'application/json',
      data: localStorage.getItem('apply_action_list'),
      success: function (data, status) {
        uptOrderInfo(false);
        addAlert(data.msg);
        updateDataWorkflowFlowActionId(data.actions);
      },
      error: function (jqXHR, status) {
        var modalcontent = "Update failed";
        $("#inputModal").html(modalcontent);
        $("#allModal").modal("show");
      }
    });
  });
  $('#btn-new-flow').on('click', function () {
    let flow_name = $('#txt_flow_name').val();
    if (flow_name.length == 0) {
      $('#div_flow_name').addClass('has-error');
      $('#txt_flow_name').focus();
      return;
    }
    $.ajax({
      url: document.location,
      method: 'POST',
      async: true,
      contentType: 'application/json',
      data: JSON.stringify({ 'flow_name': flow_name }),
      success: function (data, status) {
        if (data.code == 0) {
          document.location.href = data.data.redirect;
        }
      },
      error: function (jqXHR, status) {
        var modalcontent = 'Create failed.';
        if (jqXHR.status === 400) {
          var response = JSON.parse(jqXHR.responseText);
          modalcontent += ' ' + response.msg;
        }
        $('#inputModal').text(modalcontent);
        $('#allModal').modal('show');
      }
    });
  });
  $('#btn-upt-flow').on('click', function () {
    let flow_name = $('#txt_flow_name').val();
    if (flow_name.length == 0) {
      $('#div_flow_name').addClass('has-error');
      $('#txt_flow_name').focus();
      return;
    }
    $.ajax({
      url: document.location,
      method: 'POST',
      async: true,
      contentType: 'application/json',
      data: JSON.stringify({ 'flow_name': flow_name }),
      success: function (data, status) {
        var modalcontent = data.msg;
        $('#inputModal').text(modalcontent);
        $('#modalSendEmailSuccess').modal('show');
      },
      error: function (jqXHR, status) {
        var modalcontent = 'Update failed.';
        if (jqXHR.status === 400) {
          var response = JSON.parse(jqXHR.responseText);
          modalcontent += ' ' + response.msg;
        }
        $('#inputModal').text(modalcontent);
        $('#allModal').modal('show');
      }
    });
  });
  $('#btn-del-flow').on('click', function () {
    $.ajax({
      url: document.location,
      method: 'DELETE',
      async: true,
      contentType: 'application/json',
      success: function (data, status) {
        if (0 != data.code) {
          $("#inputModal").html(data.msg);
          $("#modalSendEmailSuccess").modal("show");
        } else {
          document.location.href = data.data.redirect;
        }
      },
      error: function (jqXHE, status) {
        var modalcontent = "Delete Failed";
        $("#inputModal").html(modalcontent);
        $("#allModal").modal("show");
      }
    });
  });

  let action_list = [];
  $('#txt_flow_name').focus();
  setOrderApproval();
  $('#tb_action_list .action_ids').each(function (index) {
    let $tr = $(this).parents('tr');
    let actionId = $(this).text();
    let actionname = $('#td_action_name_' + actionId).text();
    if(!isApproval({'name': actionname})){
      $('#btn_apply_' + actionId).removeClass('btn-primary');
      $('#btn_apply_' + actionId).addClass('btn-default');
      $('#btn_apply_' + actionId).prop('disabled', true);
      $('#btn_unusable_' + actionId).addClass('btn-primary');
      $('#btn_unusable_' + actionId).removeProp('disabled');
    }
    else{
      $('#btn_unusable_' + actionId).addClass('btn-primary');
      $('#btn_unusable_' + actionId).removeProp('disabled');
    }
    $('#flow_action_ver_' + actionId).text($('#td_action_ver_' + actionId).text());
    $('#flow_action_date_' + actionId).text($('#td_action_date_' + actionId).text());
    action_list.push({
      id: actionId,
      name: $tr.find('#td_action_name_' + actionId).text(),
      date: $tr.find('#td_action_date_' + actionId).text(),
      version: $tr.find('#td_action_ver_' + actionId).text(),
      user: $tr.find('#td_action_user_' + actionId).val(),
      user_deny: $tr.find('#td_action_user_deny_' + actionId).is(':checked'),
      role: $tr.find('#td_action_role_' + actionId).val(),
      role_deny: $tr.find('#td_action_role_deny_' + actionId).is(':checked'),
      workflow_flow_action_id: $(this).data('workflow-flow-action-id'),
      send_mail_setting: {
        "request_approval": $tr.find('#td_action_request_approval_' + actionId).is(':checked'),
        "inform_approval": $tr.find('#td_action_approval_done_' + actionId).is(':checked'),
        "inform_reject": $tr.find('#td_action_approval_reject_' + actionId).is(':checked')
      },
      action: 'ADD'
    });
  });
  localStorage.setItem('apply_action_list', JSON.stringify(action_list));
  function init_action_list(apply_action) {
    if (apply_action.action == 'DEL') {
      let $tr;
      $('#tb_action_list .action_ids').each(function (index) {
        if ($(this).parents('tr').prop('id') === 'row_' + apply_action.id) {
          $tr = $(this).parents('tr');
        }
      });
      $tr.remove();
    } else {
      let new_row = $('table.flow-row-template').clone();
      new_row = new_row.html();
      new_row = new_row.replaceAll('<tbody>', '');
      new_row = new_row.replaceAll('</tbody>', '');
      new_row = new_row.replaceAll('apply_action.id', apply_action.id);
      new_row = new_row.replaceAll('action.id', apply_action.workflow_flow_action_id);
      new_row = new_row.replaceAll('apply_action.name', apply_action.name);
      new_row = new_row.replaceAll('apply_action.action_date', apply_action.date);
      new_row = new_row.replaceAll('apply_action.action_version', apply_action.version);
      if(!isApproval(apply_action)){
        new_row = new_row.replaceAll('specify-property-option', 'hide');
        new_row = new_row.replaceAll('<span class="approval-order"></span>', '');
        new_row = new_row.replaceAll('mail_setting_options', 'hide');
      }
      $('#tb_action_list').append(new_row);
    }
    initSortedBtn();
  }
  function initSortedBtn() {
    $('.sortable').removeProp('disabled');
    $('.sortable_up:first').prop('disabled', true);
    $('.sortable_down:last').prop('disabled', true);
    initOrderNum();
    uptOrderInfo();
    setOrderApproval();
  }
  function initOrderNum() {
    $('#tb_action_list .action_order').each(function (index) {
      $(this).text(index + 1);
      let cbbActionUser = $(this).parents('tr').find('select.td_action_user');
      $(cbbActionUser).attr('data-row-order', $(this).text());
    });
  }
  function uptOrderInfo(with_delete = true) {
    action_list = [];
    $('#tb_action_list .action_ids').each(function (index) {

      let $tr = $(this).parents('tr');

      let actionId = $(this).text();
      action_list.push({
        id: actionId,
        name: $tr.find('#td_action_name_' + actionId).text(),
        date: $tr.find('#td_action_date_' + actionId).text(),
        version: $tr.find('#td_action_ver_' + actionId).text(),
        user: $tr.find('#td_action_user_' + actionId).val(),
        user_deny: $tr.find('#td_action_user_deny_' + actionId).is(':checked'),
        role: $tr.find('#td_action_role_' + actionId).val(),
        role_deny: $tr.find('#td_action_role_deny_' + actionId).is(':checked'),
        workflow_flow_action_id: $(this).data('workflow-flow-action-id'),
        send_mail_setting: {
            "request_approval": $tr.find('#td_action_request_approval_' + actionId).is(':checked'),
            "inform_approval":  $tr.find('#td_action_approval_done_' + actionId).is(':checked'),
            "inform_reject":  $tr.find('#td_action_approval_reject_' + actionId).is(':checked')
        },
        action: 'ADD'
      });
    });
    if (with_delete) {
      apply_action_list = JSON.parse(localStorage.getItem('apply_action_list'));
      for (let index = 0; index < apply_action_list.length; index++) {
        let deleted_action = apply_action_list[index];
        if (deleted_action.action == 'DEL' && deleted_action.workflow_flow_action_id != '-1') {
          action_list.push(deleted_action);
        }
      }
    }
    localStorage.setItem('apply_action_list', JSON.stringify(action_list));
  }

  function setOrderApproval(){
    $('#tb_action_list .approval-order').each(function (i) {
      $(this).text(' ('+(i+1)+')');
    });
  }

  function updateDataWorkflowFlowActionId(actions){
    // Update data-workflow-flow-action-id
    $('#tb_action_list .action_ids').each(function (i) {
      let row = $(this).parents('tr');
      let order = $(row).find('.action_order').text();
      let action = actions.find(function(elm){
        if(elm.action_order == order){
          return elm;
        }
      });
      $(this).data('workflow-flow-action-id', action.id);
    });
  }

  function addAlert(message) {
    $("#alerts").append(
      '<div class="alert alert-light" id="alert-style">' +
        '<button type="button" class="close" data-dismiss="alert">' +
        "&times;</button>" +
        message +
        "</div>"
    );
  }

  $('#myModalActionUser').on('hidden.bs.modal', function (e) {
    $('#cbxActionUser option:selected').removeAttr('selected');
    let order = $("#myModalActionUser .action-order").text();
     if($('select[data-row-order="'+order+'"]').val() == '-1'){
        $('select[data-row-order="'+order+'"]').val(0);
     }
  })
});

