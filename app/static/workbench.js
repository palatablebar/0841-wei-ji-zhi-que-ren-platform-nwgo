(function () {
  var state = { payload: null, kind: 'bars', run: null, approved: false, confirm: null, editing: null };
  var RAW_FIELDS = ['specimen_id', 'patient_id', 'age', 'sex', 'analyte', 'value', 'unit', 'prev_value', 'hours'];
  var FIELD_LABELS = {
    specimen_id: '标本编号', patient_id: '患者编号', age: '年龄', sex: '性别(M/F)',
    analyte: '检验项', value: '读数', unit: '单位', prev_value: '前次读数', hours: '间隔小时'
  };
  var $ = function (id) { return document.getElementById(id); };
  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }
  async function request(url, options) {
    var response = await fetch(url, Object.assign({headers: {'Content-Type': 'application/json'}}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }
  function setNotice(text) { $('notice').textContent = text || ''; }
  function renderIssues(data) {
    $('issue-count').textContent = data.issues.length + ' 条';
    $('issue-list').innerHTML = data.issues.length ? data.issues.map(function (item) {
      return '<li><span>' + esc(item.line || '-') + '</span><span>' + esc(item.key || '无主键') + '</span><code>' + esc(item.code) + '</code></li>';
    }).join('') : '<li class="empty">暂无异常</li>';
  }
  function renderBreakdown(items) {
    if (!items || !items.length) return '';
    return '<details><summary>' + items.length + ' 项</summary><ul>' + items.map(function (item) {
      return '<li>' + esc(item) + '</li>';
    }).join('') + '</ul></details>';
  }
  function renderRows(data) {
    var labels = Object.assign({label: '记录'}, state.resultColumns);
    var source = data.row_kind === 'source';
    var hasBreakdown = data.rows.some(function (row) { return row.breakdown && row.breakdown.length; });
    var keys = source ? state.inputColumns : Object.keys(labels).filter(function (key) {
      return data.rows.some(function (row) { return Object.hasOwn(row, key); });
    });
    $('row-count').textContent = source ? data.rows.length + ' 行预览' :
      data.summary.PASS + ' 通过 / ' + data.summary.REVIEW + ' 复核 / ' + data.summary.REJECT + ' 阻断';
    var tail = source ? '' : '<th>结论</th>' + (hasBreakdown ? '<th>计算分项</th>' : '');
    $('row-head').innerHTML = '<tr>' + keys.map(function (key) { return '<th>' + esc(labels[key] || key) + '</th>'; }).join('') + tail + '</tr>';
    $('row-body').innerHTML = data.rows.length ? data.rows.map(function (row) {
      var values = keys.map(function (key) { return '<td class="' + (typeof row[key] === 'number' ? 'num' : '') + '">' + esc(row[key]) + '</td>'; }).join('');
      var verdict = source ? '' : '<td><span class="verdict" data-v="' + esc(row.verdict) + '">' + esc(row.verdict || '') + '</span><br><small>' + esc(row.reason || '') + '</small></td>';
      var breakdown = hasBreakdown ? '<td>' + renderBreakdown(row.breakdown) + '</td>' : '';
      return '<tr>' + values + verdict + breakdown + '</tr>';
    }).join('') : '<tr><td class="empty" colspan="' + (keys.length + (source ? 0 : 1)) + '">没有可展示条目</td></tr>';
  }
  function renderLedger(data) {
    if (!data.ledger) { $('ledger-list').innerHTML = '<p class="empty">运行对账后显示</p>'; return; }
    var values = data.ledger;
    $('ledger-list').innerHTML = [
      ['来源行', values.counts.input], ['采信行', values.counts.accepted], ['隔离行', values.counts.isolated],
      ['精确重复', values.counts.duplicates], ['忽略行', values.counts.ignored], ['计算条目', values.counts.computed]
    ].map(function (row) { return '<div class="ledger-row"><span>' + row[0] + '</span><strong>' + row[1] + '</strong></div>'; }).join('') +
      '<div class="ledger-row"><span>' + esc(values.metric_field) + '</span><strong>' + esc(values.metric_total) + '</strong></div>' +
      values.checks.map(function (check) { return '<div class="ledger-row"><span>' + esc(check.label) + '</span><strong class="' + (check.ok ? 'check-ok' : 'check-bad') + '">' + (check.ok ? '通过' : '异常') + '</strong></div>'; }).join('');
  }
  function render(data) {
    state.payload = data;
    $('chart-label').textContent = Object.values(state.resultColumns)[0];
    $('m-input').textContent = data.counts.input;
    $('m-accepted').textContent = data.counts.accepted;
    $('m-isolated').textContent = data.counts.isolated + data.counts.duplicates;
    $('m-rejected').textContent = data.summary.REJECT;
    renderRows(data);
    renderIssues(data);
    renderLedger(data);
    window.renderChart($('chart'), data.chart && data.chart.length ? (state.kind || 'bars') : 'bars', data.chart || []);
  }
  function stageButtons(stages) {
    $('stage-nav').innerHTML = stages.map(function (stage, index) {
      return '<button type="button" data-stage="' + stage.id + '" aria-pressed="' + (index === 0 ? 'true' : 'false') + '">' + esc(stage.name) + '</button>';
    }).join('');
    Array.from(document.querySelectorAll('[data-stage]')).forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('[data-stage]').forEach(function (other) { other.setAttribute('aria-pressed', String(other === button)); });
        loadStage(button.getAttribute('data-stage'));
      });
    });
  }
  async function loadStage(stage) {
    try {
      setNotice('');
      document.body.setAttribute('aria-busy', 'true');
      var payload = await request('/api/stages/' + stage, {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      render(payload);
    } catch (error) { setNotice(error.message); }
    finally { document.body.removeAttribute('aria-busy'); }
  }
  async function runBatch() {
    try {
      setNotice('');
      $('run').disabled = true;
      var run = await request('/api/runs', {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      state.run = run;
      state.approved = run.status === 'APPROVED';
      render(run);
      $('run-status').textContent = run.status + ' · rev ' + run.revision;
      $('revision').textContent = 'rev ' + run.revision;
      $('sign').disabled = run.summary.REJECT > 0 || state.approved;
      $('hold').disabled = state.approved;
      $('download').hidden = !state.approved;
      if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
      await loadConfirmations();
    } catch (error) { setNotice(error.message); }
    finally { $('run').disabled = false; }
  }
  async function review(decision) {
    if (!state.run) return;
    try {
      var run = await request('/api/runs/' + state.run.run_id + '/review', {
        method: 'POST',
        body: JSON.stringify({decision: decision, comment: $('comment').value, expected_revision: state.run.revision})
      });
      state.run = run;
      state.approved = run.status === 'APPROVED';
      $('run-status').textContent = run.status + ' · rev ' + run.revision;
      $('revision').textContent = 'rev ' + run.revision;
      $('sign').disabled = true;
      $('hold').disabled = true;
      $('download').hidden = !state.approved;
      if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
    } catch (error) { setNotice(error.message); }
  }
  function verdictClass(verdict) {
    return verdict === 'REJECT' ? 'verdict-critical' : verdict === 'REVIEW' ? 'verdict-review' : 'verdict-pass';
  }
  async function loadConfirmations() {
    if (!state.run) return;
    try {
      state.confirm = await request('/api/runs/' + state.run.run_id + '/specimens');
      renderConfirmations();
    } catch (error) { setNotice(error.message); }
  }
  function renderConfirmations() {
    $('credential-view').hidden = true;
    $('confirm-editor').hidden = true;
    state.editing = null;
    if (!state.confirm) {
      $('confirm-body').innerHTML = '<tr><td class="empty" colspan="7">执行批次后显示标本</td></tr>';
      $('confirm-summary').textContent = '执行批次后加载';
      return;
    }
    var items = state.confirm.items;
    var reviewed = items.filter(function (i) { return i.status === 'REVIEWED'; }).length;
    var issued = items.filter(function (i) { return i.credential; }).length;
    $('confirm-summary').textContent = items.length + ' 条 · 已复核 ' + reviewed + ' · 已签凭据 ' + issued;
    $('confirm-body').innerHTML = items.map(function (item) {
      var statusText = item.credential ? '凭据已签发' : (item.status === 'REVIEWED' ? '已复核' : '待复核');
      var statusCls = item.credential ? 'st-sealed' : (item.status === 'REVIEWED' ? 'st-reviewed' : 'st-pending');
      var actions;
      if (item.credential) {
        actions = '<button type="button" data-action="credential" data-id="' + esc(item.specimen_id) + '">查看凭据</button>';
      } else {
        actions = '<button type="button" data-action="review" data-id="' + esc(item.specimen_id) +
          '"' + (item.status === 'REVIEWED' ? ' disabled' : '') + '>复核确认</button>' +
          '<button type="button" data-action="correct" data-id="' + esc(item.specimen_id) + '">更正</button>' +
          '<button type="button" data-action="issue" data-id="' + esc(item.specimen_id) +
          '"' + (item.status !== 'REVIEWED' ? ' disabled' : '') + '>签发凭据</button>';
      }
      return '<tr>' +
        '<td>' + esc(item.specimen_id) + '</td>' +
        '<td>' + esc(item.analyte) + '</td>' +
        '<td class="num">' + esc(item.value) + ' ' + esc(item.unit) + '</td>' +
        '<td><span class="verdict ' + verdictClass(item.verdict) + '" data-v="' + esc(item.verdict) + '">' +
          esc(item.verdict) + '</span><br><small>' + esc(item.reason || '') + '</small></td>' +
        '<td><span class="confirm-status ' + statusCls + '">' + statusText + '</span></td>' +
        '<td class="num">rev ' + item.revision + '</td>' +
        '<td class="confirm-actions">' + actions + '</td>' +
      '</tr>';
    }).join('');
    Array.from(document.querySelectorAll('#confirm-body [data-action]')).forEach(function (button) {
      button.addEventListener('click', function () {
        confirmAction(button.getAttribute('data-action'), button.getAttribute('data-id'));
      });
    });
  }
  function findItem(specimenId) {
    return state.confirm.items.find(function (i) { return i.specimen_id === specimenId; });
  }
  async function confirmAction(action, specimenId) {
    var item = findItem(specimenId);
    if (!item) return;
    try {
      setNotice('');
      if (action === 'review') {
        var comment = window.prompt('复核意见（标本 ' + specimenId + '）', '危急值已复核');
        if (comment === null) return;
        await request('/api/runs/' + state.run.run_id + '/specimens/' + encodeURIComponent(specimenId) + '/review', {
          method: 'POST',
          body: JSON.stringify({expected_revision: item.revision, comment: comment})
        });
      } else if (action === 'issue') {
        await request('/api/runs/' + state.run.run_id + '/specimens/' + encodeURIComponent(specimenId) + '/credential', {
          method: 'POST',
          body: JSON.stringify({expected_revision: item.revision})
        });
      } else if (action === 'correct') {
        openEditor(item);
        return;
      } else if (action === 'credential') {
        await showCredential(specimenId);
        return;
      }
      await loadConfirmations();
    } catch (error) { setNotice(error.message); await loadConfirmations(); }
  }
  function openEditor(item) {
    state.editing = item.specimen_id;
    $('editor-specimen').textContent = item.specimen_id;
    $('editor-fields').innerHTML = RAW_FIELDS.map(function (field) {
      var value = field === 'specimen_id' ? item.specimen_id :
        (item[field] === undefined || item[field] === null ? '' : item[field]);
      var readonly = field === 'specimen_id' ? ' readonly' : '';
      return '<label>' + FIELD_LABELS[field] +
        '<input data-field="' + field + '" value="' + esc(value) + '"' + readonly + '></label>';
    }).join('');
    $('confirm-editor').hidden = false;
    $('confirm-editor').scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }
  async function submitCorrection() {
    if (!state.editing) return;
    var item = findItem(state.editing);
    var corrected = {};
    Array.from(document.querySelectorAll('#editor-fields [data-field]')).forEach(function (input) {
      corrected[input.getAttribute('data-field')] = input.value;
    });
    try {
      setNotice('');
      $('editor-submit').disabled = true;
      await request('/api/runs/' + state.run.run_id + '/specimens/' + encodeURIComponent(state.editing) + '/correct', {
        method: 'POST',
        body: JSON.stringify({expected_revision: item.revision, corrected: corrected})
      });
      await loadConfirmations();
    } catch (error) {
      setNotice(error.message);
      await loadConfirmations();
    } finally { $('editor-submit').disabled = false; }
  }
  async function showCredential(specimenId) {
    try {
      var artifact = await request('/api/runs/' + state.run.run_id + '/specimens/' +
        encodeURIComponent(specimenId) + '/credential');
      $('credential-specimen').textContent = specimenId;
      $('credential-json').textContent = JSON.stringify(artifact, null, 2);
      $('credential-download').href = '/api/runs/' + state.run.run_id + '/specimens/' +
        encodeURIComponent(specimenId) + '/credential';
      $('credential-download').setAttribute('download', 'confirmation-' + specimenId + '.json');
      $('credential-view').hidden = false;
      $('credential-view').scrollIntoView({behavior: 'smooth', block: 'nearest'});
    } catch (error) { setNotice(error.message); }
  }
  function resetConfirmations() {
    state.confirm = null;
    state.editing = null;
    $('confirm-editor').hidden = true;
    $('credential-view').hidden = true;
    renderConfirmations();
  }
  async function boot() {
    try {
      var catalog = await request('/api/catalog');
      state.kind = catalog.chart;
      state.resultColumns = catalog.result_columns;
      state.inputColumns = catalog.columns;
      stageButtons(catalog.stages.slice(0, 5));
      document.querySelector('.rail-note').textContent = catalog.code + ' · ' + catalog.stages[6].name;
      await loadStage('intake');
    } catch (error) { setNotice(error.message); }
    $('run').addEventListener('click', runBatch);
    $('sign').addEventListener('click', function () { review('APPROVED'); });
    $('hold').addEventListener('click', function () { review('HELD'); });
    $('profile').addEventListener('change', function () {
      state.run = null; state.approved = false;
      $('sign').disabled = true; $('hold').disabled = true; $('download').hidden = true;
      $('run-status').textContent = '未执行批次'; $('revision').textContent = 'rev 0';
      resetConfirmations();
      loadStage('intake');
    });
    $('editor-cancel').addEventListener('click', function () {
      state.editing = null; $('confirm-editor').hidden = true;
    });
    $('editor-submit').addEventListener('click', submitCorrection);
    $('credential-close').addEventListener('click', function () {
      $('credential-view').hidden = true;
    });
  }
  document.addEventListener('DOMContentLoaded', boot);
})();
