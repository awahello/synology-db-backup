/* Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved. */
SYNO.namespace('SYNO.SDS.App.DBBackup');
function dbBackupTokenFromResponse(result) {
  var data = result && result.data ? result.data : result;
  if (!result || result.success === false) return '';
  return (data && (data.synotoken || data.SynoToken || data.token)) ||
    result.SynoToken || result.synotoken || '';
}
function dbBackupTokenFromDsmContext() {
  var token = '';
  try {
    token = window.SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken;
  } catch (e) {}
  if (!token) {
    try { token = new URLSearchParams(window.location.search).get('SynoToken'); } catch (e) {}
  }
  return typeof token === 'string' ? token : '';
}
function dbBackupFetchToken(url) {
  return fetch(url, { credentials: 'same-origin', cache: 'no-store' })
    .then(function (response) { return response.json(); })
    .then(dbBackupTokenFromResponse)
    .catch(function () { return ''; });
}
SYNO.SDS.App.DBBackup.Instance = Vue.extend({
  data: function () { return { cgiUrl: 'about:blank' }; },
  created: function () {
    var vm = this;
    var token = dbBackupTokenFromDsmContext();
    var getApiToken = function () {
      return dbBackupFetchToken('/webapi/entry.cgi?api=SYNO.API.Auth&version=6&method=token');
    };
    Promise.resolve(token || getApiToken()).then(function (value) {
      return value || dbBackupFetchToken('/webman/login.cgi');
    }).then(function (value) {
      vm.cgiUrl = '/webman/3rdparty/DBBackup/index.cgi' +
        (value ? '?SynoToken=' + encodeURIComponent(value) : '');
    }).catch(function () {
      // The CGI still checks the DSM cookie server-side. It will reject access
      // when a token is required but cannot be retrieved by this DSM session.
      vm.cgiUrl = '/webman/3rdparty/DBBackup/index.cgi';
    });
  },
  template: '<v-app-instance class-name="SYNO.SDS.App.DBBackup.Instance"><v-app-window syno-id="SYNO.SDS.App.DBBackup.Window" width="1200" height="760" :resizable="true"><iframe title="数据库自动备份" :src="cgiUrl" style="width:100%;height:100%;border:0;display:block"></iframe></v-app-window></v-app-instance>'
});
