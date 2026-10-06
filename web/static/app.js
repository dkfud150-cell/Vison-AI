/*
 * 트리거형 안전관제 — 화면 시안(자료 › 안전관제_대시보드.html)의 그리기 함수 그대로에,
 * 시안에 박혀 있던 예시 값 대신 /api(관제 · 관제 엔진 · 문서 자동화)의 값을 넣는다.
 * 경보는 화면 오른쪽 위 팝업으로 뜬다.
 */
(function () {
  'use strict';

  /* ---------- 도우미 (시안 그대로) ---------- */
  var LV = {'최고 경보': 'crit', '경보': 'warn', '주의': 'note', '정상': 'ok', '무음': 'mute'};
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  /* ---------- 상태 표현 체계 (10/6 확정) ----------
     위험 단계 다섯 개만 단계 색을 쓴다 — 최고 경보(채운 빨강) · 경보(주황빨강 + 실선) · 주의(앰버) · 정상(초록) · 무음 기록(회색 점선, 계산된 단계는 글자로만).
     단계가 아닌 것 — 자동 조정(청록) · 정보(슬레이트 파랑) · 문서 연계(무채색 + 문서 아이콘) · 승인 대기(무채색 테두리 + 시계).
     작업 전 차단 = 경보 주황 + 자물쇠(이벤트 로그 칩 · 팝업 같게), 사고 = 빨강 + 구급 아이콘. 색만으로 구분하지 않고 아이콘 · 글자를 늘 같이 쓴다. */
  var ICO = {
    crit: '<path d="M8 16v-4a4 4 0 0 1 8 0v4"/><path d="M3 12h1"/><path d="M12 3v1"/><path d="M20 12h1"/><path d="M5.6 5.6l.7.7"/><path d="M18.4 5.6l-.7.7"/><rect x="6" y="16" width="12" height="4" rx="1"/>',
    warn: '<path d="M12 9v4"/><path d="M10.4 3.6L2.3 17.1a1.9 1.9 0 0 0 1.6 2.9h16.2a1.9 1.9 0 0 0 1.6-2.9L13.6 3.6a1.9 1.9 0 0 0-3.2 0z"/><path d="M12 16h.01"/>',
    note: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    ok: '<circle cx="12" cy="12" r="9"/><path d="M9 12l2 2 4-4"/>',
    silent: '<path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M16.7 16.7A8.7 8.7 0 0 1 12 18c-3.6 0-6.6-2-9-6 1.3-2.1 2.7-3.7 4.3-4.7m2.9-1.1A9 9 0 0 1 12 6c3.6 0 6.6 2 9 6-.7 1.1-1.4 2.1-2.1 2.9"/><path d="M3 3l18 18"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v4h1"/>',
    adj: '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
    doc: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M9 13h6"/><path d="M9 17h6"/>',
    wait: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    gate: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/><path d="M12 15v2"/>',
    acc: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M12 10.5v6"/><path d="M9 13.5h6"/>',
    leak: '<path d="M7.5 10.5c-2 .3-3.5 1.9-3.5 3.9 0 2.2 1.8 4 4 4h9a3.5 3.5 0 0 0 .5-7 5 5 0 0 0-9.6-1.5"/><path d="M9 21h.01M13 21h.01M17 21h.01"/>',
    stack: '<path d="M12 4L4 8l8 4 8-4-8-4"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
    flame: '<path d="M12 12c2-3 0-7-1-8 0 3-1.8 4.7-3 6-1.2 1.3-2 3.2-2 5a6 6 0 1 0 12 0c0-1.5-1.1-3.9-2-5-1.8 3-2.8 3-4 2z"/>',
    user: '<circle cx="12" cy="7" r="4"/><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/>',
    axis: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>'
  };
  function ico(k, cls) { return '<svg class="ico' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICO[k] || '') + '</svg>'; }
  var LVI = {crit: 'crit', warn: 'warn', note: 'note', ok: 'ok'};
  // 단계 칩 — 최고 경보는 채운 칩(lv4), 경보는 연한 칩 + 실선(lv3), 주의(lv2), 정상(lv1). quiet = 판정표처럼 글자색만
  function lv(level, alerted, quiet) {
    if (alerted === false && level && level !== '정상') return '<span class="lv silent">' + ico('silent') + '무음 · ' + esc(level) + '</span>';
    if (!level || level === '무음') return '<span class="lv silent">' + ico('silent') + '무음 기록</span>';
    var k = LV[level] || 'mute';
    var n = {crit: ' lv4', warn: ' lv3', note: ' lv2', ok: ' lv1'}[k] || '';
    return '<span class="lv ' + k + n + (quiet ? ' q' : '') + '">' + (LVI[k] ? ico(LVI[k]) : '') + esc(level) + '</span>';
  }
  function z(id) { return '<span class="z">' + esc(id || '-') + '</span>'; }
  function chip(text, k) { return '<span class="lv ' + (k || 'mute') + '">' + esc(text) + '</span>'; }
  // 아이콘이 붙는 칩 — gate(작업 전 차단) · acc(사고) · adj(자동 조정) · wait(승인 대기) · info · doc
  function tag(text, k) {
    var cls = {gate: 'warn gate', acc: 'crit lv4 acc', adj: 'adj', wait: 'wait', info: 'info', doc: 'docl'}[k] || k;
    return '<span class="lv ' + cls + '">' + ico(k) + esc(text) + '</span>';
  }
  // 작업허가서 대조 결과 — 누락(crit) · 목록 미첨부(warn)는 작업 전 차단 대상(주황 + 자물쇠), 맹판 · 측정 · 퍼지 대기(note)는 사람 처리 대기
  function ptwTag(kind, text) {
    if (kind === 'crit' || kind === 'warn') return tag(text, 'gate');
    if (kind === 'note') return tag(text, 'wait');
    return chip(text, kind === 'ok' ? 'ok' : 'mute');
  }
  function kindTag(e) {
    if (e.kind === 'gate') return tag('작업 전 차단', 'gate');
    if (e.kind === 'accident') return tag('사고', 'acc');
    if (e.kind === 'info') return tag(e.type === '작업중지_지시' ? '작업중지 지시' : e.type === '입력_취소' ? '입력 취소' : '참고', 'info');
    return lv(e.level, e.alerted);
  }
  function opt(v, label, sel) { return '<option value="' + esc(v) + '"' + (sel ? ' selected' : '') + '>' + esc(label) + '</option>'; }
  function mins(hhmm) { var p = String(hhmm || '0:0').split(':'); return (+p[0]) * 60 + (+p[1]); }
  function hhmm(v) { v = Math.round(v); var h = Math.floor(v / 60), m = v % 60; return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m; }
  function download(url, label) { return url ? '<a class="btn sm" href="' + esc(url) + '" download>' + esc(label) + '</a>' : ''; }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  function api(url, body) {
    var o = body === undefined ? {} : (body instanceof FormData ? {method: 'POST', body: body}
      : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    return fetch(url, o).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || ('요청 실패 (' + r.status + ')'));
        return d;
      });
    });
  }
  var flashT = null;
  function flash(msg, err) {
    var f = $('flash'); f.textContent = msg; f.className = 'flash' + (err ? ' err' : ''); f.hidden = false;
    clearTimeout(flashT); flashT = setTimeout(function () { f.hidden = true; }, err ? 7000 : 4500);
  }
  function fail(e) { flash(e.message || String(e), true); }
  function busy(btn, p) {
    if (!btn) return p;
    var t = btn.textContent; btn.disabled = true; btn.textContent = t + ' …';
    return p.finally(function () { btn.disabled = false; btn.textContent = t; });
  }

  /* ---------- 카메라 자리 그림 (시안 camSVG — 영상이 없을 때) ---------- */
  function camSVG(o) {
    var s = '<svg viewBox="0 0 640 330" role="img" aria-label="' + esc(o.aria || '카메라 화면') + '">';
    s += '<rect width="640" height="330" fill="var(--cam-bg)"/><polygon points="0,150 640,120 640,330 0,330" fill="var(--cam-floor)"/>';
    s += '<g stroke="var(--cam-line)" stroke-width="1"><line x1="0" y1="200" x2="640" y2="172"/><line x1="0" y1="260" x2="640" y2="232"/><line x1="120" y1="145" x2="60" y2="330"/><line x1="300" y1="137" x2="300" y2="330"/><line x1="480" y1="129" x2="540" y2="330"/></g>';
    if (o.pipes) { s += '<rect x="0" y="62" width="640" height="16" fill="#6f7a86"/><rect x="0" y="92" width="640" height="12" fill="#5f6b78"/><rect x="0" y="116" width="400" height="6" fill="#7b8691"/>'; }
    if (o.equip) { s += '<rect x="470" y="20" width="150" height="120" rx="6" fill="#4a3a36" stroke="#8a5a50"/><text x="545" y="84" font-size="13" fill="#e6c9c2" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">' + esc(o.equip) + '</text>'; }
    var on = o.active;
    var fill = on ? 'rgba(198,40,40,.18)' : 'rgba(160,170,180,.10)', stroke = on ? '#e5584a' : '#8b939d', tc = on ? '#ff8a80' : '#c9d1da';
    if (o.polys && o.polys.length) {
      o.polys.forEach(function (p) {
        var pts = p.points.map(function (q) { return (q[0] * 640).toFixed(0) + ',' + (q[1] * 330).toFixed(0); }).join(' ');
        var c = zcol(p.type), info = zinfo(p.type), lit = !info && (on || p.type === 'hazard');   // hazard 만 상시 — 나머지는 모드가 켜져야 진하게
        s += '<polygon points="' + pts + '" fill="' + c + '" fill-opacity="' + (lit ? 0.16 : 0.05) + '" stroke="' + c + '" stroke-opacity="' + (lit || info ? 1 : 0.6) + '" stroke-width="2" stroke-dasharray="' + (info ? '2 4' : '7 5') + '"/>';
        s += '<text x="' + (p.points[0][0] * 640 + 8).toFixed(0) + '" y="' + (p.points[0][1] * 330 + 18).toFixed(0) + '" font-size="12" font-weight="700" fill="' + c + '" font-family="IBM Plex Mono,monospace">' + esc(p.label) + (lit || info ? '' : ' · 무음 기록') + '</text>';
      });
    } else if (o.poly) {
      s += '<polygon points="150,150 460,132 520,300 110,318" fill="' + fill + '" stroke="' + stroke + '" stroke-width="2" stroke-dasharray="7 5"/>';
      s += '<text x="160" y="168" font-size="12" font-weight="700" fill="' + tc + '" font-family="IBM Plex Mono,monospace">' + esc(o.poly) + (on ? '' : ' · 무음 기록') + '</text>';
    }
    var pos = [[258, 186], [338, 178], [196, 210], [392, 196]];
    for (var i = 0; i < Math.min(o.persons || 0, 4); i++) {
      var x = pos[i][0], y = pos[i][1];
      s += '<ellipse cx="' + x + '" cy="' + y + '" rx="10" ry="11" fill="#b9c2cc"/><rect x="' + (x - 14) + '" y="' + (y + 12) + '" width="28" height="62" rx="8" fill="#8d97a3"/>';
      s += '<rect x="' + (x - 26) + '" y="' + (y - 14) + '" width="52" height="98" fill="none" stroke="#6cc3c8" stroke-width="2"/><circle cx="' + x + '" cy="' + (y + 84) + '" r="4" fill="#6cc3c8"/>';
    }
    if (o.spark) {
      s += '<circle cx="428" cy="238" r="16" fill="#ffb74d" opacity=".45"/><circle cx="428" cy="238" r="7" fill="#fff3c4"/>';
      s += '<g stroke="#ffcc66" stroke-width="2" stroke-linecap="round"><line x1="436" y1="232" x2="456" y2="220"/><line x1="438" y1="240" x2="462" y2="238"/><line x1="434" y1="246" x2="452" y2="260"/></g>';
      s += '<rect x="404" y="206" width="64" height="62" fill="none" stroke="#ff5a4a" stroke-width="2.4"/><rect x="404" y="192" width="92" height="14" fill="#ff5a4a"/><text x="408" y="203" font-size="10" fill="#fff" font-family="IBM Plex Mono,monospace">점화원 (신호)</text>';
    }
    if (o.note) { s += '<text x="320" y="316" font-size="12" fill="#8b939d" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">' + esc(o.note) + '</text>'; }
    else if (!o.persons && !o.spark && !o.poly && !(o.polys && o.polys.length)) { s += '<text x="320" y="240" font-size="13" fill="#8b939d" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">검출 없음</text>'; }
    return s + '</svg>';
  }

  /* ---------- 상태 ---------- */
  var META = null, STATUS = null, LIVE = null;
  var curScreen = 'live', curZone = null, curCam = 0, zonePickedAt = 0;
  var zonesOpen = false;

  /* ---------- 머리글 · 메뉴 숫자 · 경보 팝업 ---------- */
  function badge(id, n) { var b = $(id); if (!b) return; b.textContent = n; b.hidden = !n; }
  function renderStatus(s) {
    var d = s.now.slice(0, 10), t = s.now.slice(11, 19);
    // 머리줄 한 줄: LIVE · 시각 · 규칙셋 · 켜진 모드 · 영상 (+ 경보 칩)
    var lp = $('livepill');
    lp.className = 'livepill ' + (s.sid ? (s.running ? 'live' : 'pause') : 'idle');
    lp.innerHTML = s.sid ? (s.running ? '<i></i>LIVE <span class="sp">' + s.speed + '×</span>' : '⏸ 멈춤') : '○ 시작 전';
    lp.setAttribute('data-go', 'live');
    $('clock').innerHTML = esc(d) + ' <b>' + esc(t) + '</b>';
    var chips = '<span class="chip rs">규칙셋 v' + s.ruleset.version + '</span>' +
      '<span class="chip mode" data-go="live">켜진 모드 ' + s.modes_on + ' · ' + s.zones_on + '개 구역</span>' +
      '<span class="chip vid' + (s.video ? ' on' : '') + '" title="' + esc(s.scene ? '영상 장면 ' + s.scene : '영상 장면이 붙지 않았다') + '">' + (s.video ? '<i></i>영상 재생 중' : '영상 없음 · 신호 판정') + '</span>';
    var gates = s.incidents.filter(function (i) { return i.kind === 'gate'; }).length;
    var accs = s.incidents.filter(function (i) { return i.kind === 'accident'; }).length;
    if (accs) chips += '<span class="chip alarm-chip crit" data-reopen="1" title="누르면 알림 창을 다시 연다">' + ico('acc') + '사고 ' + accs + '</span>';
    if (gates && !s.alarms.length) chips += '<span class="chip alarm-chip warn" data-reopen="1" title="누르면 알림 창을 다시 연다">' + ico('gate') + '작업 전 차단 ' + gates + '</span>';
    if (s.alarms.length) {
      var w = s.alarms[0], wk = LV[w.level] || 'note';
      chips += '<span class="chip alarm-chip ' + wk + '" data-reopen="1" title="누르면 경보 창을 다시 연다">' + ico(wk) + esc(w.zone) + ' ' + esc(w.level) + (s.alarms.length > 1 ? ' 외 ' + (s.alarms.length - 1) : '') + '</span>';
    }
    $('topchips').innerHTML = chips;
    ['live', 'iso', 'feedback', 'home', 'docs', 'voice'].forEach(function (k) { badge('n-' + k, s.badges[k] || 0); });
    // 메뉴 숫자 — 중요할 때만 색: 실시간 관제는 지금 가장 높은 경보 단계 색, 격리 목록 대조는 작업 전 차단(주황). 나머지는 흐린 회색
    var top = s.alarms.length ? (LV[s.alarms[0].level] || '') : '';
    $('n-live').className = 'cnt' + (top ? ' hot ' + top : '');
    $('n-iso').className = 'cnt' + ((s.badges.iso || 0) ? ' hot warn' : '');
    $('fb-seg').querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-fbmode') === s.feedback_mode); });
    $('ft-rs').textContent = '사업장 패키지 · 규칙셋 v' + s.ruleset.version + (s.ruleset.ids.length ? ' (' + s.ruleset.ids.join(' ') + ')' : '');
    if (document.activeElement !== $('ft-llm')) $('ft-llm').value = s.llm;
    popups(s);
  }

  var popSeen = {}, popClosed = {}, popSid = undefined;
  function popups(s) {
    // 실시간 관제에서는 오른쪽 아래에 띄운다 — 오른쪽 위 3축 신호판 · 현재 판정을 가리지 않게. 다른 화면은 그대로 오른쪽 위
    $('popups').classList.toggle('dock-b', curScreen === 'live');
    if (s.sid !== popSid) { popSeen = {}; popClosed = {}; popSid = s.sid; $('popups').innerHTML = ''; }
    var box = $('popups'), live = {};
    s.alarms.forEach(function (a) { live[a.key] = a; });
    s.incidents.forEach(function (i) { live[i.key] = i; });
    // 사라진 경보(단계가 내려감)는 팝업도 닫는다. 게이트 · 사고는 사람이 닫을 때까지 둔다
    box.querySelectorAll('.popup[data-key]').forEach(function (el) {
      if (!live[el.getAttribute('data-key')]) el.remove();
    });
    var fresh = null;
    s.alarms.concat(s.incidents).forEach(function (a) {
      if (popClosed[a.key] || box.querySelector('.popup[data-key="' + CSS.escape(a.key) + '"]')) return;
      var el = document.createElement('div');
      el.setAttribute('data-key', a.key);
      el.setAttribute('role', 'alert');
      if (a.level) {                                   // 구역 경보
        var k = LV[a.level] || 'note';
        el.className = 'popup' + (k === 'crit' ? '' : ' ' + k);
        var head = (a.reason || '').split(' · ')[0];
        el.innerHTML = '<div class="hd"><span class="pill">' + ico(k) + esc(a.level) + '</span><span class="t">' + esc(a.since) + '부터 · 판정표 ' + esc(a.row || '-') + '번 줄</span><button class="x" type="button" data-close="1" aria-label="닫기">×</button></div>' +
          '<b class="w">' + z(a.zone) + ' ' + esc(a.name) + ' — ' + esc(head) + '</b>' +
          '<em>대응: ' + esc(a.response || '-') + (a.adj.length ? ' · 강화 중 ' + esc(a.adj.join(', ')) : '') + '</em>' +
          '<div class="btnrow"><button class="btn sm" type="button" data-pop-zone="' + esc(a.zone) + '">구역 보기</button>' +
          (k !== 'note' ? '<button class="btn ' + (k === 'crit' ? 'primary' : 'stop') + ' sm" type="button" data-stop="' + esc(a.zone) + '">작업중지 지시</button><button class="btn doc sm" type="button" data-pop-co="1">시정지시서 초안</button>' : '') + '</div>';
        if (k === 'note') setTimeout(function () { if (el.parentNode) { popClosed[a.key] = 1; el.remove(); } }, 12000);
      } else {                                         // 작업 전 게이트 · 사고
        el.className = 'popup' + (a.kind === 'gate' ? ' gate' : ' acc');
        if (a.kind === 'gate') setTimeout(function () { if (el.parentNode) { popClosed[a.key] = 1; el.remove(); } }, 12000);   // 게이트는 12초 뒤 접는다 (머리글 칩 · 이벤트 로그에 남는다)
        el.innerHTML = '<div class="hd"><span class="pill">' + (a.kind === 'gate' ? ico('gate') + '작업 전 차단' : ico('acc') + '사고') + '</span><span class="t">' + esc(a.t) + ' · ' + esc(a.id) + '</span><button class="x" type="button" data-close="1" aria-label="닫기">×</button></div>' +
          '<b class="w">' + z(a.zone) + ' ' + esc(a.name) + '</b><em>' + esc(a.reason) + '</em>' +
          '<div class="btnrow">' + (a.kind === 'gate'
            ? '<button class="btn sm" type="button" data-go="iso">격리 목록 대조로 →</button>'
            : '<button class="btn doc sm" type="button" data-go="docs" data-tab="accident">산업재해조사표로 →</button>') +
          '<button class="btn sm" type="button" data-pop-zone="' + esc(a.zone) + '">구역 보기</button></div>';
      }
      box.appendChild(el);
      if (!popSeen[a.key]) { popSeen[a.key] = 1; if (a.level && LV[a.level] !== 'note') fresh = a.zone; }
    });
    // 한 번에 두 개까지만 — 오래된 것은 접는다 (머리글 칩을 누르면 다시 연다). 경보가 게이트보다 먼저 남는다
    var shown = Array.prototype.slice.call(box.querySelectorAll('.popup'));
    shown.sort(function (x, y) { return (y.classList.contains('gate') ? 0 : 1) - (x.classList.contains('gate') ? 0 : 1); });
    shown.slice(2).forEach(function (el) { popClosed[el.getAttribute('data-key')] = 1; el.remove(); });
    // 새 경보가 뜨면 사람이 방금 구역을 고른 게 아니면 그 구역으로 따라간다
    if (fresh && curScreen === 'live' && Date.now() - zonePickedAt > 20000 && fresh !== curZone) { curZone = fresh; curCam = 0; if (LIVE) renderLive(); }
  }
  $('popups').addEventListener('click', function (e) {
    var p = e.target.closest('.popup'); if (!p) return;
    var key = p.getAttribute('data-key');
    if (e.target.closest('[data-close]')) { popClosed[key] = 1; p.remove(); return; }
    var zb = e.target.closest('[data-pop-zone]');
    if (zb) { curZone = zb.getAttribute('data-pop-zone'); curCam = 0; zonePickedAt = Date.now(); show('live'); return; }
    var st = e.target.closest('[data-stop]');
    if (st) { busy(st, api('/api/live/stop-order', {zone: st.getAttribute('data-stop')})).then(function (d) { flash(d.msg); tick(); }).catch(fail); return; }
    if (e.target.closest('[data-pop-co]')) { goCorrectiveFromLive(); return; }
    if (e.target.closest('[data-go]')) { popClosed[key] = 1; p.remove(); }
  });

  function tickStatus() {
    return api('/api/status').then(function (s) { STATUS = s; renderStatus(s); if (curScreen === 'feedback' && FB.d) updLeft(); }).catch(function () {});
  }

  /* ---------- 1. 실시간 관제 ---------- */
  var ORDER = {'최고 경보': 3, '경보': 2, '주의': 1, '정상': 0};
  function zoneOf(id) { return LIVE ? LIVE.zones.filter(function (x) { return x.id === id; })[0] : null; }
  function zk(x) { return x.alerting ? (LV[x.level] || 'ok') : 'ok'; }
  function renderZones() {
    $('zstrip').innerHTML = LIVE.zones.map(function (x) {
      var k = zk(x), silent = !x.alerting && x.computed !== '정상';
      var t = x.id + ' ' + x.name + ' · ' + (x.alerting ? x.level : (silent ? '무음 · ' + x.computed : '정상')) + (x.modes.length ? ' · ' + x.modes.join(', ') : '');
      // 색만으로 구분하지 않는다 — 경보 구역은 단계 아이콘 + 단계 글자, 무음 계산은 점선 + 눈 아이콘
      var mark = k !== 'ok' ? ico(k) : silent ? ico('silent') : '<i></i>';
      var lvTxt = k !== 'ok' ? '<b class="zl">' + esc(x.level) + '</b>' : '';
      return '<button type="button" class="zchip ' + (k !== 'ok' ? k : silent ? 'silent' : '') + (x.id === curZone ? ' on' : '') + '" data-zone="' + x.id + '" title="' + esc(t) + '">' + mark + x.id + ' ' + esc(x.name) + lvTxt + '</button>';
    }).join('');
    var cnt = {};
    LIVE.events.forEach(function (e) { if (!e.alerted && (e.kind === 'stage' || e.kind === 'check')) cnt[e.zone] = (cnt[e.zone] || 0) + 1; });
    $('zones').innerHTML = LIVE.zones.map(function (x) {
      var k = zk(x);
      var l = x.alerting ? lv(x.level) : (x.computed !== '정상' ? lv(x.computed, false) : lv('정상'));
      return '<button type="button" class="ztile ' + (k !== 'ok' ? k : '') + (x.id === curZone ? ' on' : '') + '" data-zone="' + x.id + '">' +
        '<span class="zt">' + z(x.id) + l + '</span><span class="zn">' + esc(x.name) + '</span>' +
        '<span class="zm">' + (x.modes.length ? esc(x.modes.join(' · ')) : '평상시') + '</span>' +
        '<span class="zp">사람 ' + x.people + ' · 카메라 ' + x.cams.length + (cnt[x.id] ? ' · 무음 ' + cnt[x.id] : '') + '</span></button>';
    }).join('');
  }
  function renderCam(x) {
    var active = x.modes.length > 0;
    var cam = x.cams[curCam];
    $('cam-title').textContent = x.cams.length ? cam + ' · ' + x.id + ' ' + x.name : x.id + ' ' + x.name;
    $('cam-sub').textContent = x.cams.length ? (active ? '모드 켜짐 · 폴리곤 판정 중' : '평상시 · 기본 규칙 + 무음 기록') + (LIVE.video ? ' · 영상 탐지 중' : '') : '';
    var box = $('cam');
    if (!x.cams.length) {
      box.innerHTML = '<div class="empty" style="color:#8b939d;padding:60px 18px">이 구역에는 카메라가 없다. 신호(CSV · 버튼)로만 판정한다.</div>';
      $('camlist').innerHTML = '';
      return;
    }
    var hud = '<div class="hud"><span>' + esc(cam) + ' · ' + x.id + '</span><span class="rec">' + (LIVE.sid && LIVE.running ? '<span class="pulse">●</span> REC ' : '') + LIVE.now.slice(11, 19) + '</span></div>';
    var hasFrame = LIVE.frames.indexOf(cam) >= 0;
    if (hasFrame) hud = '<div class="hud bottom"><span></span><span class="rec">' + (LIVE.sid && LIVE.running ? '<span class="pulse">●</span> REC ' : '') + LIVE.now.slice(11, 19) + '</span></div>';   // 영상에는 엔진이 쓴 글자가 위에 있다
    if (hasFrame) {
      var img = box.querySelector('img[data-cam="' + cam + '"]');
      var url = '/api/live/frame/' + encodeURIComponent(cam) + '?t=' + Date.now();
      if (!img) { box.innerHTML = '<img data-cam="' + esc(cam) + '" alt="' + esc(cam) + ' 영상" src="' + url + '">' + hud; }
      else {                                             // 깜빡이지 않게 — 새 프레임을 받은 뒤 바꾼다
        var pre = new Image(); pre.onload = function () { img.src = pre.src; }; pre.src = url;
        var h = box.querySelector('.hud'); if (h) h.outerHTML = hud;
      }
    } else if (LIVE.scene && LIVE.scene.video && LIVE.scene.camera === cam) {
      camPreview(box, x, active, hud.replace(/<span>[^<]*<\/span>/, '<span></span>'));   // 영상 첫 프레임에도 글자가 있다 — 오른쪽 시각만
    } else {
      box.innerHTML = camSVG({polys: x.polys, poly: x.id + ' 구역', active: active, persons: x.people, spark: x.ignition,
        equip: curCam === 0 ? x.equip : null, pipes: x.piping, aria: x.id + ' 카메라 화면',
        note: LIVE.video ? '' : '영상이 연결되지 않았다 — 폴리곤만 표시 · 판정은 신호(CSV · 버튼)로'}) + hud;
    }
    $('camlist').innerHTML = x.cams.map(function (c, i) { return '<button type="button" data-cam="' + i + '" class="' + (i === curCam ? 'on' : '') + '">' + esc(c) + '</button>'; }).join('');
  }
  /* 영상 장면이 붙었는데 아직 재생 전 — 그 영상의 첫 프레임에 구역을 겹쳐 보여주고, 언제 도는지 알려준다 */
  var PCOL = {hazard: '#e5584a', hazard_repair: '#ff6b5e', work: '#6cc3c8', restricted: '#e0a13a'};
  function zcol(t) { var c = (META && META.zone_types || []).filter(function (y) { return y.key === t; })[0]; return c ? c.color : (PCOL[t] || '#9aa4af'); }
  function zinfo(t) { return !PCOL[t]; }        // 관리자가 더한 종류 — 판정이 아니라 표시 · 기록용
  function camPreview(box, x, active, hud) {
    var sc = LIVE.scene;
    var key = sc.video + '|' + JSON.stringify(x.polys) + '|' + active;
    if (box.getAttribute('data-prev') !== key) {
      var svg = '<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + x.polys.map(function (p) {
        var c = zcol(p.type), info = zinfo(p.type), lit = !info && (active || p.type === 'hazard');
        return '<polygon points="' + p.points.map(function (q) { return (q[0] * 100).toFixed(2) + ',' + (q[1] * 100).toFixed(2); }).join(' ') +
          '" fill="' + c + '" fill-opacity="' + (lit ? 0.14 : 0.05) + '" stroke="' + c + '" stroke-opacity="' + (lit || info ? 1 : 0.6) + '" stroke-width="2" stroke-dasharray="' + (info ? '2 4' : '6 4') + '" vector-effect="non-scaling-stroke"/>';
      }).join('') + '</svg>';
      var labels = x.polys.map(function (p) {
        return '<span class="plab" style="left:' + (p.points[0][0] * 100).toFixed(1) + '%;top:' + (p.points[0][1] * 100).toFixed(1) + '%;color:' + zcol(p.type) + '">' + esc(p.label) + '</span>';
      }).join('');
      box.innerHTML = '<div class="prev"><img alt="' + esc(sc.name) + ' 첫 프레임" src="/api/scene/frame?video=' + encodeURIComponent(sc.video) + '&schedule=' + encodeURIComponent(LIVE.meta.schedule || '') + '">' + svg + labels +
        '<div class="wait" id="cam-wait"></div></div>' + hud;
      box.setAttribute('data-prev', key);
    } else {
      var h = box.querySelector('.hud'); if (h) h.outerHTML = hud;
    }
    $('cam-wait').innerHTML = sceneWait(true);
  }
  function sceneClock() { return LIVE.now.slice(11, 16); }
  /* 영상 장면이 언제 도는지 — 한 줄 */
  function sceneWait(onCam) {
    var sc = LIVE.scene; if (!sc) return '';
    var btn = '<button class="btn sm" type="button" data-scene-now="1">' + (sc.started ? '⏭ 다시 재생' : '⏭ 지금 재생') + '</button>';
    if (LIVE.video) return '';
    if (sc.started) return '<span>영상 장면 <b>' + esc(sc.name) + '</b> 재생이 끝났다 — 지금은 신호로만 판정한다</span>' + btn;
    if (!sc.at) return '<span>영상 장면 <b>' + esc(sc.name) + '</b> — 시각이 정해지지 않은 장면이라 저절로 돌지 않는다</span>' + btn;
    var left = mins(sc.at) - mins(sceneClock());
    if (!LIVE.sid) return '<span>시작 전 미리 보기 — <b>▶ 시작</b>을 누르면 시연 시각 <b>' + esc(sc.at) + '</b>에 이 영상이 돈다</span>' + btn;
    if (left <= 0) return '<span>영상 장면 <b>' + esc(sc.name) + '</b> 곧 시작</span>';
    var real = left * 60 / (LIVE.speed || 1);
    return '<span>' + (onCam ? '영상 대기 — ' : '영상 장면 <b>' + esc(sc.name) + '</b> 대기 — ') + '시연 시각 <b>' + esc(sc.at) + '</b>에 시작 · ' + (left >= 60 ? Math.floor(left / 60) + '시간 ' : '') + (left % 60) + '분 남음' +
      (LIVE.running ? ' (' + LIVE.speed + '×라 실제 약 ' + (real >= 90 ? Math.round(real / 60) + '분' : Math.round(real) + '초') + ')' : ' · 시계가 멈춰 있다') + '</span>' + btn;
  }
  function fmtSec(v) { v = Math.max(0, Math.round(v || 0)); return Math.floor(v / 60) + ':' + ('0' + v % 60).slice(-2); }
  function renderUndo() {
    var u = LIVE.undo, b = $('lv-undo');
    b.disabled = !u;
    b.textContent = u ? '↶ 되돌리기 — ' + u.t + ' ' + u.label : '↶ 되돌리기';
    // 시연 줄에도 같은 되돌리기 — 현장 입력 칸이 맨 아래로 내려가서, 방금 누른 입력을 위에서 바로 되돌릴 수 있게
    var bt = $('lv-undo-top'); bt.hidden = !u; if (u) { bt.textContent = '↶ ' + u.t + ' ' + u.label; bt.title = '방금 넣은 현장 입력을 되돌린다 — ' + u.t + ' ' + u.label; }
    $('lv-undo-note').textContent = !LIVE.sid ? '세션을 시작하고 넣은 입력만 되돌린다.'
      : !u ? '되돌릴 입력이 없다 — 버튼 · 입력창으로 넣은 것만 되돌린다.'
      : (u.rows ? '그 뒤 관제 기록 ' + u.rows + '건이 생겼다 — 기록은 지우지 않고 ‘입력 취소’ 기록을 덧붙인다.' : '판정 상태를 그 입력 직전으로 돌린다.') + (u.n > 1 ? ' (되돌릴 수 있는 입력 ' + u.n + '개)' : '');
  }
  $('lv-undo').addEventListener('click', function () {
    var u = LIVE && LIVE.undo; if (!u) return;
    var go = function () { return busy($('lv-undo'), api('/api/live/undo', {})).then(function (d) { flash(d.msg); tick(); }); };
    if (!u.rows) { go().catch(fail); return; }
    ask({title: '입력 되돌리기', note: u.t + ' ' + u.label + ' 을 되돌린다. 그 뒤 관제 기록 ' + u.rows + '건이 생겼는데, 관제 기록은 추가 전용이라 지우지 않는다 — 대신 ‘입력 취소’ 기록을 하나 덧붙인다.', fields: []}, go);
  });
  function renderRun() {
    renderUndo();
    var st, cls;
    if (!LIVE.sid) { st = '○ 시작 전 — 시계가 서 있다'; cls = 'idle'; }
    else if (!LIVE.running) { st = '⏸ 멈춤'; cls = 'pause'; }
    else if (LIVE.video) { st = '<i></i>영상 재생 중 ' + (LIVE.video_pos ? fmtSec(LIVE.video_pos[0]) + ' / ' + fmtSec(LIVE.video_pos[1]) : ''); cls = 'live'; }
    else { st = '<i></i>시연 중 · ' + LIVE.speed + '×'; cls = 'live'; }
    $('lv-run').className = 'runpill ' + cls;
    $('lv-run').innerHTML = st + ' <span class="clk">시연 시각 <b>' + esc(LIVE.now.slice(11, 19)) + '</b></span>';
    var line = $('lv-scn'), w = LIVE.scene ? sceneWait(false) : '';
    var sel = $('lv-scene').value, ses = (LIVE.meta && LIVE.meta.scene) || '';
    if (!w && sel && sel !== ses) {
      w = '<span>고른 영상 장면 ‘<b>' + esc(sel) + '</b>’ — 아직 이 세션에 붙지 않았다. 새 세션을 시작하거나 바로 재생한다</span><button class="btn sm" type="button" data-scene-now="form">⏭ 고른 장면 바로 재생</button>';
    }
    if (LIVE.video && LIVE.scene) w = '<span><i class="dot-live"></i>영상 장면 <b>' + esc(LIVE.scene.name) + '</b> 재생 중 · ' + esc(LIVE.scene.camera || '') + ' — 사람 · 불꽃을 프레임마다 탐지해 판정에 넣는다</span>';
    line.hidden = !w;
    if (line.getAttribute('data-w') !== w) { line.innerHTML = w; line.setAttribute('data-w', w); }
  }
  function focusCam(camId) {
    if (!LIVE || !camId) return;
    LIVE.zones.forEach(function (x) { var i = x.cams.indexOf(camId); if (i >= 0) { curZone = x.id; curCam = i; zonePickedAt = Date.now(); } });
  }
  function sceneNow(btn, body) {
    if (!body.scene) { flash('영상 장면을 먼저 고른다 — 시연 제어의 ‘영상 장면’', true); return Promise.resolve(); }
    return busy(btn, api('/api/live/scene-now', body)).then(function (d) {
      flash(d.msg); popSid = undefined;
      return api('/api/live').then(function (l) { LIVE = l; if (l.scene) focusCam(l.scene.camera); renderLive(); });
    }).catch(fail);
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-scene-now]'); if (!b) return;
    var m = LIVE && LIVE.meta || {};
    var body = b.getAttribute('data-scene-now') === 'form' || !LIVE.scene ? liveForm()
      : {schedule: m.schedule, ruleset: m.ruleset, scene: m.scene, start: m.start, speed: LIVE.speed};
    sceneNow(b, body);
  });
  /* 3축 신호판 — 축 이름은 무채색 + 아이콘(A). 그 축에 실제로 상황이 생겼을 때(tone danger)만 아이콘 칸에 그 축의 색이 든다(B).
     단계 이름은 축에 붙이지 않는다 — 축은 확인 · 가능 · 해제 · 있음 · 없음, 단계는 아래 '현재 판정' 한 곳에만. */
  var AXK = {'발생': ['leak', 'x1'], '축적': ['stack', 'x2'], '점화원': ['flame', 'x3']};
  function axState(a) { return a.state === '●' ? '있음' : a.state === '○' ? '없음' : a.state === '-' ? '—' : a.state; }
  function splitT(s) { var m = /^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*)$/.exec(String(s || '')); return m ? {t: m[1], x: m[2]} : {t: '', x: String(s || '')}; }
  var judgeOpen = false;
  function renderAxes(x) {
    var active = x.modes.length > 0;
    $('ax-title').textContent = '3축 신호판 · ' + x.id;
    $('ax-sub').textContent = active ? '켜진 모드: ' + x.modes.join(' · ') : '모드 꺼짐 — 경보 없이 무음 기록';
    if (!x.table) {
      $('axes').innerHTML = '<p class="empty">' + esc(x.id) + '에는 판정표가 걸려 있지 않다 — 모드 규칙(영상)과 무음 기록만 돈다.</p>';
      $('verdict').innerHTML = ''; $('judge').innerHTML = ''; $('jt-toggle').parentNode.hidden = true;
      renderPerson(x);
      return;
    }
    $('jt-toggle').parentNode.hidden = false;
    var rows = x.axes.map(function (a, i) {
      var key = AXK[a.name] || ['axis', 'x' + ((i % 3) + 1)];
      var st = a.tone === 'danger' ? 'on' : a.tone === 'warn' ? 'half' : a.tone === 'ok' ? 'clr' : 'off';
      var ev = a.why.length ? splitT(a.why[0]) : {t: '', x: a.why_not[0] || ''};
      var more = a.why.slice(1).map(function (w) { return splitT(w).x; }).join(' · ');
      return '<div class="axr ' + st + ' ' + key[1] + '"><span class="axi">' + ico(key[0]) + '</span><span class="axn">' + esc(a.name) + '</span>' +
        '<span class="axs">' + esc(axState(a)) + '</span><span class="axe" title="' + esc(a.why.concat(a.why.length ? [] : a.why_not.slice(0, 1)).join(' · ')) + '"><b>' + esc(ev.x || '—') + '</b>' + (more ? '<small>' + esc(more) + '</small>' : '') + '</span>' +
        '<span class="axt mono">' + esc(ev.t || '—') + '</span></div>';
    });
    $('axes').innerHTML = rows.join('<div class="axar" aria-hidden="true"></div>') + '<div class="axar to" aria-hidden="true"></div>';
    // 현재 판정 — 단계 색은 여기 한 곳에만
    var silent = !x.alerting && x.computed !== '정상';
    var hitRow = x.judge.filter(function (r) { return r.hit; })[0];
    var lvl = x.alerting ? x.level : x.computed, k = silent ? 'silent' : (LV[lvl] || 'ok');
    var dflt = x.judge[x.judge.length - 1] || {};
    var rowTxt = hitRow ? hitRow.n + '번 줄 · ' + hitRow.label : (lvl === '정상' || !x.row ? '걸린 줄 없음' + (dflt.n ? ' (' + dflt.n + '번 그 외)' : '') : x.row + '번 줄');
    var head = silent ? '무음 기록 <span class="vk">계산상 ' + esc(x.computed) + '</span>' : esc(lvl || '정상');
    var sub = silent ? '모드가 꺼져 있어 경보를 울리지 않는다 — 기록만 남긴다'
      : (lvl === '정상' ? (active ? '3축 기준으로 경보 조건이 아니다' : '모드 꺼짐 — 계산돼도 무음 기록으로만 남는다')
        : (x.since ? x.since + '부터' : '') + (x.response ? ' · 대응: ' + x.response : ''));
    $('verdict').className = 'verdict ' + k;
    $('verdict').innerHTML = '<span class="vi">' + ico(k === 'silent' ? 'silent' : k) + '</span><div class="vb"><span class="vl">현재 판정</span><b class="vh">' + head + '</b>' +
      '<span class="vr">' + esc(rowTxt) + '</span><small>' + esc(sub) + '</small></div>';
    renderPerson(x);
    // 전체 판정표 (접기) — 걸린 줄만 단계 칩, 나머지는 글자색만
    $('jt-toggle').textContent = '전체 판정표 ' + (judgeOpen ? '접기 ▾' : '보기 ▸');
    $('jt-toggle').setAttribute('aria-expanded', judgeOpen ? 'true' : 'false');
    $('jt-note').textContent = '위에서부터 처음 맞는 줄에서 멈춘다';
    $('judge').hidden = !judgeOpen;
    $('judge').innerHTML = x.judge.map(function (r) {
      var hit = r.hit, rk = LV[r.level] || 'ok';
      return '<div class="row' + (hit ? ' hit ' + (silent ? 'silent' : rk) : '') + '"><span class="n">' + (r.n || '') + '</span><span>' + esc(r.label) + '</span>' + lv(r.level, undefined, !hit) + '</div>';
    }).join('') + (x.alerting ? '' : '<p class="note" style="margin-top:6px">모드가 꺼져 있어 경보를 울리지 않는다. 판정은 무음 기록으로만 남는다' + (silent ? ' (점선이 계산된 줄)' : '') + '.</p>');
  }
  /* 사람 축 — 다른 축과 떨어진 보조 칸. 단계에는 영향 없이 대응만 바꾼다 */
  function renderPerson(x) {
    var on = LIVE.video ? x.people > 0 : !!x.present;
    var ppl = LIVE.video ? '사람 ' + x.people + '명 감지 (영상)' : (x.present ? '허가 작업 중 — 사람이 있다고 본다' : '영상 없음 · 허가 작업 없음');
    $('person').className = 'person' + (on ? ' on' : '');
    $('person').innerHTML = '<span class="axi">' + ico('user') + '</span><div class="pb"><b>' + esc(ppl) + '</b><small>단계에는 영향 없음 · 대응만 바뀐다' + (x.response && x.alerting ? ' — ' + esc(x.response) : '') + '</small></div><span class="pn mono">' + x.people + '</span>';
  }
  $('jt-toggle').addEventListener('click', function () { judgeOpen = !judgeOpen; if (LIVE) renderAxes(zoneOf(curZone)); });
  function renderZoneDetail() {
    var x = zoneOf(curZone); if (!x) return;
    renderCam(x);
    renderAxes(x);
    var today = LIVE.events.filter(function (e) { return e.zone === x.id; });
    $('zlog-title').textContent = '최근 기록 · ' + x.id + ' ' + today.length + '건 · ' + LIVE.log_src;
    $('zlog').innerHTML = today.length ? today.slice(0, 14).map(function (e) {
      return '<div><span class="t">' + e.time + '</span><span>' + esc(e.type) + ' · ' + esc(e.mode) + (e.adj ? ' · ' + tag('강화 ' + e.adj, 'adj') : '') + '</span>' + kindTag(e) + '</div>';
    }).join('') : '<p class="empty">오늘 기록 없음</p>';
    if (x.ptws.length) {
      // 격리 목록 누락 · 미첨부는 작업 전 차단 대상 — 경보 주황 + 자물쇠 (빨강은 최고 경보 · 사고에만)
      $('zptw').innerHTML = '<div class="ph"><h2>작업허가서 · 격리 상태</h2><button class="go" type="button" data-go="iso" data-ptw="' + esc(x.ptws[0].id) + '">격리 목록 대조로 →</button></div><div class="stack">' +
        x.ptws.map(function (p) {
          return '<div class="hcard' + (p.kind === 'crit' ? ' gatec' : '') + '"><div class="hd"><b class="mono">' + esc(p.id) + '</b>' + ptwTag(p.kind, p.tag) + '</div><p>' + esc(p.work) + '</p><p>' + esc(p.type) + ' · ' + esc(p.when) + ' · 발생 축 해제: <b>' + esc(p.clear) + '</b></p></div>';
        }).join('') + '</div>';
    } else { $('zptw').innerHTML = '<div class="ph"><h2>작업허가서 · 격리 상태</h2></div><p class="empty">이 구역에 걸린 허가서가 없다.</p>'; }
  }
  /* 다음 처리 — 판정 바로 아래. 숫자는 이 세션 · 전 구역 기준(고른 구역 기준이 아니다) */
  function renderNext() {
    var c = LIVE.counts;
    function row(icon, label, n, sub, btn) {
      return '<div class="nxr' + (n ? '' : ' zero') + (icon === 'gate' ? ' g' : '') + '"><span class="nxi">' + ico(icon) + '</span><div class="nxb"><b>' + label + ' <span class="mono">' + n + '</span>건</b><small>' + sub + '</small></div>' + btn + '</div>';
    }
    $('lv-next').innerHTML =
      row('doc', '시정지시서 초안', c.alerts, '경보 이상 기록에서 만든다 · 발행은 사람이', '<button class="btn sm doc" type="button" id="go-co">안전 문서로 →</button>') +
      row('doc', '수시 위험성평가 제안', c.adhoc, '위험도 12 이상 또는 중대성 4등급 1건이면 열린다', '<button class="btn sm doc" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button>') +
      (c.gates ? row('gate', '작업 전 차단', c.gates, '격리 목록 누락 등으로 작업 시작을 막은 기록 (R1)', '<button class="btn sm doc" type="button" data-go="docs" data-tab="ptw">작업허가서 점검 →</button>') : '');
  }
  function renderCtl() {
    var m = LIVE.meta;
    $('lv-play').textContent = LIVE.running ? '⏸ 멈춤' : (LIVE.sid ? '▶ 계속' : '▶ 시작');
    $('lv-speed').querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', +b.getAttribute('data-v') === LIVE.speed); });
    var nx = LIVE.next ? '다음 <b>' + esc(LIVE.next.t) + '</b> ' + esc(LIVE.next.text) : '스케줄 끝 — 버튼으로 계속';
    $('lv-status').innerHTML = (LIVE.sid ? '세션 <b>' + esc(LIVE.sid) + '</b> · ' : '미리 보기 · ') + esc(m.schedule_title) + ' · 규칙 ' + esc(m.rules_label) + ' · ' + nx +
      (LIVE.scene ? ' · 영상 장면 ' + esc(LIVE.scene.name) + ' (' + esc(LIVE.scene.at || '-') + ')' : ' · 영상 장면 없음') + (LIVE.video_note ? ' · ' + esc(LIVE.video_note) : '');
    var nh = LIVE.notes.length ? LIVE.notes.map(function (n) { return '<div><span class="t">' + n.t + '</span>' + esc(n.msg) + '</div>'; }).join('') : '<div>엔진 메모 없음 — 신호가 무엇을 바꿨는지 여기에 남는다</div>';
    if ($('lv-notes').getAttribute('data-h') !== nh) { $('lv-notes').innerHTML = nh; $('lv-notes').setAttribute('data-h', nh); }
    $('lv-notes-n').textContent = LIVE.notes.length ? '최근 ' + LIVE.notes.length + '줄 · 마지막 ' + LIVE.notes[0].t : '신호가 무엇을 바꿨는지';
  }
  /* 접는 칸 (현장 입력 · 엔진 메모) — 연 상태는 이 브라우저에 기억 */
  function drawer(id, open) {
    var sec = $(id), b = sec.querySelector('.dr-b'), h = sec.querySelector('.dr-h');
    if (open === undefined) open = b.hidden;
    b.hidden = !open; h.setAttribute('aria-expanded', open ? 'true' : 'false');
    h.querySelector('.chev').textContent = open ? '▾' : '▸';
    store('dr:' + id, open ? '1' : '0');
  }
  ['dr-input', 'dr-notes'].forEach(function (id) {
    $(id).querySelector('.dr-h').addEventListener('click', function () { drawer(id); });
    if (store('dr:' + id) === '1') drawer(id, true);
  });
  $('lv-input-jump').addEventListener('click', function () {
    drawer('dr-input', true);
    $('dr-input').scrollIntoView({behavior: 'smooth', block: 'center'});
  });
  $('lv-undo-top').addEventListener('click', function () { $('lv-undo').click(); });
  var wasVideo = false;
  function renderLive() {
    if (!curZone || !zoneOf(curZone)) curZone = (META && META.focus_zone) || LIVE.zones[0].id;
    if (LIVE.video && !wasVideo && LIVE.scene) focusCam(LIVE.scene.camera);    // 영상이 막 돌기 시작 — 그 카메라 화면으로
    wasVideo = !!LIVE.video;
    renderCtl(); renderRun(); renderZones(); renderZoneDetail(); renderNext();
  }
  function loadLive() { return api('/api/live').then(function (d) { LIVE = d; renderLive(); }).catch(fail); }

  $('z-toggle').addEventListener('click', function () {
    zonesOpen = !zonesOpen;
    $('zones').hidden = !zonesOpen; $('zstrip').hidden = zonesOpen;
    this.textContent = zonesOpen ? '간단히 보기' : '구역 전체 보기';
    this.setAttribute('aria-expanded', zonesOpen ? 'true' : 'false');
  });
  $('lv-more').addEventListener('click', function () {
    var p = $('lv-panel'); p.hidden = !p.hidden; this.setAttribute('aria-expanded', p.hidden ? 'false' : 'true');
  });
  function liveForm() {
    var sp = $('lv-speed').querySelector('button.on');
    return {schedule: $('lv-sched').value, ruleset: $('lv-rs').value, scene: $('lv-scene').value, start: $('lv-start').value, speed: sp ? +sp.getAttribute('data-v') : 10};
  }
  $('lv-new').addEventListener('click', function () {
    busy(this, api('/api/live/session', liveForm())).then(function (d) { flash(d.msg); popSid = undefined; tick(); }).catch(fail);
  });
  $('lv-scene-now').addEventListener('click', function () { sceneNow(this, liveForm()); });
  $('lv-play').addEventListener('click', function () {
    busy(this, api('/api/live/play', liveForm())).then(function (d) { flash(d.msg); tick(); }).catch(fail);
  });
  $('lv-speed').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    api('/api/live/speed', {speed: +b.getAttribute('data-v')}).then(tick).catch(fail);
  });
  $('lv-sched').addEventListener('change', fillScenes);
  function fillScenes() {
    var sc = META.schedules.filter(function (x) { return x.key === $('lv-sched').value; })[0];
    $('lv-scene').innerHTML = opt('', '영상 없음 — 신호로만 판정') + (sc ? sc.scenes.map(function (x) { return opt(x.name, x.name + ' · ' + (x.at || '-') + ' · ' + (x.camera || '') + (x.own ? ' · 그린 구역' : '')); }).join('') : '');
    if (typeof sceneHint === 'function') sceneHint();
  }
  $('lv-btns').addEventListener('click', function (e) {
    var b = e.target.closest('[data-press]'); if (!b) return;
    busy(b, api('/api/live/press', {key: b.getAttribute('data-press')})).then(function (d) { flash(d.msg + (d.notes.length ? ' — ' + d.notes.join(' · ') : '') + ' · 잘못 눌렀으면 ↶ 되돌리기'); tick(); }).catch(fail);
  });
  $('sg-put').addEventListener('click', function () {
    busy(this, api('/api/live/signal', {signal: $('sg-sig').value, zone: $('sg-zone').value, target: $('sg-tgt').value, value: $('sg-val').value}))
      .then(function (d) { flash(d.msg + (d.notes.length ? ' — ' + d.notes.join(' · ') : '')); tick(); }).catch(fail);
  });
  $('lv-send').addEventListener('click', function () {
    busy(this, api('/api/live/handoff', {})).then(function (d) { flash(d.msg); show('docs', {tab: 'handoff', hid: d.handoff_id}); }).catch(fail);
  });
  function goCorrectiveFromLive() {
    api('/api/live/corrective', {}).then(function (d) { show('docs', {tab: 'corrective', ev: d.event_id}); }).catch(fail);
  }
  document.addEventListener('click', function (e) { if (e.target.closest('#go-co')) goCorrectiveFromLive(); });

  /* ---------- 2. 격리 목록 대조 ---------- */
  var ISO = {list: [], cur: null, filter: 'all', detail: null};
  function isoDiagram(p) {
    var n = Math.max(p.lines.length, 1), H = 70 + n * 60, s = '<svg viewBox="0 0 600 ' + H + '" role="img" aria-label="' + esc(p.equipment) + ' 배관 계통도">';
    s += '<rect x="10" y="30" width="80" height="' + (n * 60 - 10) + '" rx="6" fill="var(--panel-2)" stroke="var(--line)"/><text x="50" y="' + (30 + (n * 60 - 10) / 2) + '" font-size="12" fill="var(--ink-2)" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">공급 · 밸브</text>';
    s += '<rect x="470" y="22" width="120" height="' + (n * 60 + 6) + '" rx="8" fill="var(--panel-2)" stroke="var(--ink-3)"/><text x="530" y="' + (30 + (n * 60) / 2) + '" font-size="13.5" font-weight="700" fill="var(--ink)" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">' + esc(p.equipment) + '</text>';
    p.lines.forEach(function (l, i) {
      var y = 60 + i * 60, bad = !l.in_list && !p.no_list;
      var col = p.no_list ? 'var(--ink-3)' : bad ? 'var(--crit-strong)' : 'var(--p)';
      s += '<text x="104" y="' + (y - 12) + '" font-size="11.5" font-weight="600" fill="' + (bad ? 'var(--crit)' : 'var(--ink-2)') + '" font-family="IBM Plex Sans KR,sans-serif">' + esc(l.line_id) + ' ' + esc(l.name) + (l.hazard ? ' · 가연물' : '') + (bad ? ' — 목록에 없음' : '') + '</text>';
      s += '<line x1="90" y1="' + y + '" x2="190" y2="' + y + '" stroke="' + col + '" stroke-width="5"/>';
      s += '<line x1="190" y1="' + y + '" x2="470" y2="' + y + '" stroke="' + col + '" stroke-width="5"' + (bad || l.blind === 'none' ? ' stroke-dasharray="7 5"' : '') + '/>';
      s += '<path d="M178,' + (y - 10) + ' L190,' + y + ' L178,' + (y + 10) + ' z" fill="var(--ink-2)"/><path d="M202,' + (y - 10) + ' L190,' + y + ' L202,' + (y + 10) + ' z" fill="var(--ink-2)"/>';
      var tx = '', tc = 'var(--ink-3)';
      if (l.blind === 'done') { s += '<rect x="276" y="' + (y - 16) + '" width="9" height="32" fill="var(--ok)"/>'; tx = '맹판 설치' + (l.by_step ? ' (단계 입력)' : ''); tc = 'var(--ok)'; }
      else if (l.blind === 'pending') { s += '<rect x="274" y="' + (y - 16) + '" width="13" height="32" fill="none" stroke="var(--warn)" stroke-width="2"/>'; tx = '맹판 설치 대기'; tc = 'var(--warn)'; }
      else if (l.blind === 'valve') { s += '<rect x="272" y="' + (y - 18) + '" width="18" height="36" rx="3" fill="none" stroke="var(--crit-strong)" stroke-width="1.8" stroke-dasharray="4 3"/>'; tx = '밸브만 잠김'; tc = 'var(--crit)'; }
      else { tx = '미정 (목록 없음)'; }
      s += '<text x="298" y="' + (y + 22) + '" font-size="11" font-weight="700" fill="' + tc + '" font-family="IBM Plex Sans KR,sans-serif">' + tx + '</text>';
    });
    s += '<text x="10" y="' + (H - 8) + '" font-size="10.5" fill="var(--ink-3)" font-family="IBM Plex Sans KR,sans-serif">◇ 차단밸브 · 초록 막대 맹판 · 점선은 맹판이 없는 구간</text>';
    return s + '</svg>';
  }
  function loadIso(pick) {
    return api('/api/iso').then(function (d) {
      ISO.list = d.ptws;
      if (pick) ISO.cur = pick;
      renderIsoPicks();
    }).catch(fail);
  }
  function renderIsoPicks() {
    var list = ISO.list.filter(function (p) {
      if (ISO.filter === 'open') return p.open;
      if (ISO.filter === 'bad') return p.kind === 'crit' || p.kind === 'warn';
      return true;
    });
    if (!list.some(function (p) { return p.id === ISO.cur; }) && list.length) ISO.cur = list[0].id;
    $('iso-picks').innerHTML = list.map(function (p) {
      return '<button type="button" class="pick' + (p.id === ISO.cur ? ' on' : '') + (p.new ? ' new' : '') + '" data-ptw="' + esc(p.id) + '"><span class="top2">' + z(p.zone) + ptwTag(p.kind, p.tag) + '</span><b>' + esc(p.work) + '</b><span class="s mono">' + esc(p.id) + ' · ' + esc(p.work_type) + (p.new ? ' · 방금 등록' : '') + '</span></button>';
    }).join('') || '<p class="empty">조건에 맞는 허가서가 없다.</p>';
    if (ISO.cur) loadIsoDetail(); else ['iso-kpis', 'iso-diagram', 'iso-list', 'iso-blinds', 'iso-meas'].forEach(function (i) { $(i).innerHTML = ''; });
  }
  function loadIsoDetail() {
    return api('/api/iso/' + encodeURIComponent(ISO.cur)).then(function (p) { ISO.detail = p; renderIsoDetail(p); }).catch(fail);
  }
  function renderIsoDetail(p) {
    var inList = p.lines.filter(function (l) { return l.in_list; }).length;
    var miss = p.no_list ? 0 : p.miss;
    $('iso-kpis').innerHTML =
      '<div class="kpi"><span>계통도 연결</span><b>' + p.lines.length + '</b><small>사업장 패키지 site.json · ' + esc(p.ptw.zone) + '</small></div>' +
      '<div class="kpi"><span>목록에 적힌 배관</span><b>' + (p.no_list ? '—' : inList) + '</b><small>' + (p.no_list ? '첨부 안 됨' : '격리 목록 CSV') + '</small></div>' +
      '<div class="kpi' + (miss ? ' crit' : '') + '"><span>목록에 없는 연결</span><b>' + (p.no_list ? '—' : miss) + '</b><small>작업 전 게이트 (R1)</small></div>' +
      '<div class="kpi ' + (p.clear === '인정' ? 'ok' : 'warn') + '"><span>발생 축 해제</span><b class="txt">' + esc(p.clear) + '</b><small>퍼지 ' + (p.purge_min == null ? '—' : p.purge_min) + '분 / 기준 ' + p.purge_need + '분</small></div>';
    $('iso-dg-title').textContent = '배관 계통도 — ' + p.equipment + '에 물린 것';
    $('iso-diagram').innerHTML = p.has_pid ? isoDiagram(p) : '<p class="empty">' + esc(p.ptw.zone) + '에는 배관 계통도가 없다 — 사업장 패키지 site.json 의 piping 에 넣는다.</p>';
    $('iso-list-sub').textContent = p.ptw.ptw_id + ' · ' + p.ptw.start.replace('T', ' ') + ' ~ ' + (p.ptw.end || '').slice(11, 16) + ' · ' + (p.open ? '진행 중' : '시간 밖');
    var tail = '<div class="btnrow" style="margin-top:10px">' + (miss || p.no_list ? '<button class="btn dark" type="button" id="iso-redo">목록 ' + (p.no_list ? '첨부' : '보완') + ' — 다시 등록</button>' : '') +
      '<button class="btn doc" type="button" data-go="docs" data-tab="ptw" data-ptw="' + esc(p.ptw.ptw_id) + '">작업허가서 점검 → 문서 자동화</button></div>';
    if (p.no_list) {
      $('iso-list').innerHTML = '<p class="empty">격리 목록이 첨부되지 않았다.</p><div class="bar warn"><span>' + esc(p.bar) + '</span></div>' + tail;
    } else {
      var rows = p.lines.map(function (l) {
        if (!l.in_list) return '<tr class="hit"><td class="t x">' + esc(l.line_id) + '</td><td class="x" colspan="5"><b>' + esc(l.name) + ' — 계통도에는 있는데 목록에 없다</b></td></tr>';
        function ox(v) { v = (v || '—').trim().toUpperCase(); return '<td class="c ' + (v === 'O' || v === '○' ? 'y' : v === 'X' ? 'x' : 'd') + '">' + esc(v) + '</td>'; }
        return '<tr><td class="t">' + esc(l.line_id) + '</td><td>' + esc(l.row['배관'] || l.name) + '</td><td>' + esc(l.row['격리방법'] || '-') + '</td><td class="c ' + (l.blind === 'done' ? 'y' : 'x') + '">' + (l.blind === 'done' ? 'O' : l.blind === 'valve' ? '밸브' : '대기') + '</td>' + ox(l.row['벤트']) + ox(l.row['가스측정']) + '</tr>';
      }).join('') + p.extra.map(function (x) { return '<tr class="gate"><td class="t" colspan="2">' + esc(x) + '</td><td colspan="4"><b>목록에만 있다 — 계통도 확인 필요</b></td></tr>'; }).join('');
      $('iso-list').innerHTML = '<div class="tbl"><table class="t"><thead><tr><th>line_id</th><th>배관</th><th>격리방법</th><th>맹판</th><th>벤트</th><th>측정</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
        '<div class="bar ' + (p.kind === 'mute' ? 'info' : p.kind === 'note' ? 'warn' : p.kind) + '"><span>' + esc(p.bar) + '</span></div>' + tail;
    }
    $('iso-blinds').innerHTML = p.lines.map(function (l) {
      if (p.no_list) return '<div class="stage-item"><div><b>' + esc(l.line_id) + ' ' + esc(l.name) + '</b><br><span class="s">목록이 없어 단계 입력을 받을 수 없다</span></div><span class="lv mute">대기</span></div>';
      if (l.blind === 'done') return '<div class="stage-item"><div><b>' + esc(l.line_id) + ' 맹판 설치 완료</b><br><span class="s">' + (l.by_step ? '단계 입력됨' : '격리 목록에 완료로 적힘') + '</span></div><span class="lv ok">완료</span></div>';
      if (l.blind === 'pending') return '<div class="stage-item"><div><b>' + esc(l.line_id) + ' 맹판 설치</b><br><span class="s">입력 대기</span></div><button class="btn sm" type="button" data-blind="' + esc(l.line_id) + '">완료 입력</button></div>';
      return '<div class="stage-item bad"><div><b>' + esc(l.line_id) + ' — 밸브만 잠김</b><br><span class="s">밸브 단독 격리는 발생 해제가 아니다' + (l.in_list ? '' : ' · 목록에 없다') + '</span></div><span class="lv crit">발생 확인 유지</span></div>';
    }).join('') || '<p class="empty">배관 없음</p>';
    var okN = p.meas.filter(function (m) { return m.ok; }).length;
    $('iso-meas').innerHTML = p.meas.length ?
      '<div class="tbl"><table class="t"><thead><tr><th>측정 지점</th><th>시각</th><th>값</th><th>판정 (LEL ≤ ' + p.lel_max + '%)</th></tr></thead><tbody>' +
      p.meas.map(function (m) { return '<tr><td>' + esc(m.point) + '</td><td class="t">' + esc(m.time) + '</td><td class="mono">' + esc(m.value) + '</td><td>' + (m.ok ? '<span class="lv ok">기준 이하</span>' : m.measured ? '<span class="lv crit">기준 초과</span>' : tag('측정 없음', 'wait')) + '</td></tr>'; }).join('') +
      '</tbody></table></div><div class="bar ' + (p.clear === '인정' ? 'ok' : 'warn') + '"><span>퍼지 ' + (p.purge_min == null ? '—' : p.purge_min) + '분 / 기준 ' + p.purge_need + '분 · 지점 ' + okN + '/' + p.meas.length + '</span><span>해제 ' + esc(p.clear) + '</span></div>'
      : '<p class="empty">측정 기록 없음</p>';
    $('iso-pt').innerHTML = p.meas.map(function (m) { return opt(m.line_id, m.point); }).join('');
  }
  function isoStep(kind, line, value, btn) {
    var by = $('iso-by').value.trim();
    if (!by) { flash('입력자 이름을 적는다 — 단계 입력 기록에 남는다', true); $('iso-by').focus(); return; }
    store('iso-by', by);
    busy(btn, api('/api/iso/step', {ptw_id: ISO.cur, kind: kind, line_id: line, value: value, by: by}))
      .then(function (d) { flash(d.msg); loadIso(); }).catch(fail);
  }
  $('iso-blinds').addEventListener('click', function (e) { var b = e.target.closest('[data-blind]'); if (b) isoStep('blind', b.getAttribute('data-blind'), null, b); });
  $('iso-gas').addEventListener('click', function () { isoStep('gas', $('iso-pt').value, $('iso-lel').value, this); });
  $('iso-purge-go').addEventListener('click', function () { isoStep('purge', null, $('iso-purge').value, this); });
  $('iso-filter').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; ISO.filter = b.getAttribute('data-f'); setTimeout(renderIsoPicks, 0); });
  document.addEventListener('click', function (e) { if (e.target.closest('#iso-redo') && ISO.detail) openReg(ISO.detail.ptw.zone, ISO.detail.ptw.work); });

  /* 작업허가서 등록 창 (시안 그대로 · 대조와 등록은 서버에서) */
  function regZoneNote() {
    var zz = META.zones.filter(function (x) { return x.id === $('reg-zone').value; })[0];
    $('reg-pid').textContent = zz && zz.piping ? '이 구역 계통도: ' + zz.equip + '에 물린 배관 ' + zz.lines.length + '건 (' + zz.lines.join(' · ') + ')' : '이 구역에는 배관 계통도가 없다.';
  }
  function regRead() {
    return {zone: $('reg-zone').value, work_type: $('reg-mode').value, start: $('reg-start').value, end: $('reg-end').value,
      work: $('reg-title').value.trim(), supervisor: $('reg-sup').value.trim(), workers: $('reg-n').value ? +$('reg-n').value : null,
      csv: $('reg-csv').value, no_list: $('reg-nolist').checked};
  }
  function regPreview() {
    var r = regRead(), err = $('reg-err');
    if (!r.work) { err.textContent = '작업 내용을 적는다.'; err.hidden = false; return Promise.resolve(null); }
    return api('/api/iso/check', {zone: r.zone, csv: r.csv, no_list: r.no_list}).then(function (c) {
      err.hidden = true;
      if (c.no_list) { $('reg-preview').innerHTML = '<div class="bar warn"><span>목록 미첨부로 등록된다 — 작업 전 게이트에서 막힌다</span></div>'; return r; }
      var miss = c.lines.filter(function (l) { return !l.in_list; });
      $('reg-preview').innerHTML = '<div class="tbl"><table class="t"><thead><tr><th>line_id</th><th>배관</th><th>대조</th></tr></thead><tbody>' +
        c.lines.map(function (l) { return '<tr class="' + (l.in_list ? '' : 'hit') + '"><td class="t">' + esc(l.line_id) + '</td><td>' + esc(l.name) + '</td><td>' + (l.in_list ? (l.blind === 'done' ? '<span class="lv ok">목록에 있음 · 맹판 O</span>' : '<span class="lv note">목록에 있음 · 맹판 대기</span>') : '<span class="lv crit">목록에 없음</span>') + '</td></tr>'; }).join('') +
        c.extra.map(function (x) { return '<tr class="gate"><td class="t" colspan="2">' + esc(x) + '</td><td><span class="lv warn">계통도에 없음 — 확인 필요</span></td></tr>'; }).join('') +
        '</tbody></table></div><div class="bar ' + (miss.length ? 'crit' : 'ok') + '"><span>계통도 ' + c.lines.length + '건 · 목록에 없는 연결 ' + miss.length + '건' + (c.extra.length ? ' · 계통도에 없는 줄 ' + c.extra.length + '건' : '') + '</span></div>';
      return r;
    }).catch(function (e) { err.textContent = e.message; err.hidden = false; $('reg-preview').innerHTML = ''; return null; });
  }
  function openReg(zone, work) {
    var zs = zone || (META.zones.filter(function (x) { return x.id === curZone && x.piping; })[0] || {}).id || META.focus_zone;
    $('reg-zone').value = zs; regZoneNote();
    var day = (STATUS ? STATUS.now : new Date().toISOString()).slice(0, 10);
    $('reg-start').value = day + 'T13:00'; $('reg-end').value = day + 'T17:00';
    $('reg-title').value = work || ''; $('reg-csv').value = ''; $('reg-file').value = ''; $('reg-nolist').checked = false;
    $('reg-sup').value = ''; $('reg-n').value = '';
    $('reg-preview').innerHTML = ''; $('reg-err').hidden = true;
    $('reg').hidden = false; $('reg-title').focus();
  }
  function closeReg() { $('reg').hidden = true; $('reg-open').focus(); }
  $('reg-open').addEventListener('click', function () { openReg(); });
  $('reg-close').addEventListener('click', closeReg);
  $('reg').addEventListener('click', function (e) { if (e.target === this) closeReg(); });
  $('reg-zone').addEventListener('change', function () { regZoneNote(); if ($('reg-preview').innerHTML) regPreview(); });
  $('reg-sample').addEventListener('click', function () {
    api('/api/iso-sample?zone=' + encodeURIComponent($('reg-zone').value)).then(function (d) {
      if (!d.csv) { $('reg-err').textContent = '이 구역에는 예시가 없다 (배관 계통도 없음).'; $('reg-err').hidden = false; return; }
      $('reg-csv').value = d.csv; $('reg-nolist').checked = false;
      if (!$('reg-title').value.trim()) $('reg-title').value = d.work;
      if (!$('reg-sup').value) $('reg-sup').value = d.supervisor;
      if (!$('reg-n').value) $('reg-n').value = d.workers;
      regPreview();
    }).catch(fail);
  });
  $('reg-file').addEventListener('change', function () {
    var f = this.files && this.files[0]; if (!f) return;
    var fd = new FormData(); fd.append('file', f);
    api('/api/docs/upload-csv', fd).then(function (d) { $('reg-csv').value = d.text; $('reg-nolist').checked = false; regPreview(); })
      .catch(function (e) { $('reg-err').textContent = e.message; $('reg-err').hidden = false; });
  });
  $('reg-check').addEventListener('click', regPreview);
  $('reg-save').addEventListener('click', function () {
    var btn = this;
    regPreview().then(function (r) {
      if (!r) return;
      return busy(btn, api('/api/iso/register', r)).then(function (d) {
        closeReg();
        ISO.filter = 'all';
        $('iso-filter').querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-f') === 'all'); });
        $('reg-toast').textContent = d.msg; $('reg-toast').hidden = false;
        loadIso(d.ptw_id); tickStatus();
      });
    }).catch(function (e) { $('reg-err').textContent = e.message; $('reg-err').hidden = false; });
  });

  /* ---------- 3. 이벤트 로그 — 검색 · 카테고리 필터 ----------
     거르기는 서버(control/eventlog.py)가 한다 — '보이는 경보 이상 넘기기'가 같은 조건으로 넘겨야 화면과 넘긴 목록이 같다.
     조건을 바꾸면 '적용'(또는 검색창에서 Enter)을 눌러야 표에 반영된다. */
  var MULTI = ['kinds', 'levels', 'types', 'rulesets', 'flags'];
  var FACET_T = {kinds: '종류', levels: '단계', types: '위반 유형', rulesets: '규칙셋', flags: '표시'};
  function defF() { return {q: '', mode: '전체', zone: '전체', period: '14', kinds: [], levels: [], types: [], rulesets: [], flags: [], src: ''}; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  var applied = defF(), draft = defF(), selEv = null, LOG = null;
  function normF(f) { var o = clone(f); o.q = String(o.q || '').trim().replace(/\s+/g, ' '); MULTI.forEach(function (k) { o[k] = (o[k] || []).slice().sort(); }); return o; }
  function same(a, b) { return JSON.stringify(normF(a)) === JSON.stringify(normF(b)); }
  function periodText(p) { return {today: '오늘', '14': '최근 14일', '90': '최근 90일', all: '전체 기간'}[p]; }
  function rxq(t) { return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function hl(text, toks) {               // 찾은 낱말 표시 — 글자는 먼저 이스케이프하고, 태그 안은 건드리지 않는다
    var out = esc(text);
    (toks || []).forEach(function (t) { if (t) out = out.replace(new RegExp('(' + rxq(esc(t)) + ')(?![^<]*>)', 'gi'), '<mark class="hl">$1</mark>'); });
    return out;
  }
  function facetLabel(k, v) { var x = ((LOG && LOG.facets[k]) || []).filter(function (y) { return y.v === v; })[0]; return x ? x.label : v; }
  function appliedText() {
    var parts = [];
    if (normF(applied).q) parts.push('검색 “' + normF(applied).q + '”');
    parts.push('모드 ' + applied.mode, '구역 ' + applied.zone, periodText(applied.period));
    MULTI.forEach(function (k) { if (applied[k].length) parts.push(FACET_T[k] + ' ' + applied[k].map(function (v) { return facetLabel(k, v); }).join('·')); });
    if (applied.src) parts.push('출처 ' + facetLabel('sources', applied.src));
    return '적용 중: ' + parts.join(' · ');
  }
  function renderChips() {
    if (!LOG) return;
    MULTI.forEach(function (k) {
      $('f-' + k).innerHTML = (LOG.facets[k] || []).map(function (x) {
        var on = draft[k].indexOf(x.v) >= 0;
        return '<button type="button" class="fchip' + (on ? ' on' : '') + '" aria-pressed="' + on + '" data-fk="' + k + '" data-fv="' + esc(x.v) + '">' + esc(x.label) + ' <small>' + x.n + '</small></button>';
      }).join('') || '<span class="note">기록 없음</span>';
    });
    var src = LOG.facets.sources || [];
    $('f-src').innerHTML = opt('', '전체') + src.map(function (x) { return opt(x.v, x.label + ' (' + x.n + ')', x.v === draft.src); }).join('');
    $('f-src').value = draft.src;
    var nd = ['types', 'rulesets', 'flags'].reduce(function (n, k) { return n + draft[k].length; }, 0) + (draft.src ? 1 : 0);
    $('f-more-n').textContent = nd ? '상세 조건 ' + nd + '개 고름' : '';
  }
  function updatePending() { $('f-pending').hidden = same(applied, draft); }
  function syncInputs() {
    $('f-q').value = draft.q; $('f-zone').value = draft.zone; $('f-period').value = draft.period;
    if ($('f-mode').options.length) $('f-mode').value = draft.mode;
  }
  function loadLog(o) {
    if (o && o.q) { draft = defF(); draft.q = o.q; draft.period = 'all'; applied = clone(draft); syncInputs(); }  // 다른 화면에서 ID 로 찾아 들어올 때
    return api('/api/log', applied).then(function (d) {
      LOG = d;
      $('f-mode').innerHTML = ['전체'].concat(d.modes).map(function (m) { return opt(m, m, m === draft.mode); }).join('');
      $('f-mode').value = draft.mode;
      renderChips(); renderLog();
    }).catch(fail);
  }
  function applyLog() { draft.q = normF(draft).q; applied = clone(draft); loadLog(); }
  function renderLog() {
    var rows = LOG.rows, toks = LOG.tokens || [];
    $('log-count').textContent = '이벤트 ' + LOG.n + '건 · 경보 ' + LOG.alerts + ' · 무음 ' + LOG.shadow;
    $('f-applied').textContent = appliedText();
    updatePending();
    if (!rows.some(function (e) { return e.id === selEv; })) selEv = rows.length ? rows[0].id : null;
    var extra = LOG.extra ? '<div class="extra-note note"><span>' + periodText(applied.period) + ' 밖에도 맞는 기록이 ' + LOG.extra + '건 더 있다.</span><button class="go" type="button" id="f-all-period">전체 기간으로 보기 →</button></div>' : '';
    $('log-table').innerHTML = (rows.length ? '<table class="t" style="min-width:600px"><thead><tr><th>event_id</th><th>일시</th><th>구역</th><th>모드</th><th>위반 유형</th><th>단계</th></tr></thead><tbody>' +
      rows.slice(0, 400).map(function (e) {
        var shadow = !e.alerted && (e.kind === 'stage' || e.kind === 'check');
        return '<tr class="click' + (shadow ? ' shadow' : '') + (e.id === selEv ? ' sel' : '') + '" data-ev="' + esc(e.id) + '" tabindex="0"><td class="t">' + hl(e.id, toks) + '</td><td class="t">' + hl(e.date.slice(5) + ' ' + e.time, toks) + '</td><td><span class="z">' + hl(e.zone || '-', toks) + '</span></td><td>' + hl(e.mode, toks) + '</td><td>' + hl(e.type, toks) + (e.fp ? ' <span class="lv mute">오탐</span>' : '') + (e.adj ? ' ' + tag('강화', 'adj') : '') +
          (e.hit && e.hit.length ? '<span class="hitnote">' + esc(e.hit.join(' · ')) + '에서 일치</span>' : '') + '</td><td>' + kindTag(e) + '</td></tr>';
      }).join('') + '</tbody></table>' + (rows.length > 400 ? '<p class="note">앞의 400건만 보인다 — 조건을 좁힌다.</p>' : '')
      : '<p class="empty">조건에 맞는 이벤트가 없다.</p>') + extra;
    renderLogDetail();
  }
  /* 줄을 고르면 표는 그대로 두고(스크롤 · 위치 유지) 고른 표시와 오른쪽 상세만 바꾼다 */
  function selectEv(id) {
    selEv = id;
    document.querySelectorAll('#log-table tr[data-ev]').forEach(function (tr) { tr.classList.toggle('sel', tr.getAttribute('data-ev') === id); });
    renderLogDetail();
  }
  function renderLogDetail() {
    if (!selEv) { $('log-detail').innerHTML = '<p class="empty">이벤트를 고르면 여기에 뜬다.</p>'; return; }
    var toks = (LOG && LOG.tokens) || [], want = selEv;
    api('/api/event/' + encodeURIComponent(selEv)).then(function (e) {
      if (want !== selEv) return;            // 그새 다른 줄을 골랐다
      var detect = e.kind === 'stage' || e.kind === 'check';
      var frame = e.has_frame ? '<img alt="' + esc(e.id) + ' 대표 프레임" src="/api/event/' + encodeURIComponent(e.id) + '/frame">'
        : camSVG({poly: e.zone + ' 구역', active: e.alerted, persons: 0, aria: e.id + ' 대표 프레임', note: '프레임 없음 — 영상이 없던 기록(신호 판정)이거나 무음 기록'});
      var clip = e.has_clip ? '<video controls preload="none" src="/api/event/' + encodeURIComponent(e.id) + '/clip"></video>' : '';
      var rows = [['일시', esc(e.ts_full)], ['구역 · 모드', z(e.zone) + ' ' + hl(e.zname, toks) + ' · ' + hl(e.mode, toks)], ['위반 유형', hl(e.type, toks)], ['종류', esc(e.kind_t)],
        ['판정 근거', hl((e.row ? e.row + '번 줄 · ' : '') + (e.reason || '-'), toks)], ['대응', hl(e.response || '-', toks)], ['규칙셋', hl(e.ruleset || '-', toks)],
        ['강화 중', hl(e.adj || '아님 — 기본 규칙', toks)], ['클립', esc(e.clip_path || '-')], ['출처', hl(e.src, toks)]];
      if (e.fp) rows.push(['오탐 표시', hl((e.fp_by || '예') + (e.fp_note ? ' · ' + e.fp_note : ''), toks)]);
      $('log-detail').innerHTML = '<div class="ph"><h2>' + esc(e.id) + '</h2>' + kindTag(e) + '</div>' +
        '<div class="frame">' + frame + '</div>' + (clip ? '<div class="frame" style="margin-top:8px">' + clip + '</div>' : '') +
        '<div class="tbl" style="margin-top:10px"><table class="t"><tbody>' + rows.map(function (r) { return '<tr><td class="d">' + r[0] + '</td><td' + (r[0] === '일시' ? ' class="t"' : '') + '>' + r[1] + '</td></tr>'; }).join('') + '</tbody></table></div>' +
        '<div class="btnrow" style="margin-top:10px">' + (e.alerted && detect ? '<button class="btn doc" type="button" id="ld-co">문서로 보내기 →</button>' : '') +
        '<button class="btn sm" type="button" id="ld-send">이 이벤트 넘기기</button>' +
        (detect ? '<button class="btn sm" type="button" id="ld-fp">' + (e.fp ? '오탐 취소' : '오탐 표시') + '</button>' : '') +
        (e.adj ? '<button class="go" type="button" data-go="feedback">조정 ' + esc(e.adj) + ' 보기 →</button>' : '') + '</div>' +
        '<p class="note" style="margin-top:6px">' + (!e.alerted && detect ? '모드가 꺼진 구간의 검출이라 경보 없이 남았다. 통계와 사고 경과에 쓰인다.' : '오탐 표시는 표시자와 시각이 남고, 오탐을 근거로 한 완화는 사람이 승인해야 한다.') + '</p>';
      $('log-detail').setAttribute('data-fp', e.fp ? '1' : '');
    }).catch(fail);
  }
  $('log-detail').addEventListener('click', function (e) {
    if (e.target.closest('#ld-co')) { busy(e.target, api('/api/log/corrective', {event_id: selEv})).then(function (d) { show('docs', {tab: 'corrective', ev: d.event_id}); }).catch(fail); return; }
    if (e.target.closest('#ld-send')) { busy(e.target, api('/api/log/handoff', {event_ids: [selEv]})).then(function (d) { flash(d.handoff_id + ' — 넘김'); show('docs', {tab: 'handoff', hid: d.handoff_id}); }).catch(fail); return; }
    if (e.target.closest('#ld-fp')) {
      var undo = !!$('log-detail').getAttribute('data-fp');
      ask({title: undo ? '오탐 취소 — ' + selEv : '오탐 표시 — ' + selEv, note: '표시자와 시각이 남는다. 위험성평가 집계 · 통계에서 ' + (undo ? '다시 들어간다.' : '빠진다.'),
        fields: [{k: 'by', label: '표시자', req: true}, {k: 'reason', label: '사유', area: true}]}, function (v) {
        return api('/api/log/fp', {event_id: selEv, by: v.by, reason: v.reason, undo: undo}).then(function (d) { flash(d.msg); loadLog(); });
      });
    }
  });
  $('log-send').addEventListener('click', function () {
    if (!same(applied, draft)) flash('바꾼 조건은 아직 적용 전이다 — 지금 표에 보이는 조건(적용 중)으로 넘긴다');
    busy(this, api('/api/log/handoff', {filter: applied})).then(function (d) { flash(d.handoff_id + ' — 넘김'); show('docs', {tab: 'handoff', hid: d.handoff_id}); }).catch(fail);
  });
  $('log-table').addEventListener('click', function (e) {
    if (e.target.closest('#f-all-period')) { draft.period = 'all'; applied.period = 'all'; syncInputs(); loadLog(); }
  });
  $('f-q').addEventListener('input', function () { draft.q = this.value; updatePending(); });
  $('f-q').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); applyLog(); } });
  $('f-mode').addEventListener('change', function () { draft.mode = this.value; updatePending(); });
  $('f-zone').addEventListener('change', function () { draft.zone = this.value; updatePending(); });
  $('f-period').addEventListener('change', function () { draft.period = this.value; updatePending(); });
  $('f-src').addEventListener('change', function () { draft.src = this.value; renderChips(); updatePending(); });
  document.querySelector('[data-screen="log"]').addEventListener('click', function (e) {
    var c = e.target.closest('.fchip[data-fk]'); if (!c) return;
    var k = c.getAttribute('data-fk'), v = c.getAttribute('data-fv'), i = draft[k].indexOf(v);
    if (i >= 0) draft[k].splice(i, 1); else draft[k].push(v);
    renderChips(); updatePending();
  });
  $('f-more').addEventListener('click', function () {
    var open = $('f-detail').hidden; $('f-detail').hidden = !open;
    this.setAttribute('aria-expanded', open ? 'true' : 'false'); this.textContent = open ? '상세 필터 ▴' : '상세 필터 ▾';
  });
  $('f-apply').addEventListener('click', applyLog);
  $('f-reset').addEventListener('click', function () {
    draft = defF(); applied = defF(); syncInputs(); loadLog();
  });

  /* ---------- 4. 재생 비교 ---------- */
  var RP = {list: [], cur: null, d: null, cursor: null, timer: null, speed: 10, lastAt: null, at: null};
  function loadReplay(force) {
    return api('/api/replay' + (force ? '?force=1' : '')).then(function (d) {
      RP.list = d.scenarios;
      if (!RP.list.some(function (s) { return s.key === RP.cur; })) RP.cur = RP.list.length ? RP.list[0].key : null;
      renderScPicks();
      if (RP.cur) return loadSc();
    }).catch(fail);
  }
  function renderScPicks() {
    $('sc-picks').innerHTML = RP.list.map(function (s) {
      var good = s.ok === s.n;
      return '<button type="button" class="pick' + (s.key === RP.cur ? ' on' : '') + '" data-sc="' + esc(s.key) + '"><span class="top2"><b>' + esc(s.title) + '</b></span><span class="top2"><span class="s">' + z(s.zone) + ' ' + esc(s.table) + ' 판정표</span><span class="lv ' + (good ? 'ok' : 'crit') + '">' + s.ok + '/' + s.n + (good ? ' 일치' : ' 불일치') + '</span></span></button>';
    }).join('') || '<p class="empty">사업장 패키지에 시나리오가 없다.</p>';
  }
  function loadSc() {
    stopPlay();
    return api('/api/replay/' + encodeURIComponent(RP.cur)).then(function (d) {
      RP.d = d; RP.cursor = d.times.length ? mins(d.times[d.times.length - 1]) : 0; RP.at = null; RP.lastAt = null;
      renderSc();
    }).catch(fail);
  }
  function renderSc() {
    var d = RP.d; if (!d) return;
    var names = d.variants.map(function (v) { return v.name; });
    $('sc-title').textContent = d.title;
    $('sc-sub').textContent = d.zone + ' ' + d.zname + ' · ' + d.table + ' 판정표 · ' + names.join(' ↔ ');
    var t0 = d.times.length ? mins(d.times[0]) : 0, t1 = d.times.length ? mins(d.times[d.times.length - 1]) : 1;
    $('sc-start').textContent = d.times[0] || ''; $('sc-end').innerHTML = '<b>' + esc(hhmm(RP.cursor)) + '</b> / ' + esc(d.times[d.times.length - 1] || '');
    $('sc-track').style.width = (t1 > t0 ? (RP.cursor - t0) / (t1 - t0) * 100 : 100) + '%';
    var atMap = {};
    if (RP.at && RP.cursor < t1) RP.at.states.forEach(function (s) { atMap[s.name] = s; });
    function atLine(name) {
      var s = atMap[name]; if (!s) return '';
      return '<p><b>커서 ' + esc(RP.at.t) + '</b> — ' + lv(s.level) + (s.row && s.level !== '정상' ? ' · ' + s.row + '줄' : '') + ' · ' + esc(s.axes || '') + '</p>';
    }
    if (d.variants.length >= 2) {
      $('sc-cards').innerHTML = d.variants.map(function (v) {
        return '<div class="vcard' + (v.hot ? ' hot' : '') + '"><span class="k">' + esc(v.name) + ' · 개정안 ' + esc(v.changes.join(' ') || '없음') + '</span><span class="big">' + esc(v.head) + '</span><p>' + esc(v.text) + '</p>' + atLine(v.name) +
          '<p class="note">기대 결과 ' + v.ok + '/' + v.n + ' · <button class="go" type="button" data-sc-send="' + esc(v.name) + '">이 결과 문서 자동화로 넘기기 →</button></p></div>';
      }).join('');
    } else {
      var v = d.variants[0];
      $('sc-cards').innerHTML = '<div class="vcard"><span class="k">규칙셋</span><span class="big">' + esc(v.name) + '</span><p>' + esc(v.head) + ' — ' + esc(v.text) + '</p>' + atLine(v.name) + '<p class="note"><button class="go" type="button" data-sc-send="' + esc(v.name) + '">이 결과 문서 자동화로 넘기기 →</button></p></div>' +
        '<div class="vcard' + (d.ok === d.n ? '' : ' hot') + '"><span class="k">기대 결과</span><span class="big">' + d.ok + ' / ' + d.n + '</span><p>' + (d.ok === d.n ? '모두 일치한다.' : '불일치가 있다. 아래에서 이유를 본다.') + '</p></div>';
    }
    var head = '<th>시각</th><th>신호</th><th>입력</th>' + names.map(function (n) { return '<th>' + esc(n) + '</th>'; }).join('');
    var curT = hhmm(RP.cursor), lastPast = null;
    d.rows.forEach(function (r) { if (r.t <= curT) lastPast = r.t; });
    $('sc-table').innerHTML = '<table class="t" style="min-width:' + (names.length >= 2 ? 640 : 480) + 'px"><thead><tr>' + head + '</tr></thead><tbody>' +
      d.rows.map(function (r) {
        var hot = r.cells.some(function (c) { return c[0] === 'gate' || c[0] === 'acc' || c[0] === '최고 경보'; });
        var cells = r.cells.map(function (c) {
          if (c[0] === 'gate') return '<td>' + chip('작업 전 차단', 'crit') + '</td>';
          if (c[0] === 'acc') return '<td>' + chip('사고', 'crit') + '</td>';
          var rest = String(c[1] || '').replace(c[0], '').replace(/^\s*·\s*/, '');
          return '<td>' + (c[0] && c[0] !== '정상' ? lv(c[0]) + ' ' : '') + '<span class="d">' + esc(c[0] === '정상' ? c[1] : rest) + '</span></td>';
        }).join('');
        var cls = (r.t === lastPast && RP.cursor < mins(d.times[d.times.length - 1]) ? 'sel' : hot ? 'hit' : '');
        return '<tr class="' + cls + '"' + (r.t > curT ? ' style="opacity:.35"' : '') + '><td class="t">' + r.t + '</td><td>' + esc(r.signals) + '</td><td>' + esc(r.source) + '</td>' + cells + '</tr>';
      }).join('') + '</tbody></table>';
    $('sc-expect').innerHTML = d.expect.length ? d.expect.map(function (x) {
      return '<div class="' + (x.ok ? '' : 'bad') + '"><b class="mk ' + (x.ok ? 'y' : 'x') + '">' + (x.ok ? '✓' : '✗') + '</b><span><b>' + esc(x.variant) + '</b> · ' + esc(x.msg) + '</span></div>';
    }).join('') : '<p class="empty">이 시나리오에는 기대 결과가 없다.</p>';
    $('sc-play').textContent = RP.timer ? '⏸ 멈춤' : '▶ 재생';
  }
  function fetchAt() {
    var t = hhmm(RP.cursor);
    if (t === RP.lastAt) return;
    RP.lastAt = t;
    api('/api/replay/' + encodeURIComponent(RP.cur) + '/at?t=' + t).then(function (d) { RP.at = d; renderSc(); }).catch(function () {});
  }
  function stopPlay() { if (RP.timer) { clearInterval(RP.timer); RP.timer = null; } }
  $('sc-play').addEventListener('click', function () {
    if (!RP.d || !RP.d.times.length) return;
    if (RP.timer) { stopPlay(); renderSc(); return; }
    var t0 = mins(RP.d.times[0]), t1 = mins(RP.d.times[RP.d.times.length - 1]);
    if (RP.cursor >= t1) RP.cursor = t0;
    RP.timer = setInterval(function () {
      RP.cursor = Math.min(t1, RP.cursor + RP.speed * 0.25 / 60 * 6);   // 1× = 시연 시각 1분을 10초에 (60× = 1초에 6분)
      if (RP.cursor >= t1) stopPlay();
      renderSc(); fetchAt();
    }, 250);
    renderSc(); fetchAt();
  });
  $('sc-speed').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) RP.speed = +b.getAttribute('data-v'); });
  $('sc-trackbar').addEventListener('click', function (e) {
    if (!RP.d || !RP.d.times.length) return;
    var r = this.getBoundingClientRect(), f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    var t0 = mins(RP.d.times[0]), t1 = mins(RP.d.times[RP.d.times.length - 1]);
    RP.cursor = t0 + f * (t1 - t0); renderSc(); fetchAt();
  });
  $('sc-all').addEventListener('click', function () { busy(this, loadReplay(true)).then(function () { flash('전체 다시 돌렸다 — control/records/replay/'); }); });
  $('sc-import').addEventListener('click', function () { $('sc-zip').click(); });
  $('sc-zip').addEventListener('change', function () {
    var f = this.files && this.files[0]; if (!f) return;
    var fd = new FormData(); fd.append('file', f);
    api('/api/replay/import', fd).then(function (d) { flash(d.msg); RP.cur = d.key; loadReplay(); }).catch(fail).finally(function () { $('sc-zip').value = ''; });
  });
  $('sc-cards').addEventListener('click', function (e) {
    var b = e.target.closest('[data-sc-send]'); if (!b) return;
    api('/api/replay/' + encodeURIComponent(RP.cur) + '/handoff', {variant: b.getAttribute('data-sc-send')}).then(function (d) {
      flash(d.handoff_id + ' — 재생 결과를 넘겼다 (조사표 초안 시험 등)'); show('docs', {tab: 'handoff', hid: d.handoff_id});
    }).catch(fail);
  });

  /* ---------- 5. 피드백 · 조정 로그 ----------
     짧은 루프(자동 · 기한부 · 감시 강도 강화만) | 긴 루프(사람 확정 · 규칙 변경 다섯 단계) | 조정 로그(상태가 바뀔 때마다 한 줄).
     판단은 control/feedback.py · 위험성평가(docgen) — 여기는 모양만. */
  var FB = {d: null, rc: null, review: false, open: {}, logAll: false, lf: null};
  // 피드백 화면의 처리 상태 — 위험 단계 색(빨강 · 주황 · 앰버)은 쓰지 않는다. 자동 조정 = 청록, 사람 처리 대기 = 무채색 테두리, 반려 · 승격 = 진한 무채색
  var LOG_K = {applied: 'adj', scheduled: 'wait', pending: 'wait', approved: 'ok', expired: 'mute', reverted: 'mute', rejected: 'mute',
    promoted: 'ink', toggle: 'mute', signed: 'wait', confirmed: 'ok', reflected: 'ok', ra_rejected: 'ink', rule_rejected: 'ink', restored: 'mute'};
  var PH_K = {none: 'mute', draft: 'wait', worker: 'wait', rejected: 'ink', ra_rejected: 'ink', rejected_final: 'ink', confirmed: 'info', live: 'ok'};
  var ST_K = {done: 'ok', now: 'info', wait: 'mute', rej: 'ink'};
  function ymd(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function fbDefLF(now) {
    var t = new Date(now.slice(0, 10) + 'T00:00:00');
    return {from: ymd(new Date(t.getTime() - 13 * 86400000)), to: now.slice(0, 10), zone: '', loop: '', state: '', actor: '', q: ''};
  }
  function syncLF() { var f = FB.lf; $('fbl-from').value = f.from; $('fbl-to').value = f.to; $('fbl-zone').value = f.zone; $('fbl-loop').value = f.loop; $('fbl-state').value = f.state; $('fbl-actor').value = f.actor; $('fbl-q').value = f.q; }
  function loadFb() {
    return api('/api/feedback').then(function (d) {
      FB.d = d;
      if (!FB.lf) { FB.lf = fbDefLF(d.now); }
      renderFb();
    }).catch(fail);
  }
  function fbKpi(label, n, sub, cls, tail) {
    return '<div class="kpi' + (cls ? ' ' + cls : '') + '"><div class="kb"><span>' + esc(label) + '</span><b>' + n + '<small>건</small></b><small>' + sub + '</small></div>' + (tail || '') + '</div>';
  }
  function renderFb() {
    var d = FB.d, k = d.kpis, t = k.trend;
    $('fb-banner').textContent = '자동 조정은 감시 강도만 강화 방향으로 ' + d.expire_h + '시간 기한부로 올린다. 규칙 자체 변경은 긴 루프(위험성평가 확정)에서만 반영된다.';
    var mx = Math.max.apply(null, t.vals.concat([1]));
    var spark = '<div class="spark" role="img" aria-label="최근 14일 날짜별 조정 건수">' + t.vals.map(function (v, i) {
      return '<i' + (v ? '' : ' class="z"') + ' style="height:' + (v ? Math.max(14, v / mx * 100) : 6).toFixed(0) + '%" title="' + t.days[i] + ' · ' + v + '건"></i>'; }).join('') + '</div>';
    var delta = t.delta === 0 ? '전주와 같음 (' + t.this_week + '건)' : '전주 대비 <span class="' + (t.delta > 0 ? 'up' : 'dn') + '">' + (t.delta > 0 ? '+' : '') + t.delta + '건' +
      (t.pct != null ? ' (' + (t.delta > 0 ? '▲' : '▼') + Math.abs(t.pct) + '%)' : '') + '</span>';
    var waitN = k.pending + k.long_wait;
    $('fb-kpis').innerHTML =
      fbKpi('활성 자동 조정', k.active, '짧은 루프 · ' + d.expire_h + '시간 안에 만료' + (k.active_zones.length ? ' · ' + esc(k.active_zones.join(' · ')) : '')) +
      fbKpi('승인 대기', waitN, '짧은 루프(승인형) ' + k.pending + ' · 긴 루프 ' + k.long_wait + (k.long_wait ? ' (' + esc(k.long_wait_ids.join(' ')) + ')' : ''), waitN ? 'waitk' : '') +
      fbKpi('최근 14일 조정', k.n14, delta, '', spark) +
      '<div class="kpi"><div class="kb"><span>현재 운영 규칙셋</span><b class="txt">v' + esc(k.version) + '</b><small>' + (k.last_ts ? '최근 반영 ' + esc(k.last_ts) : '개정 없음 — 기본 규칙') +
        (k.ids.length ? ' · ' + esc(k.ids.join(' · ')) : '') + '</small></div><button class="btn sm" type="button" id="fb-rs-hist">변경 이력 보기</button></div>';
    // 짧은 루프
    $('fb-mode-badge').textContent = k.mode === 'auto' ? '자동' : '승인형';
    $('fb-mode-badge').className = 'lv ' + (k.mode === 'auto' ? 'adj' : 'wait');
    $('fb-mode-sub').textContent = d.expire_h + '시간 · 감시 강도 강화만 (규칙 자체 변경 없음)' + (k.mode === 'auto' ? '' : ' · 승인형 — 사람이 승인해야 적용');
    renderFbOpen();
    $('fb-crit-short').innerHTML = d.criteria_short.map(critLi).join('');
    var bmx = Math.max.apply(null, d.zone_counts.map(function (x) { return x.n; }).concat([d.promote.count]));
    $('fb-bars').innerHTML = d.zone_counts.length ? d.zone_counts.map(function (x) {
      return '<div class="hb" title="' + esc(x.zone + ' ' + x.name) + '"><span>' + esc(x.zone) + ' ' + esc(x.name) + '</span><div class="tr"><i class="' + (x.n >= d.promote.count ? 'k' : x.n >= d.promote.count - 1 ? 'k2' : 'p') + '" style="width:' + (x.n / bmx * 100).toFixed(0) + '%"></i></div><b>' + x.n + '</b></div>';
    }).join('') : '<p class="empty">최근 14일 조정 없음</p>';
    $('fb-bars-note').textContent = '진한 막대 = 같은 구역 ' + d.promote.within_days + '일 안에 ' + d.promote.count + '회 — 긴 루프로 승격하는 기준';
    $('fb-rules').innerHTML = [
      '<b>감시 강도만 강화 방향으로</b> 올린다 — 알림 단계 상향(구역당 최대 +' + d.max_up + ') · 꺼진 구역 규칙 임시 활성화 · 관리자 알림. 규칙 내용은 바꾸지 않는다.',
      '최대 <b>' + d.expire_h + '시간</b> 적용 후 자동 만료 — 연장하지 않는다.',
      '<b>만료되거나 사람이 되돌릴 때만</b> 원래 값으로 (되돌리기는 사유 필수).',
      '강화 기간에 잡힌 기록은 <b>기준선에서 뺀다</b> — 자기강화 폭주 방지.',
      '같은 구역 ' + d.promote.within_days + '일 안에 ' + d.promote.count + '회면 <b>긴 루프로 승격</b>한다.'
    ].map(function (x) { return '<li>' + x + '</li>'; }).join('');
    // 긴 루프
    var wait = d.rcs.filter(function (r) { return r.phase === 'worker' || r.phase === 'draft'; });
    if (!d.rcs.some(function (r) { return r.id === FB.rc; })) FB.rc = ((wait[0] || d.rcs[0]) || {}).id;
    $('rc-picks').innerHTML = d.rcs.map(function (r) {
      var dot = {worker: 'now', draft: 'now', confirmed: 'done', live: 'done', rejected: 'rej', ra_rejected: 'rej', rejected_final: 'rej'}[r.phase] || '';
      return '<button type="button" class="rc-chip' + (r.id === FB.rc ? ' on' : '') + '" data-rc="' + esc(r.id) + '" aria-pressed="' + (r.id === FB.rc) + '" title="' + esc(r.text) + '"><i class="' + dot + '"></i><b>' + esc(r.id) + '</b>' + esc(r.phase_text) + '</button>';
    }).join('') || '<p class="empty">규칙셋 변경안이 없다 — 사업장 패키지 rules.json › rule_changes</p>';
    renderRc();
    $('fb-prop-h').textContent = '긴 루프로 올라온 제안 ' + d.proposals.length + '건';
    $('fb-prop').innerHTML = d.proposals.length ? d.proposals.map(function (x) {
      return '<div class="pr">' + chip(x.kind, x.kind === '급감' ? 'mute' : x.kind === '승격' || x.kind === '위험도' ? 'ink' : 'wait') +
        '<div class="tx"><p>' + z(x.zone) + ' ' + esc(x.zname) + ' — ' + esc(x.text) + '</p>' + (x.ref ? '<small class="mono">' + esc(x.ref) + '</small>' : '') + '</div>' +
        '<span class="t">' + esc(x.ts.slice(5)) + '</span>' + (x.go ? '<button class="go" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button>' : '<span class="note">점검 알림</span>') + '</div>';
    }).join('') : '<p class="empty">긴 루프로 올릴 제안이 없다.</p>';
    $('fb-crit-long').innerHTML = d.criteria_long.map(critLi).join('');
    renderFbLog();
    updLeft();
  }
  /* 짧은 루프 카드 — '적용 중'과 '승인 대기'를 두 묶음으로 나눈다 */
  function renderFbOpen() {
    var d = FB.d, live = d.open.filter(function (a) { return a.state !== 'pending'; }), pend = d.open.filter(function (a) { return a.state === 'pending'; });
    if (!d.open.length) { $('fb-open').innerHTML = '<p class="empty">걸려 있는 자동 조정이 없다. 이탈 조건에 걸리면 여기에 뜬다.</p>'; return; }
    function grp(cls, icon, title, sub, list, empty) {
      return '<div class="fb-grp ' + cls + '"><div class="fb-gh">' + ico(icon) + '<b>' + title + ' <span class="mono">' + list.length + '</span></b><span class="sub">' + sub + '</span></div>' +
        (list.length ? list.map(adjCard).join('') : '<p class="empty sm">' + empty + '</p>') + '</div>';
    }
    $('fb-open').innerHTML = grp('g-live', 'adj', '적용 중', '지금 감시를 강화하고 있다 · 만료되면 원래 값으로', live, '적용 중인 조정이 없다') +
      grp('g-wait', 'wait', '승인 대기', '사람이 승인해야 적용된다', pend, '승인을 기다리는 조정이 없다');
  }
  function critLi(c) { return '<li><b>' + esc(c[0]) + '</b><span>' + esc(c[1]) + '</span><em>' + esc(c[2]) + '</em></li>'; }
  function adjCard(a) {
    var pend = a.state === 'pending', open = !!FB.open[a.adj_id], id = esc(a.adj_id);
    var target = [a.zone_rule ? '구역 규칙 임시 활성화(무음 → 경보)' : '', a.notify ? '알림 대상에 관리자 추가' : ''].filter(Boolean).join(' · ');
    var btns = pend
      ? '<button class="btn sm dark" type="button" data-adj="approve" data-id="' + id + '">승인</button><button class="btn sm" type="button" data-adj="reject" data-id="' + id + '">거부</button>'
      : '<button class="btn sm" type="button" data-adj="revert" data-id="' + id + '">↶ 되돌리기</button><button class="btn sm" type="button" data-adj="promote" data-id="' + id + '">개정 제안으로 승격</button>';
    btns += '<button class="btn sm" type="button" data-adj-more="' + id + '" aria-expanded="' + open + '">' + (open ? '접기' : '상세 보기') + '</button>';
    var more = open ? '<div class="more">' +
      '<p><b>근거 이벤트</b> ' + (a.evidence.length ? '<span class="evlinks">' + a.evidence.map(function (x) { return '<button class="go" type="button" data-go="log" data-q="' + esc(x) + '">' + esc(x) + '</button>'; }).join('') + '</span>' : '—') + '</p>' +
      '<p><b>처리 이력</b></p><ol class="hist">' + a.history.map(function (h) { return '<li><span class="mono">' + esc(h.ts) + '</span> · ' + esc(h.state) + ' · ' + esc(h.actor) + (h.note ? ' · ' + esc(h.note) : '') + '</li>'; }).join('') + '</ol>' +
      '<p class="note mono">' + id + ' · ' + (a.feedback_mode === 'approval' ? '승인형' : '자동') + ' 방식으로 생성 · ' + esc(a.mode) + ' · ' + esc(a.violation_type) + (a.sample ? ' · 예시 데이터' : '') + '</p></div>' : '';
    return '<div class="acard' + (pend ? ' pending' : '') + (a.severe ? ' severe' : '') + '">' +
      '<div class="hd"><b>' + z(a.zone) + ' ' + esc(a.zname) + '</b><span class="btnrow" style="gap:6px">' + (a.severe ? chip('중대성 4', 'ink') : '') + (pend ? tag(a.state_label, 'wait') : a.state_key === 'applied' ? tag(a.state_label, 'adj') : chip(a.state_label, 'mute')) + '</span></div>' +
      '<dl><dt>조정 대상</dt><dd>감시 강도' + (target ? ' — ' + esc(target) : '') + '</dd>' +
      '<dt>알림 단계</dt><dd><span class="lvchg" title="1 = 현장 · 2 = 현장 + 관리자">' + chip('단계 ' + a.level_before, 'mute') + '→' + chip('단계 ' + a.level_after, 'adj') + '</span></dd>' +
      (pend ? '<dt>시작</dt><dd>승인하면 그때부터 ' + FB.d.expire_h + '시간</dd>'
            : '<dt>시작</dt><dd class="mono">' + esc(a.start) + '</dd><dt>만료 예정</dt><dd><span class="mono">' + esc(a.expires_at.replace('T', ' ')) + '</span><span class="left" data-exp="' + esc(a.expires_at) + '"></span></dd>') +
      '<dt>조정 사유</dt><dd>' + esc(a.reason) + '</dd></dl>' +
      '<div class="btnrow">' + btns + '</div>' + more + '</div>';
  }
  function updLeft() {
    var now = new Date((STATUS && STATUS.now) || (FB.d && FB.d.now));
    document.querySelectorAll('#fb-open [data-exp]').forEach(function (el) {
      var ms = new Date(el.getAttribute('data-exp')) - now;
      if (ms <= 0) { el.textContent = '(만료 — 정리 전)'; el.classList.add('soon'); return; }
      var s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
      el.textContent = '(남은 시간 ' + h + ':' + ('0' + m).slice(-2) + ':' + ('0' + x).slice(-2) + ')';
      el.classList.toggle('soon', ms < 6 * 3600 * 1000);
    });
  }
  function curRc() { return FB.d.rcs.filter(function (x) { return x.id === FB.rc; })[0]; }
  function renderRc() {
    var r = curRc();
    if (!r) { $('rc-steps').innerHTML = ''; $('rc-detail').innerHTML = '<p class="empty">변경안을 고른다.</p>'; return; }
    $('rc-steps').innerHTML = r.steps.map(function (s, i) {
      return '<li class="' + s.state + '"><span class="n">' + (s.state === 'done' ? '✓' : s.state === 'rej' ? '✕' : i + 1) + '</span><div class="tx"><div class="t1"><b>' + esc(s.name) + '</b>' + chip(s.label, ST_K[s.state]) + '</div><small>' + esc(s.sub) + '</small></div></li>';
    }).join('');
    var ev = r.evidence.length ? r.evidence.length + '건 <span class="evlinks">' + r.evidence.map(function (x) { return '<button class="go" type="button" data-go="log" data-q="' + esc(x) + '">' + esc(x) + '</button>'; }).join('') + '</span>' : '—';
    if (r.accidents.length) ev += ' · 사고 ' + esc(r.accidents.join(', '));
    var chg = function (k, cls) { return r.change.map(function (c) { return '<span class="p">' + esc(c.path) + '</span><code class="' + cls + '">' + esc(c[k]) + '</code>'; }).join(''); };
    var rejTitle = r.can_reject ? '' : r.phase === 'none' || r.phase === 'draft' ? '관리자 서명 뒤 · 근로자 확인 전에만 반려한다' : r.phase === 'confirmed' || r.phase === 'live' ? '확정된 변경은 새 위험성평가로만 되돌린다' : '이미 반려됐다';
    var dl = '<dl><dt>변경안</dt><dd><b class="mono">' + esc(r.id) + '</b> ' + esc(r.text) + '</dd>' +
      '<dt>구역</dt><dd>' + (r.zones.length ? r.zones.map(function (x) { return z(x.id) + ' ' + esc(x.name); }).join(' · ') : '—') + '</dd>' +
      '<dt>위험성평가</dt><dd>' + (r.ra_id ? '<span class="mono">' + esc(r.ra_id) + '</span> · ' + esc(r.ra_kind) + ' · ' + esc(r.ra_state) : r.phase === 'draft' ? '초안 (서명 전)' : '— 연결 전') + '</dd>' +
      '<dt>변경 전</dt><dd class="chg">' + chg('before', 'b') + '</dd><dt>변경 후</dt><dd class="chg">' + chg('after', 'a') + '</dd>' +
      '<dt>제안자</dt><dd>' + esc(r.proposer || '—') + '</dd><dt>생성 일시</dt><dd class="mono">' + esc(r.created || '—') + '</dd>' +
      '<dt>제안 사유</dt><dd>' + esc(r.reason || (r.phase === 'none' ? '위험성평가 감소대책에 ' + r.id + ' 가 연결되면 채워진다' : '—')) + '</dd>' +
      '<dt>첨부 근거</dt><dd>' + ev + '</dd></dl>';
    var review = FB.review ? '<div class="rc-review"><div class="diff">' + r.diff.map(function (x) { return '<div class="' + x[0] + '">' + esc(x[1]) + '</div>'; }).join('') + '</div>' +
      (r.rows.length ? r.rows.map(function (x) { return '<div class="hcard soft"><div class="hd"><b>' + z(x.zone) + ' ' + esc(x.mode || '') + ' · ' + esc(x.violation_type || '') + '</b>' + chip('위험도 ' + x.score + ' · ' + (x.grade || ''), 'ink') + '</div><p>' + esc(x.hazard) + '</p>' + (x.cause ? '<p>' + esc(x.cause) + '</p>' : '') + '<p class="mono">' + esc(x.measures.join(' / ')) + '</p></div>'; }).join('') : '<p class="note">연결된 평가표 행이 아직 없다.</p>') + '</div>' : '';
    $('rc-detail').innerHTML = '<div class="bh"><b>현재 선택된 변경안</b>' + chip(r.phase_text, PH_K[r.phase]) + '</div>' + dl +
      (r.rejection ? '<div class="bar ink rej"><span>반려 · ' + esc(r.rejection.name) + (r.rejection.role ? ' (' + esc(r.rejection.role) + ')' : '') + ' · ' + esc(r.rejection.ts) + '</span><span>' + esc(r.rejection.note) + '</span></div>' : '') +
      (r.demo_on ? '<p class="note" style="margin-top:6px">지금 관제 세션에 시연용으로 켜져 있다 — 확정 전이다.</p>' : '') +
      '<div class="btnrow" style="margin-top:10px">' +
        '<button class="btn sm' + (FB.review ? ' dark' : '') + '" type="button" id="rc-review" aria-pressed="' + FB.review + '">검토</button>' +
        (r.can_restore ? '<button class="btn sm" type="button" data-rc-act="restore">반려 취소</button>'
                       : '<button class="btn sm" type="button" data-rc-act="reject"' + (r.can_reject ? '' : ' disabled title="' + esc(rejTitle) + '"') + '>반려</button>') +
        '<button class="btn sm doc" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button>' +
        (r.phase === 'worker' || r.phase === 'rejected' ? '<button class="go" type="button" data-go="voice">근로자 확인 →</button>' : '') +
      '</div>' + review;
  }
  $('rc-detail').addEventListener('click', function (e) {
    if (e.target.closest('#rc-review')) { FB.review = !FB.review; renderRc(); return; }
    var b = e.target.closest('[data-rc-act]'); if (!b || b.disabled) return;
    var act = b.getAttribute('data-rc-act'), r = curRc();
    ask({title: (act === 'reject' ? '변경안 반려 — ' : '반려 취소 — ') + r.id,
      note: act === 'reject' ? '이 변경안만 규칙셋에 올리지 않는다. ' + r.ra_id + ' 은 그대로 근로자 확인을 기다리고, 확정할 때 ' + r.id + ' 만 빠진다. 처리자 · 사유가 위험성평가 기록과 조정 로그에 남는다.'
                             : r.id + ' 를 다시 ' + r.ra_id + ' 근로자 확인 대상으로 되돌린다.',
      fields: [{k: 'actor', label: '처리자', req: true}, {k: 'role', label: '역할', options: ['관리자', '안전관리자', '근로자 대표']},
               {k: 'note', label: act === 'reject' ? '반려 사유 (필수)' : '사유', area: true, req: act === 'reject'}]}, function (v) {
      return api('/api/feedback/rule', {action: act, rule_id: r.id, actor: v.actor, role: v.role, note: v.note}).then(function (d) { flash(d.msg); loadFb(); tickStatus(); });
    });
  });
  // 조정 로그 — 화면에서 바로 거른다 (작은 표 · 서버에 다시 묻지 않는다)
  function fbLogRows() {
    var f = FB.lf, toks = String(f.q || '').toLowerCase().split(/\s+/).filter(Boolean);
    return FB.d.log.filter(function (r) {
      var day = r.ts.slice(0, 10);
      if (f.from && day < f.from) return false;
      if (f.to && day > f.to) return false;
      if (f.zone && r.zone.split(' · ').indexOf(f.zone) < 0) return false;
      if (f.loop && r.loop !== f.loop) return false;
      if (f.state && r.label !== f.state) return false;
      if (f.actor && r.actor !== f.actor) return false;
      if (toks.length) {
        var hay = [r.id, r.text, r.note, r.actor, r.zone, r.zname, r.kind, r.label].join(' ').toLowerCase();
        if (!toks.every(function (t) { return hay.indexOf(t) >= 0; })) return false;
      }
      return true;
    });
  }
  function uniq(xs) { var o = []; xs.forEach(function (x) { if (x && o.indexOf(x) < 0) o.push(x); }); return o; }
  function renderFbLog() {
    var d = FB.d, f = FB.lf;
    $('fbl-zone').innerHTML = opt('', '전체') + d.zones.map(function (x) { return opt(x.id, x.id + ' ' + x.name); }).join('');
    $('fbl-state').innerHTML = opt('', '전체') + uniq(d.log.map(function (r) { return r.label; })).map(function (x) { return opt(x, x); }).join('');
    $('fbl-actor').innerHTML = opt('', '전체') + uniq(d.log.map(function (r) { return r.actor; })).sort().map(function (x) { return opt(x, x); }).join('');
    syncLF();
    var rows = fbLogRows(), shown = FB.logAll ? rows : rows.slice(0, 12), toks = String(f.q || '').split(/\s+/).filter(Boolean);
    $('fb-log').innerHTML = shown.length ? shown.map(function (r) {
      var lk = r.kind === '승격' ? 'ink' : r.loop === 'short' ? 'adj' : 'mute';
      return '<tr class="' + r.loop + (r.kind === '승격' ? ' promo' : '') + '"><td class="t lb">' + esc(r.ts.slice(5)) + '</td><td>' + chip(r.kind, lk) + '</td><td class="id">' + hl(r.id, toks) + '</td>' +
        '<td>' + hl(r.text, toks) + (r.sample ? ' <span class="lv mute">예시</span>' : '') + '</td><td>' + (r.zone ? r.zone.split(' · ').map(function (x) { return z(x); }).join(' ') : '—') + '</td>' +
        '<td>' + chip(r.label, LOG_K[r.state] || 'mute') + '</td><td class="t">' + esc(r.expires || '—') + '</td><td>' + hl(r.actor || '—', toks) + '</td><td class="note2">' + hl(r.note || '', toks) + '</td></tr>';
    }).join('') : '<tr><td colspan="9" class="d">조건에 맞는 기록이 없다</td></tr>';
    $('fbl-count').textContent = rows.length + '건' + (rows.length !== d.log.length ? ' · 전체 ' + d.log.length + '건 중' : '') + (!FB.logAll && rows.length > 12 ? ' · 앞의 12건만 보인다' : '');
    $('fbl-more').hidden = rows.length <= 12;
    $('fbl-more').textContent = FB.logAll ? '접기 ↑' : '전체 보기 →';
  }
  [['fbl-from', 'from'], ['fbl-to', 'to'], ['fbl-zone', 'zone'], ['fbl-loop', 'loop'], ['fbl-state', 'state'], ['fbl-actor', 'actor']].forEach(function (x) {
    $(x[0]).addEventListener('change', function () { FB.lf[x[1]] = this.value; renderFbLog(); });
  });
  $('fbl-q').addEventListener('input', function () { FB.lf.q = this.value; renderFbLog(); });
  $('fbl-reset').addEventListener('click', function () { FB.lf = fbDefLF(FB.d.now); renderFbLog(); });
  $('fbl-more').addEventListener('click', function () { FB.logAll = !FB.logAll; renderFbLog(); });
  $('fbl-csv').addEventListener('click', function () {
    var rows = fbLogRows();
    if (!rows.length) { flash('내보낼 줄이 없다', true); return; }
    var q = function (v) { v = String(v == null ? '' : v); return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var lines = [['시각', '구분', 'ID', '내용', '구역', '결과', '만료', '처리자', '사유·비고']].concat(rows.map(function (r) { return [r.ts, r.kind, r.id, r.text, r.zone, r.label, r.expires, r.actor, r.note]; }));
    var blob = new Blob(['﻿' + lines.map(function (l) { return l.map(q).join(','); }).join('\r\n')], {type: 'text/csv;charset=utf-8'});
    var url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = '조정로그_' + (FB.lf.from || '처음') + '_' + (FB.lf.to || '끝') + '.csv';
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 0);
    flash('조정 로그 ' + rows.length + '줄을 내보냈다 — 지금 거른 조건 그대로');
  });
  document.querySelector('[data-screen="feedback"]').addEventListener('click', function (e) {
    if (e.target.closest('#fb-rs-hist')) {
      FB.lf = fbDefLF(FB.d.now); FB.lf.from = ''; FB.lf.loop = 'long'; FB.logAll = true; renderFbLog();
      $('fbl').scrollIntoView({behavior: 'smooth', block: 'start'}); return;
    }
    if (e.target.closest('#fb-pr-open')) {
      var open = $('fb-pr').hidden; $('fb-pr').hidden = !open;
      var b = $('fb-pr-open'); b.setAttribute('aria-expanded', open ? 'true' : 'false'); b.textContent = open ? '운영 원칙 접기 ↑' : '운영 원칙 자세히 보기 →';
      return;
    }
    var m = e.target.closest('[data-adj-more]');
    if (m) { var id = m.getAttribute('data-adj-more'); FB.open[id] = !FB.open[id]; renderFbOpen(); updLeft(); }
  });
  $('fb-open').addEventListener('click', function (e) {
    var b = e.target.closest('[data-adj]'); if (!b) return;
    var act = b.getAttribute('data-adj'), id = b.getAttribute('data-id');
    var need = act === 'revert' || act === 'reject';
    var T = {revert: '되돌리기', approve: '승인', reject: '거부', promote: '개정 제안으로 승격'};
    ask({title: T[act] + ' — ' + id, note: '처리자' + (need ? '와 사유' : '') + '가 조정 로그에 남는다.',
      fields: [{k: 'actor', label: '처리자', req: true}, {k: 'note', label: '사유' + (need ? ' (필수)' : ''), area: true, req: need}]}, function (v) {
      return api('/api/feedback/act', {action: act, adj_id: id, actor: v.actor, note: v.note}).then(function (d) { flash(d.msg); loadFb(); tickStatus(); });
    });
  });
  $('fb-eval').addEventListener('click', function () { busy(this, api('/api/feedback/eval', {})).then(function (d) { flash(d.msg); loadFb(); }).catch(fail); });
  $('fb-seg').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    e.stopPropagation();
    var mode = b.getAttribute('data-fbmode');
    if (STATUS && STATUS.feedback_mode === mode) return;
    ask({title: '피드백 방식 → ' + (mode === 'auto' ? '자동' : '승인형'), note: '자동은 이탈 조건에 걸리면 바로 적용하고, 승인형은 사람이 승인해야 적용한다. 바꾼 사람과 사유가 조정 로그에 남는다.',
      fields: [{k: 'actor', label: '처리자', req: true}, {k: 'note', label: '사유 (필수)', area: true, req: true}]}, function (v) {
      return api('/api/feedback/mode', {mode: mode, actor: v.actor, note: v.note}).then(function (d) { flash(d.msg); tickStatus(); if (curScreen === 'feedback') loadFb(); });
    });
  }, true);

  /* ---------- 6. 히트맵 · 통계 ---------- */
  var heatWhich = 'all';
  function loadStats() {
    return api('/api/stats?which=' + heatWhich).then(function (d) {
      var h = d.heat;
      $('heat-title').textContent = '구역 × 시간 — 최근 14일 위반 건수 (' + h.n + '건)';
      $('heat-head').innerHTML = '<tr><th class="rh">구역</th>' + h.hours.map(function (x) { return '<th>' + (x < 10 ? '0' : '') + x + '</th>'; }).join('') + '</tr>';
      $('heat').innerHTML = h.rows.length ? h.rows.map(function (r) {
        return '<tr><th class="rh">' + esc(r.zone) + ' ' + esc(r.name) + '</th>' + r.vals.map(function (v) { var k = v === 0 ? 0 : v <= 1 ? 1 : v <= 2 ? 2 : v <= 4 ? 3 : 4; return '<td class="h' + k + '">' + v + '</td>'; }).join('') + '</tr>';
      }).join('') : '<tr><td class="h0" colspan="' + (h.hours.length + 1) + '">최근 14일 기록이 없다</td></tr>';
      var mx = Math.max.apply(null, d.rates.map(function (r) { return r.rate; }).concat([0.0001]));
      $('st-rates').innerHTML = d.rates.length ? d.rates.map(function (r) {
        return '<div class="hb" title="' + r.n + '건 / ' + r.hours.toFixed(1) + '시간"><span>' + esc(r.label) + '</span><div class="tr"><i class="' + (r.kind === 'on' ? 'c' : '') + '" style="width:' + (r.rate / mx * 100).toFixed(0) + '%"></i></div><b>' + r.rate.toFixed(1) + '</b></div>';
      }).join('') : '<p class="empty">모드가 켜져 있던 시간 기록이 아직 없다. 실시간 관제 세션을 돌리면 모드가 켜지고 꺼진 시각이 쌓여 여기서 비교된다 (예시 기록에는 모드 시간이 없다).</p>';
      var hm = d.helmet;
      if (hm.has_model && hm.rate.length) {
        $('st-helmet-title').textContent = '안전모 착용률';
        $('st-helmet').innerHTML = hm.rate.map(function (x) { var p = Math.round(x.rate * 100); return '<div class="hb"><span>' + esc(x.dep) + '</span><div class="tr"><i class="' + (p >= 90 ? 'g' : 'w') + '" style="width:' + p + '%"></i></div><b>' + p + '%</b></div>'; }).join('');
        $('st-helmet-note').textContent = 'PPE는 안전모만 탐지한다. 기본 규칙(전 구역 안전모)이 도는지 보는 용도다.';
      } else {
        $('st-helmet-title').textContent = '안전모 미착용 기록';
        var mh = Math.max.apply(null, hm.by_dep.map(function (x) { return x.n; }).concat([1]));
        $('st-helmet').innerHTML = hm.by_dep.length ? hm.by_dep.map(function (x) { return '<div class="hb"><span>' + esc(x.dep) + '</span><div class="tr"><i class="w" style="width:' + (x.n / mh * 100).toFixed(0) + '%"></i></div><b>' + x.n + '건</b></div>'; }).join('') : '<p class="empty">최근 14일 안전모 미착용 기록 없음</p>';
        $('st-helmet-note').textContent = '안전모 탐지 모델이 아직 붙지 않아 착용률 대신 미착용 기록 건수를 부서 · 협력사로 묶어 보인다. detect.json 의 extra 에 no_helmet 모델을 붙이면 착용률로 바뀐다.';
      }
    }).catch(fail);
  }
  $('heat-f').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; heatWhich = b.getAttribute('data-v'); setTimeout(loadStats, 0); });

  /* ---------- 7. 홈 ---------- */
  var RA_KIND = {'확정': 'ok', '서명 대기': 'note', '수시평가 필요': 'crit', '정기평가 반영 대기': 'mute'};
  function loadHome() {
    return api('/api/home').then(function (d) {
      $('home-todo').innerHTML = d.cards.map(function (c, i) {
        var k = c.num ? (i === 0 ? ' crit' : i === 1 ? ' warn' : '') : '';
        return '<div class="tc' + k + '"><div class="hd"><b>' + esc(c.title) + '</b><span class="n">' + c.num + '</span></div><ul>' + c.lines.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' +
          '<button class="go" type="button" data-go="' + c.go + '"' + (c.tab ? ' data-tab="' + c.tab + '"' : '') + ' style="align-self:flex-start">' + ({docs: '안전 문서로 →', duty: '의무 이행 관리로 →', voice: '안전소통으로 →'}[c.go] || '열기 →') + '</button></div>';
      }).join('');
      $('home-board').innerHTML = d.zones.length ? d.zones.map(function (r) {
        return '<tr class="' + (r.score >= 12 ? 'hit' : '') + '"><td>' + z(r.zone) + ' ' + esc(r.zname) + '</td><td>' + esc(r.mode) + '</td><td class="num">' + (r.score >= 12 ? '<b>' + r.score + '</b>' : r.score) + ' <span class="d">' + esc(r.grade) + '</span></td><td>' + chip(r.ra, RA_KIND[r.ra] || 'mute') + '</td><td>' + (r.co ? '미조치 ' + r.co : '—') + '</td><td>' + (r.ptw && r.ptw !== '-' ? esc(r.ptw) : '—') + '</td><td>' + (r.voice || '—') + '</td></tr>';
      }).join('') : '<tr><td colspan="7" class="d">관제 기록이 아직 없다</td></tr>';
      var ev = d.evidence;
      $('home-period').textContent = ev.period + ' · 중처법 이행 증빙';
      $('home-kpis').innerHTML =
        '<div class="kpi"><span>이벤트</span><b>' + ev.events + '</b><small>경보 ' + ev.alerts + ' · 무음 ' + ev.silent + '</small></div>' +
        '<div class="kpi"><span>저장된 클립</span><b>' + ev.clips + '</b><small>전후 클립 · 대표 프레임</small></div>' +
        '<div class="kpi"><span>작업 전 게이트</span><b>' + ev.gates + '</b><small>목록 누락 · 미첨부</small></div>' +
        '<div class="kpi"><span>확정 문서</span><b>' + (ev.confirmed + ev.correctives) + '</b><small>평가 ' + ev.confirmed + ' · 지시서 ' + ev.correctives + '</small></div>';
      $('home-note').textContent = '기록된 날 ' + ev.recorded + '/' + ev.days + (ev.gaps.length ? ' · 끊긴 날 ' + ev.gaps.join(', ') + ' — 카메라 · 시스템 점검 대상' : ' · 끊긴 날 없음') +
        (d.handoff ? ' · 관제 인계 ' + d.handoff.n + '회, 마지막 ' + d.handoff.id + ' (' + d.handoff.source + ', 감지 ' + d.handoff.events + '건)' : '');
    }).catch(fail);
  }

  /* ---------- 8. 의무 이행 관리 ---------- */
  var DUTY = null;
  function dutyBody() { return {industry: $('dt-ind').value, workers: $('dt-n').value, cat: $('dt-cat').value, hazardous: META.profile.hazardous}; }
  function loadDuty() {
    return api('/api/duty', dutyBody()).then(function (d) {
      DUTY = d;
      var s = d.summary;
      $('dt-summary').textContent = '기준일 ' + d.today + ' · 기한 경과 ' + s.overdue + ' · 1일 이내 ' + s.urgent + ' · 7일 이내 ' + s.soon + ' · 30일 이내 ' + s.upcoming + ' · 여유 ' + s.ok;
      $('dt-rows').innerHTML = d.items.length ? d.items.map(function (it) {
        return '<tr class="' + (it.kind === 'crit' ? 'hit' : '') + '" title="' + esc(it.why) + '"><td>' + chip(it.status, it.kind) + '</td><td>' + esc(it.name) + (it.ref ? ' <span class="d mono">' + esc(it.ref) + '</span>' : '') + '</td><td class="nw">' + esc(it.category) + '</td><td>' + esc(it.basis) + '</td><td class="t">' + esc(it.due) + '</td><td>' + esc(it.retention) + '</td></tr>';
      }).join('') : '<tr><td colspan="6" class="d">해당 의무 없음</td></tr>';
      var cur = $('dt-item').value;
      $('dt-item').innerHTML = d.items.map(function (it) { return opt(it.key, it.name + (it.ref ? ' · ' + it.ref : '') + ' (기한 ' + it.due + ')', it.key === cur); }).join('');
      if (!$('dt-day').value) $('dt-day').value = d.today;
      $('dt-done').innerHTML = d.done.length ? d.done.map(function (r) {
        return '<tr><td class="t">' + esc(r['이행일']) + '</td><td>' + esc(r['의무']) + (r['대상'] && r['대상'] !== '-' ? ' <span class="d mono">' + esc(r['대상']) + '</span>' : '') + '</td><td>' + esc([r['담당자'], r['부서']].filter(function (x) { return x && x !== '-'; }).join(' · ') || '—') + '</td><td>' + esc(r['출처']) + '</td><td class="t">' + esc(r['서류 보존']) + '</td></tr>';
      }).join('') : '<tr><td colspan="5" class="d">이행 기록 없음</td></tr>';
    }).catch(fail);
  }
  ['dt-ind', 'dt-cat'].forEach(function (id) { $(id).addEventListener('change', loadDuty); });
  $('dt-n').addEventListener('change', loadDuty);
  $('dt-day').addEventListener('blur', function () {
    var v = this.value.trim(); if (!v) return;
    api('/api/norm-day?value=' + encodeURIComponent(v) + (DUTY ? '&today=' + DUTY.today : '')).then(function (d) { $('dt-day').value = d.day; }).catch(fail);
  });
  $('dt-go').addEventListener('click', function () {
    busy(this, api('/api/duty/done', {key: $('dt-item').value, staff: $('dt-who').value, day: $('dt-day').value, note: $('dt-note').value, today: DUTY && DUTY.today}))
      .then(function (d) { flash(d.msg); $('dt-note').value = ''; loadDuty(); tickStatus(); }).catch(fail);
  });

  /* ---------- 9. 안전 문서 ---------- */
  function pickTab(group, tab) {
    var bar = document.querySelector('.subtabs[data-group="' + group + '"]'); if (!bar) return;
    bar.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === tab); });
    document.querySelectorAll('[data-pane^="' + group + ':"]').forEach(function (p) { p.hidden = p.getAttribute('data-pane') !== group + ':' + tab; });
    if (group === 'docs') loadDocTab(tab);
  }
  var DOCS = {tab: 'ra', ev: null, ptw: null, acc: null, hid: null, ra: null, raPick: {}};
  function loadDocTab(tab, o) {
    DOCS.tab = tab; o = o || {};
    if (tab === 'ra') return loadRa();
    if (tab === 'corrective') return loadCo(o.ev);
    if (tab === 'ptw') return loadPtwDoc(o.ptw);
    if (tab === 'accident') return loadAcc(o.acc);
    if (tab === 'handoff') return loadHo(o.hid);
  }

  /* 위험성평가 */
  function loadRa() {
    return api('/api/docs/ra').then(function (d) { DOCS.ra = d; renderRa(); }).catch(fail);
  }
  function renderRa() {
    var d = DOCS.ra, has = d.drafts.length > 0;
    $('ra-steps').innerHTML = '<span class="done">① 이벤트 집계 · 위험도 계산</span>→<span class="' + (has ? 'done' : 'now') + '">② AI 초안 생성</span>→<span class="' + (has ? 'now' : '') + '">③ 관리자 서명 → 근로자 확인 요청</span>';
    $('ra-calc').innerHTML = d.rows.length ? '<table class="t" style="min-width:640px"><thead><tr><th></th><th>구역</th><th>모드</th><th>위반 유형</th><th>건수</th><th>가능성</th><th>중대성</th><th>위험도</th></tr></thead><tbody>' +
      d.rows.map(function (r) {
        return '<tr class="' + (r.adhoc.length ? 'hit' : '') + '" title="' + esc(r.l_label + (r.adhoc.length ? ' · ' + r.adhoc.join(', ') : '')) + '"><td class="pick"><input type="checkbox" data-ra-pick="' + r.i + '"' + (DOCS.raPick[r.i] ? ' checked' : '') + ' aria-label="이 행으로 초안"></td><td>' + z(r.zone) + '</td><td>' + esc(r.mode) + '</td><td>' + esc(r.type) + '</td><td class="num">' + r.count + '</td><td class="num">' + r.likelihood + (/하한/.test(r.l_label) ? ' <span class="d">(하한)</span>' : '') + '</td><td class="num">' + r.severity + '</td><td class="num">' + (r.score >= 12 ? '<b>' + r.score + '</b>' : r.score) + '</td></tr>';
      }).join('') + '</tbody></table>' : '<p class="empty">최근 90일 관제 기록이 없다.</p>';
    $('ra-bar').innerHTML = d.adhoc.length ? '<div class="bar crit"><span>위험도 12 이상 또는 중대성 4 1건 → 수시평가 제안 ' + d.adhoc.length + '건</span><span>위험성평가 지침 제15조제2항</span></div>'
      : '<div class="bar ok"><span>수시평가 제안 없음 — 정기평가로 반영</span></div>';
    if (!has) {
      $('ra-sheet').innerHTML = '<div class="ph"><h2>초안</h2><span class="sub">문장 칸은 직접 고칠 수 있다</span></div><p class="empty">AI 초안 생성을 누르면 여기에 평가표 초안이 뜬다. 숫자 칸은 코드가 채우고, 문장 칸만 AI가 쓴다.</p>';
      return;
    }
    var today = (STATUS ? STATUS.now : '').slice(0, 10);
    var kind = d.adhoc.length ? '수시' : '정기';
    var sheets = d.drafts.map(function (x) {
      function ed(k, v) { return '<dd class="llm" contenteditable="true" data-ed="' + k + '" data-i="' + x.i + '">' + esc(v) + '</dd>'; }
      return '<div class="docsheet"><div class="dh"><b>' + z(x.zone) + ' ' + esc(x.zname) + ' · ' + esc(x.mode) + '</b><span class="mono sub">' + esc(x.type) + ' · 위험도 ' + x.score + ' ' + esc(x.grade) + '</span></div><dl>' +
        '<dt>평가 구분 · 일자</dt><dd class="code"><span data-kind-view>' + kind + '</span> · ' + esc(today) + '</dd>' +
        '<dt>근거</dt><dd class="code">' + esc(x.event_ids.slice(0, 6).join(' · ') + (x.event_ids.length > 6 ? ' 외 ' + (x.event_ids.length - 6) + '건' : '')) + (x.accident_ids.length ? ' · 사고 ' + esc(x.accident_ids.join(', ')) : '') + '</dd>' +
        '<dt>가능성 × 중대성</dt><dd class="code">' + x.likelihood + ' × ' + x.severity + ' = <b>' + x.score + '</b> (' + esc(x.grade) + ')</dd>' +
        '<dt>단위작업</dt>' + ed('unit_work', x.unit_work) +
        '<dt>유해위험요인</dt>' + ed('hazard', x.hazard) +
        '<dt>발생 원인</dt>' + ed('cause', x.cause) +
        '<dt>현재 안전조치</dt>' + ed('current_measures', x.current_measures) +
        '<dt>감소대책</dt>' + ed('measures', x.measures) +
        '<dt>법적 근거</dt>' + ed('legal_refs', x.legal_refs) +
        '<dt>개선 후 위험도</dt><dd class="d">비워 둔다 — 적용 후 14일 실측</dd>' +
        (x.check ? '<dt>확인 필요</dt><dd class="d">' + esc(x.check) + '</dd>' : '') +
        '<dt>확인</dt><dd class="human">관리자 ☐ · 근로자 대표 ☐</dd></dl></div>';
    }).join('');
    $('ra-sheet').innerHTML = '<div class="ph"><h2>초안 — ' + d.drafts.length + '행</h2><span class="sub">문장 칸(노란 칸)은 눌러서 직접 고친다. 감소대책은 한 줄에 하나, [공학적]·[관리적]·[보호구]로 시작. 규칙 변경과 같으면 [관리적·R1]처럼 적는다</span></div>' + sheets +
      '<div class="btnrow" style="margin-top:10px">' +
      '<span class="field" style="flex-direction:row;align-items:center;gap:8px"><span class="lb">평가 구분</span><span class="seg" id="ra-kind"><button type="button"' + (kind === '수시' ? ' class="on"' : '') + ' data-v="수시">수시</button><button type="button"' + (kind === '정기' ? ' class="on"' : '') + ' data-v="정기">정기</button></span></span>' +
      '<span class="field" style="flex-direction:row;align-items:center;gap:8px"><label for="ra-sign">서명</label><select id="ra-sign">' + META.staff.map(function (p) { return opt(p.name, p.label); }).join('') + '</select></span>' +
      '<button class="btn dark" type="button" id="ra-go">관리자 서명 → 근로자 확인 요청</button>' + download(d.file, '엑셀로 내려받기') + '</div>';
  }
  $('ra-calc').addEventListener('change', function (e) { var c = e.target.closest('[data-ra-pick]'); if (c) DOCS.raPick[c.getAttribute('data-ra-pick')] = c.checked; });
  $('ra-draft').addEventListener('click', function () {
    var pick = Object.keys(DOCS.raPick).filter(function (k) { return DOCS.raPick[k]; }).map(Number);
    busy(this, api('/api/docs/ra/draft', {rows: pick})).then(function (d) { DOCS.ra.drafts = d.drafts; DOCS.ra.file = d.file; renderRa(); flash('초안 ' + d.drafts.length + '행 — 문장 칸을 확인하고 서명한다'); }).catch(fail);
  });
  $('ra-sheet').addEventListener('click', function (e) {
    var kb = e.target.closest('#ra-kind button');
    if (kb) { $('ra-kind').querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b === kb); }); document.querySelectorAll('[data-kind-view]').forEach(function (s) { s.textContent = kb.getAttribute('data-v'); }); return; }
    if (!e.target.closest('#ra-go')) return;
    var edits = {};
    document.querySelectorAll('#ra-sheet [data-ed]').forEach(function (dd) {
      var i = dd.getAttribute('data-i'); edits[i] = edits[i] || {i: +i}; edits[i][dd.getAttribute('data-ed')] = dd.innerText.trim();
    });
    var k = $('ra-kind').querySelector('button.on');
    busy(e.target, api('/api/docs/ra/sign', {edits: Object.keys(edits).map(function (i) { return edits[i]; }), kind: k ? k.getAttribute('data-v') : '수시', manager: $('ra-sign').value}))
      .then(function (d) { flash(d.msg); loadRa(); tickStatus(); }).catch(fail);
  });

  /* 시정지시서 */
  function loadCo(ev) {
    return api('/api/docs/co').then(function (d) {
      var want = ev || DOCS.ev || d.default;
      if (!d.events.some(function (x) { return x.id === want; })) want = d.default;
      DOCS.ev = want;
      $('co-ev').innerHTML = d.events.map(function (e) {
        return opt(e.id, e.id + ' · ' + e.ts + ' · ' + e.zone + ' · ' + e.level + ' · ' + e.type + (e.frame ? ' · 프레임' : '') + (e.handoff ? ' · 관제 인계' : '') + (e.issued ? ' · 발행 ' + e.issued : ''), e.id === want);
      }).join('') || opt('', '경보 이상 이벤트가 없다');
      return want ? showCoEvent(want) : null;
    }).catch(fail);
  }
  function showCoEvent(id) {
    DOCS.ev = id;
    return api('/api/docs/co/' + encodeURIComponent(id)).then(function (e) {
      $('co-frame').innerHTML = e.frame ? '<img alt="' + esc(id) + ' CCTV 프레임" src="/api/docs/co/' + encodeURIComponent(id) + '/frame">'
        : camSVG({poly: e.zone + ' 구역', active: true, aria: id + ' 대표 프레임', note: '프레임 없음 — 영상이 없던 기록'});
      $('co-info').innerHTML = '<table class="t"><tbody>' +
        '<tr><td class="d">일시</td><td class="t">' + esc(e.ts) + '</td></tr><tr><td class="d">구역 · 모드</td><td>' + z(e.zone) + ' ' + esc(e.zname) + ' · ' + esc(e.mode) + '</td></tr>' +
        '<tr><td class="d">판정</td><td>' + lv(e.level) + ' ' + esc(e.type) + (e.row ? ' · ' + e.row + '번 줄' : '') + '</td></tr>' +
        '<tr><td class="d">규칙</td><td>' + esc(e.adj ? '강화 중 ' + e.adj : '기본') + '</td></tr>' +
        (e.handoff ? '<tr><td class="d">관제 인계</td><td class="t">' + esc(e.handoff) + '</td></tr>' : '') + '</tbody></table>';
      $('co-sheet').innerHTML = '<div class="ph"><h2>시정지시서 초안</h2>' + (e.issued ? '<span class="lv ok">발행 ' + esc(e.issued.doc_no) + '</span>' : '<span class="lv note">아직 없음</span>') + '</div>' +
        '<p class="note">' + (e.issued ? '이미 발행한 지시서가 있다 (조치 기한 ' + esc(e.issued.deadline) + '). 다시 만들면 같은 번호의 새 판이 기록된다.' : '장면 설명 · 위험 요인 · 시정 요구 문장만 AI가 쓰고, 조치 기한과 근거 기록은 코드가 채운다. 만들면 발행 기록이 남고 의무 이행 관리에 조치 기한이 올라간다.') + '</p>' +
        '<div class="btnrow" style="margin-top:10px"><button class="btn dark" type="button" id="co-go">시정지시서 초안 생성</button>' + download(e.issued && e.issued.file, '워드로 내려받기') + '</div>';
    }).catch(fail);
  }
  $('co-ev').addEventListener('change', function () { showCoEvent(this.value); });
  $('co-sheet').addEventListener('click', function (e) {
    if (!e.target.closest('#co-go')) return;
    busy(e.target, api('/api/docs/co', {event_id: DOCS.ev})).then(function (o) {
      var rows = [['발행일 · 구역', 'code', esc(o.issued) + ' · ' + z(o.zone) + ' ' + esc(o.zname)],
        ['판정', 'code', lv(o.level) + ' ' + esc(o.type) + ' · 모드 ' + esc(o.mode) + ' · ' + esc(o.rule_state)],
        ['근거', 'code', esc(o.event_id) + ' · ' + esc(o.clip || '클립 없음') + ' · 같은 위반 최근 14일 ' + o.same_recent + '건'],
        ['중대성 · 조치 기한', 'code', o.severity + '등급 (' + esc(o.severity_label) + ') · <b>' + esc(o.deadline) + '</b>'],
        ['현장 상황', 'llm', esc(o.scene)],
        ['위험 기인물', 'llm', o.hazards.map(function (h) { return h.rank + '. ' + esc(h.hazard) + ' — ' + esc(h.reason); }).join('<br>')],
        ['위반 사항', 'llm', esc(o.violation)],
        ['시정 요구', 'llm', o.actions.map(function (a) { return '[' + esc(a.category) + '] ' + esc(a.text); }).join('<br>')],
        ['법적 근거', 'code', o.legal_refs.map(esc).join('<br>')]];
      if (o.uncertain || o.warnings.length) rows.push(['확인 필요', 'd', [o.uncertain].concat(o.warnings).filter(Boolean).map(esc).join('<br>')]);
      rows.push(['수신 · 기한', 'human', '사람이 지정 — 조치 결과를 사진과 함께 회신']);
      $('co-sheet').innerHTML = '<div class="ph"><h2>시정지시서 초안</h2><span class="lv note">초안</span></div><div class="docsheet"><div class="dh"><b>시정지시서</b><span class="mono" style="font-size:12px;color:var(--ink-2)">' + esc(o.doc_no) + '</span></div><dl>' +
        rows.map(function (r) { return '<dt>' + r[0] + '</dt><dd class="' + r[1] + '">' + r[2] + '</dd>'; }).join('') + '</dl></div>' +
        '<div class="btnrow" style="margin-top:10px">' + download(o.file, '워드로 내려받기') + '<button class="btn sm" type="button" id="co-go">다시 만들기</button></div>' +
        '<p class="note" style="margin-top:6px">보존: 조치 이행일부터 5년 (중대재해처벌법 시행령 제13조)</p>';
      flash(o.doc_no + ' — 초안 · 발행 기록'); tickStatus();
    }).catch(fail);
  });

  /* 작업허가서 점검 */
  function loadPtwDoc(pid) {
    return api('/api/docs/ptw').then(function (d) {
      var want = pid || DOCS.ptw || (d.ptws[0] || {}).id;
      if (!d.ptws.some(function (p) { return p.id === want; })) want = (d.ptws[0] || {}).id;
      DOCS.ptw = want;
      $('ptw-sel').innerHTML = d.ptws.map(function (p) { return opt(p.id, p.id + ' · ' + p.type + ' · ' + p.zone + ' · ' + p.work, p.id === want); }).join('') || opt('', '등록된 허가서가 없다');
      $('ptw-find').innerHTML = '<p class="empty">점검을 누르면 격리 목록 · 밸브 단독 격리 · 퍼지 · 측정 · 동시작업을 코드로 판정하고, 지적 문장만 AI가 쓴다.</p>'; $('ptw-cnt').innerHTML = '';
      return want ? showPtwDoc(want) : null;
    }).catch(fail);
  }
  function showPtwDoc(pid) {
    DOCS.ptw = pid;
    return api('/api/docs/ptw/' + encodeURIComponent(pid)).then(function (d) {
      var p = d.ptw;
      $('ptw-info').innerHTML = '<div class="hcard soft"><div class="hd"><b class="mono">' + esc(p.ptw_id) + '</b>' + chip(p.type, 'info') + '</div><p>' + z(p.zone) + ' ' + esc(d.zname) + ' · ' + esc(p.work) + '</p><p>' + esc((p.start || '').replace('T', ' ')) + ' ~ ' + esc((p.end || '').slice(11)) + ' · 인원 ' + esc(p.workers || '-') + ' · 작업책임자 ' + esc(p.supervisor || '(비어 있음)') + ' · 퍼지 ' + esc(d.purge == null ? '-' : d.purge) + '분</p>' + (p.registered_at ? '<p class="note">관제 격리 목록 대조에서 등록 · ' + esc(p.registered_at.replace('T', ' ')) + '</p>' : '') + '</div>';
      $('ptw-list').innerHTML = d.iso ? '<div class="tbl"><table class="t"><thead><tr><th>line_id</th><th>배관</th><th>격리방법</th><th>맹판</th></tr></thead><tbody>' +
        d.iso.map(function (l) { var b = String(l['맹판설치'] || '').trim().toUpperCase(); return '<tr><td class="t">' + esc(l.line_id) + '</td><td>' + esc(l['배관'] || '') + '</td><td>' + esc(l['격리방법'] || '-') + '</td><td class="c ' + (b === 'O' ? 'y' : 'x') + '">' + (b === 'O' ? 'O' : '대기') + '</td></tr>'; }).join('') + '</tbody></table></div>'
        : '<p class="empty">첨부된 격리 목록 없음</p>';
    }).catch(fail);
  }
  $('ptw-sel').addEventListener('change', function () { showPtwDoc(this.value); $('ptw-find').innerHTML = ''; $('ptw-cnt').innerHTML = ''; });
  $('ptw-run').addEventListener('click', function () {
    busy(this, api('/api/docs/ptw/' + encodeURIComponent(DOCS.ptw), {})).then(function (r) {
      var crit = function (c) { return ['R1', 'R2', 'LIST', 'SIMOPS'].indexOf(c) >= 0; };
      $('ptw-cnt').innerHTML = chip(r.findings.length ? r.findings.length + '건' : '없음', r.findings.length ? 'crit' : 'ok');
      $('ptw-find').innerHTML = '<div class="bar ' + (r.findings.length ? 'crit' : 'ok') + '" style="margin-top:0"><span>' + esc(r.result) + '</span><span>판정은 코드 · 문장은 ' + esc(r.text_source) + '</span></div><p class="note">' + esc(r.summary) + '</p>' +
        (r.findings.length ? r.findings.map(function (f) {
          return '<div class="hcard' + (crit(f.code) ? ' crit' : '') + '"><div class="hd"><b>' + esc(f.code) + ' · ' + esc(f.title) + '</b></div><p>' + esc(f.detail) + '</p><p>' + esc(f.note) + '</p><p class="note">' + esc(f.legal_refs.join(' · ')) + '</p></div>';
        }).join('') : '<p class="empty">찾은 항목 없음 — 허가 발급 가능</p>') +
        '<div class="tbl"><table class="t"><thead><tr><th>배관</th><th>이름</th><th>유체</th><th>격리 목록</th><th>맹판</th><th>측정</th></tr></thead><tbody>' +
        r.pid.map(function (l) { return '<tr class="' + (l.listed ? '' : 'hit') + '"><td class="t">' + esc(l.line_id) + '</td><td>' + esc(l.name) + '</td><td>' + esc(l.fluid) + '</td><td>' + (l.listed ? '있음' : '<b class="x">없음</b>') + '</td><td>' + esc(l.blind || '-') + '</td><td>' + esc(l.gas || '-') + '</td></tr>'; }).join('') + '</tbody></table></div>' +
        '<div class="btnrow">' + download(r.file, '점검 결과 워드로 내려받기') + '</div>';
    }).catch(fail);
  });

  /* 산업재해조사표 */
  function loadAcc(aid) {
    return api('/api/docs/acc').then(function (d) {
      var want = aid || DOCS.acc || d.default;
      if (!d.accidents.some(function (a) { return a.id === want; })) want = d.default;
      DOCS.acc = want;
      $('acc-sel').innerHTML = d.accidents.map(function (a) { return opt(a.id, a.id + ' · ' + a.date + ' ' + a.time + ' · ' + a.zone + ' ' + a.summary + ' (휴업 ' + a.lost_days + '일)', a.id === want); }).join('') || opt('', '대상 사고 없음');
      return want ? showAcc(want) : null;
    }).catch(fail);
  }
  function accTimeline(tl) {
    return '<table class="t"><tbody>' + tl.map(function (t) { return '<tr class="' + t.kind + '"><td class="t">' + esc(t.t) + '</td><td class="t">' + esc(t.src) + '</td><td>' + esc(t.what) + '</td></tr>'; }).join('') + '</tbody></table>';
  }
  function showAcc(aid) {
    DOCS.acc = aid;
    return api('/api/docs/acc/' + encodeURIComponent(aid)).then(function (d) {
      $('acc-tl').innerHTML = d.timeline.length ? accTimeline(d.timeline) : '<p class="empty">사고 전 관제 기록이 없다.</p>';
      $('acc-sheet').innerHTML = '<div class="ph"><h2>산업재해조사표 초안</h2><span class="sub">발생일부터 1개월 이내 제출 · 기한 ' + esc(d.due) + '</span></div>' +
        '<div class="docsheet"><div class="dh"><b>산업재해조사표</b><span class="mono" style="font-size:12px;color:var(--ink-2)">' + esc(aid) + '</span></div><dl>' +
        '<dt>발생 일시 · 장소</dt><dd class="code">' + esc(d.acc.date + ' ' + (d.acc.time || '')) + ' · ' + z(d.acc.zone) + ' ' + esc(d.zname) + '</dd>' +
        '<dt>발생 경과</dt><dd class="llm d">조사표 초안 생성을 누르면 관제 기록 · 허가서로 AI가 쓴다</dd>' +
        '<dt>재해자 정보</dt><dd class="human">사람이 입력 (지금은 부상 ' + esc(d.acc.injured || '-') + '명 · 휴업 ' + esc(d.acc.lost_days || 0) + '일)</dd>' +
        '<dt>원인 · 재발 방지</dt><dd class="human">사람이 판단 — 초안은 원인을 단정하지 않는다</dd></dl></div>';
    }).catch(fail);
  }
  $('acc-sel').addEventListener('change', function () { showAcc(this.value); });
  $('acc-run').addEventListener('click', function () {
    busy(this, api('/api/docs/acc/' + encodeURIComponent(DOCS.acc), {})).then(function (r) {
      $('acc-tl').innerHTML = accTimeline(r.timeline);
      $('acc-sheet').innerHTML = '<div class="ph"><h2>산업재해조사표 초안</h2><span class="sub">발생일부터 1개월 이내 제출 · 기한 <b>' + esc(r.due) + '</b></span></div>' +
        '<div class="docsheet"><div class="dh"><b>산업재해조사표</b><span class="mono" style="font-size:12px;color:var(--ink-2)">' + esc(r.acc.id) + '</span></div><dl>' +
        '<dt>발생 일시 · 장소</dt><dd class="code">' + esc(r.acc.date + ' ' + (r.acc.time || '')) + ' · ' + z(r.acc.zone) + ' ' + esc(r.zname) + '</dd>' +
        '<dt>발생 경과</dt><dd class="llm">' + esc(r.narrative) + '</dd>' +
        '<dt>재발방지 계획 초안</dt><dd class="llm">' + r.prevention.map(function (p) { return '[' + esc(p.category) + '] ' + esc(p.text); }).join('<br>') + '</dd>' +
        '<dt>재해자 정보</dt><dd class="human">사람이 입력 (부상 ' + esc(r.acc.injured || '-') + '명 · 휴업 ' + esc(r.acc.lost_days || 0) + '일)</dd>' +
        '<dt>원인 · 재발 방지</dt><dd class="human">사람이 판단 — 초안은 원인을 단정하지 않는다</dd>' +
        (r.check ? '<dt>조사자 확인 필요</dt><dd class="d">' + esc(r.check) + '</dd>' : '') + '</dl></div>' +
        '<div class="btnrow" style="margin-top:10px">' + download(r.file, '워드로 내려받기') + '</div>' +
        '<p class="note" style="margin-top:6px">산업안전보건법 제57조제3항 · 시행규칙 제73조제1항 · 보존 3년 · 문장은 ' + esc(r.text_source) + '</p>';
      flash('조사표 초안 — 제출 기한 ' + r.due);
    }).catch(fail);
  });

  /* 관제 인계 */
  function loadHo(hid) {
    return api('/api/docs/handoff').then(function (d) {
      var want = hid || DOCS.hid || (d.handoffs[0] || {}).id;
      if (!d.handoffs.some(function (h) { return h.id === want; })) want = (d.handoffs[0] || {}).id;
      DOCS.hid = want;
      $('ho-sel').innerHTML = d.handoffs.map(function (h) {
        return opt(h.id, h.id + ' · ' + h.source + ' · 감지 ' + h.n + '건' + (h.gates ? ' · 게이트 ' + h.gates : '') + (h.accidents ? ' · 사고 ' + h.accidents : ''), h.id === want);
      }).join('') || opt('', '넘어온 감지 내역이 아직 없다');
      $('ho-sub').textContent = d.handoffs.length + '회';
      if (want) return showHo(want);
      $('ho-info').textContent = '관제 화면에서 ‘문서 자동화로 넘기기’를 누르면 여기에 쌓인다. 관제 화면이 없을 때는 아래 ‘관제 엔진 결과 파일로 넘기기’로 엔진 결과를 바로 넣어 볼 수 있다.';
      $('ho-table').innerHTML = ''; $('ho-cand').innerHTML = '<p class="empty">인계 기록이 없다.</p>';
    }).catch(fail);
  }
  function showHo(hid) {
    DOCS.hid = hid;
    return api('/api/docs/handoff/' + encodeURIComponent(hid)).then(function (h) {
      $('ho-info').textContent = h.id + ' · ' + h.source + ' · 받은 시각 ' + h.ts + ' · 감지 ' + h.received + '건 받음 · 이미 받은 내역 ' + h.duplicates + '건 건너뜀 · 게이트 ' + h.gates.length + ' · 사고 ' + h.accidents.length + (h.warnings.length ? ' · ⚠ ' + h.warnings.join(' · ') : '');
      $('ho-table').innerHTML = h.events.length ? '<table class="t" style="min-width:640px"><thead><tr><th>시각</th><th>번호</th><th>구역</th><th>모드</th><th>위반</th><th>판정</th><th>판정 근거</th></tr></thead><tbody>' +
        h.events.map(function (x) { return '<tr class="' + (x.alerted ? '' : 'shadow') + '"><td class="t">' + esc(x.t) + '</td><td class="t">' + esc(x.id) + '</td><td>' + z(x.zone) + '</td><td>' + esc(x.mode) + '</td><td>' + esc(x.type) + (x.frame ? ' <span class="rule">프레임</span>' : '') + '</td><td>' + lv(x.level, x.alerted) + '</td><td>' + esc(x.why) + '</td></tr>'; }).join('') + '</tbody></table>'
        : '<p class="empty">감지 기록이 없다 (게이트 · 사고만 넘어왔거나 이미 받은 내역).</p>';
      var nNew = h.corrective.filter(function (x) { return !x.issued; }).length;
      var c = '<div class="hcard' + (nNew ? ' crit' : '') + '"><div class="hd"><b>시정지시서 — 경보 이상 ' + h.corrective.length + '건</b>' + chip(nNew ? '미발행 ' + nNew : '해당 없음', nNew ? 'note' : 'ok') + '</div>' +
        (h.corrective.length ? '<div class="stack" style="gap:4px">' + h.corrective.map(function (x) { return '<label class="note" style="display:flex;gap:8px;align-items:center;color:var(--ink)"><input type="checkbox" data-ho-pick="' + esc(x.id) + '"' + (x.issued ? '' : ' checked') + '> ' + esc(x.t) + ' ' + esc(x.id) + ' · ' + esc(x.zone) + ' · ' + esc(x.type) + ' · ' + esc(x.level) + (x.frame ? ' · 프레임' : '') + (x.issued ? ' · 발행됨 ' + esc(x.issued) : '') + '</label>'; }).join('') + '</div>' +
          '<div class="btnrow"><button class="btn dark sm" type="button" id="ho-make">선택한 이벤트로 시정지시서 초안 만들기</button></div><div id="ho-made"></div>' : '') + '</div>';
      c += '<div class="hcard' + (h.adhoc.length ? ' crit' : ' soft') + '"><div class="hd"><b>수시 위험성평가 제안 ' + h.adhoc.length + '건</b><button class="go" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button></div>' +
        (h.adhoc.length ? h.adhoc.map(function (a) { return '<p>' + z(a.zone) + ' ' + esc(a.mode) + ' · ' + esc(a.violation_type) + ' — 위험도 ' + a.score + ' ' + esc(a.grade) + ' · ' + esc(a.reasons.join(', ')) + '</p>'; }).join('') : '<p>기준(위험도 12 · 중대성 4)에 걸린 행 없음</p>') + '</div>';
      if (h.gates.length) c += '<div class="hcard"><div class="hd"><b>작업허가서 점검 — 작업 전 게이트 ' + h.gates.length + '건</b><button class="go" type="button" data-go="docs" data-tab="ptw">작업허가서 점검으로 →</button></div>' + h.gates.map(function (g) { return '<p>' + esc(g.t) + ' ' + z(g.zone) + ' ' + esc(g.type || '') + ' — ' + esc(g.reason) + '</p>'; }).join('') + '</div>';
      if (h.accidents.length) c += '<div class="hcard crit"><div class="hd"><b>산업재해조사표 — 사고 ' + h.accidents.length + '건</b><button class="go" type="button" data-go="docs" data-tab="accident">산업재해조사표로 →</button></div>' + h.accidents.map(function (a) { return '<p>' + esc(a.t) + ' ' + z(a.zone) + ' ' + esc(a.type || '') + ' — ' + esc(a.reason) + '</p>'; }).join('') + '<p class="note">사망 · 휴업 3일 이상이면 조사표 대상이다. 재해자 수 · 휴업일수는 사람이 넣는다.</p></div>';
      $('ho-cand').innerHTML = c;
    }).catch(fail);
  }
  $('ho-sel').addEventListener('change', function () { showHo(this.value); });
  $('ho-cand').addEventListener('click', function (e) {
    if (!e.target.closest('#ho-make')) return;
    var ids = []; document.querySelectorAll('[data-ho-pick]').forEach(function (c) { if (c.checked) ids.push(c.getAttribute('data-ho-pick')); });
    busy(e.target, api('/api/docs/handoff/' + encodeURIComponent(DOCS.hid) + '/make', {event_ids: ids})).then(function (d) {
      flash('시정지시서 초안 ' + d.made.length + '건 — 발행 기록이 남고 의무 이행 관리에 조치 기한이 올라간다');
      return showHo(DOCS.hid).then(function () {
        $('ho-made').innerHTML = '<div class="stack" style="gap:4px;margin-top:8px">' + d.made.map(function (m) { return '<div class="btnrow"><span class="mono">' + esc(m.doc_no) + '</span><span class="note">← ' + esc(m.event_id) + ' · 중대성 ' + m.severity + ' · 기한 ' + esc(m.deadline) + '</span>' + download(m.file, '워드') + '</div>'; }).join('') + '</div>';
        tickStatus();
      });
    }).catch(fail);
  });
  $('ho-up').addEventListener('click', function () {
    var f = $('ho-file').files && $('ho-file').files[0];
    if (!f) { flash('관제 엔진 결과 파일(events.jsonl 또는 events_for_docgen.json)을 고른다', true); return; }
    var fd = new FormData(); fd.append('file', f); fd.append('base_dir', $('ho-base').value); fd.append('source', $('ho-src').value);
    busy(this, api('/api/docs/handoff/upload', fd)).then(function (d) { flash(d.msg); $('ho-file').value = ''; loadHo(d.handoff_id); }).catch(fail);
  });

  /* ---------- 10. 안전소통 ---------- */
  var VC = {sel: null, kind: null, state: null};
  var VS_K = {'접수': 'warn', '조치 중': 'info', '완료': 'ok'};
  function loadVoice() {
    return api('/api/voice').then(function (d) {
      var s = d.summary;
      $('vc-kpis').innerHTML = '<div class="kpi"><span>접수</span><b>' + s.total + '</b><small>최근 30일 ' + s.recent + '건</small></div>' +
        '<div class="kpi' + (s.open ? ' warn' : '') + '"><span>미조치</span><b>' + s.open + '</b><small>완료되지 않은 제보</small></div>' +
        '<div class="kpi"><span>조치 중</span><b>' + s.doing + '</b></div><div class="kpi"><span>완료</span><b>' + s.done + '</b><small>조치율 ' + s.rate + '%</small></div>';
      var cur = $('vc-ra').value;
      $('vc-ra').innerHTML = d.pending.map(function (r) { return opt(r.id, r.id + ' · ' + r.kind + ' · 관리자 서명 ' + r.manager + ' · ' + r.n + '행', r.id === cur); }).join('') || opt('', '근로자 확인 대기 평가가 없다');
      showVcRa();
      $('vc-list').innerHTML = d.reports.length ? '<table class="t" style="min-width:560px"><thead><tr><th>접수</th><th>구분</th><th>구역</th><th>내용</th><th>상태</th></tr></thead><tbody>' +
        d.reports.map(function (r) { return '<tr class="click' + (r.id === VC.sel ? ' sel' : '') + '" data-vc="' + esc(r.id) + '" title="' + esc((r.action ? '조치: ' + r.action : '') + (r.by ? ' · ' + r.by : '')) + '"><td class="t">' + esc(r.ts.slice(5, 10)) + '</td><td>' + esc(r.kind) + '</td><td>' + z(r.zone) + '</td><td>' + esc(r.text) + '</td><td>' + chip(r.state === '접수' ? '미조치' : r.state, VS_K[r.state]) + '</td></tr>'; }).join('') + '</tbody></table>'
        : '<p class="empty">제보가 없다.</p>';
      $('vc-upd').hidden = !VC.sel;
    }).catch(fail);
  }
  function showVcRa() {
    var id = $('vc-ra').value;
    if (!id) { $('vc-ra-rows').innerHTML = ''; return; }
    api('/api/voice/ra/' + encodeURIComponent(id)).then(function (r) {
      $('vc-ra-rows').innerHTML = (r.rule_rejected && r.rule_rejected.length ? '<div class="bar crit" style="margin:0 0 8px"><span>반려된 규칙 변경 ' + esc(r.rule_rejected.join(', ')) + ' — 확정해도 규칙셋에 올리지 않는다</span><span>관제 › 피드백 · 조정 로그</span></div>' : '') + '<table class="t"><thead><tr><th>유해위험요인</th><th>위험도</th><th>감소대책</th></tr></thead><tbody>' +
        r.rows.map(function (x) { return '<tr><td>' + z(x.zone) + ' ' + esc(x.hazard || x.mode) + '</td><td class="num">' + x.score + '</td><td style="white-space:pre-line">' + esc(x.measures) + '</td></tr>'; }).join('') + '</tbody></table>';
    }).catch(fail);
  }
  $('vc-ra').addEventListener('change', showVcRa);
  $('vc-ok').addEventListener('click', function () {
    busy(this, api('/api/voice/confirm', {ra_id: $('vc-ra').value, name: $('vc-by').value, note: $('vc-why').value})).then(function (d) { flash(d.msg); $('vc-why').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });
  $('vc-no').addEventListener('click', function () {
    busy(this, api('/api/voice/reject', {ra_id: $('vc-ra').value, name: $('vc-by').value, reason: $('vc-why').value})).then(function (d) { flash(d.msg); $('vc-why').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });
  $('vc-list').addEventListener('click', function (e) {
    var tr = e.target.closest('[data-vc]'); if (!tr) return;
    VC.sel = tr.getAttribute('data-vc');
    $('vc-upd-id').textContent = VC.sel + ' 상태';
    $('vc-list').querySelectorAll('tr[data-vc]').forEach(function (r) { r.classList.toggle('sel', r === tr); });
    $('vc-upd').hidden = false;
  });
  $('vc-state').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) VC.state = b.getAttribute('data-v'); });
  $('vc-kind').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) VC.kind = b.getAttribute('data-v'); });
  $('vc-upd-go').addEventListener('click', function () {
    busy(this, api('/api/voice/update', {id: VC.sel, state: VC.state, action: $('vc-act').value, by: $('vc-who').value})).then(function (d) { flash(d.msg); $('vc-act').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });
  $('vc-send').addEventListener('click', function () {
    busy(this, api('/api/voice/report', {kind: VC.kind, zone: $('vc-zone').value, text: $('vc-body').value, reporter: $('vc-rep').value})).then(function (d) { flash(d.msg); $('vc-body').value = ''; $('vc-rep').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });

  /* ---------- 11. 기록 ---------- */
  function loadArchive() {
    return api('/api/archive').then(function (d) {
      function stK(s) { return /확정|완료|이행/.test(s) ? 'ok' : /반려|대기|초안|보완/.test(s) ? 'note' : 'mute'; }
      $('ar-docs').innerHTML = d.docs.length ? d.docs.map(function (r) {
        return '<tr><td>' + esc(r['종류']) + '</td><td class="t">' + esc(r['번호']) + '</td><td class="t">' + esc(r['날짜']) + '</td><td>' + chip(r['상태'], stK(r['상태'])) + '</td><td>' + esc(r['근거 기록']) + '</td><td class="t" title="' + esc(r['보존 근거']) + '">' + esc(r['보존 기한']) + '</td><td>' + (r.url ? '<a class="go" href="' + esc(r.url) + '" download>내려받기</a>' : '—') + '</td></tr>';
      }).join('') : '<tr><td colspan="7" class="d">문서가 없다</td></tr>';
      $('ar-eff').innerHTML = d.effects.length ? d.effects.map(function (r) {
        var done = !/측정 중/.test(r['개선 후 (실측)']);
        return '<tr><td class="t">' + esc(r['평가 번호']) + '</td><td>' + z(r['구역']) + ' ' + esc(r['작업 모드']) + '</td><td>' + esc(r['위반 유형']) + '</td><td class="num">' + esc(r['개선 전 위험도']) + '</td><td>' + chip(r['개선 후 (실측)'], done ? 'ok' : 'mute') + '</td></tr>';
      }).join('') : '<tr><td colspan="5" class="d">확정된 평가가 아직 없다</td></tr>';
      $('ar-rules').innerHTML = d.rulesets.slice().reverse().map(function (r) {
        return '<tr><td class="t">v' + esc(r['버전']) + '</td><td class="t">' + esc(r['시각']) + '</td><td style="white-space:pre-line">' + esc(r['반영한 변경']) + '</td><td class="t">' + esc(r['근거 평가']) + (r['확정자'] && r['확정자'] !== '-' ? ' · ' + esc(r['확정자']) : '') + '</td></tr>';
      }).join('');
      $('ar-rev').innerHTML = d.revisions.length ? d.revisions.map(function (r) {
        return '<tr><td class="t">' + esc(r['시각']) + '</td><td class="t">' + esc(r['평가 번호']) + '</td><td>' + chip(r['상태'], r['상태'] === '확정' ? 'ok' : r['상태'] === '반려' ? 'warn' : 'note') + '</td><td>' + esc(r['서명·처리']) + (r['비고'] ? ' · ' + esc(r['비고']) : '') + '</td></tr>';
      }).join('') : '<tr><td colspan="4" class="d">기록 없음</td></tr>';
    }).catch(fail);
  }

  /* ---------- 확인 창 (이름 · 사유) ---------- */
  var askCb = null;
  function ask(o, cb) {
    $('ask-h').textContent = o.title; $('ask-note').textContent = o.note || '';
    $('ask-fields').innerHTML = o.fields.map(function (f) {
      var v = f.k === 'actor' || f.k === 'by' ? (store('actor') || '') : '';
      var ctl = f.options ? '<select id="askf-' + f.k + '" data-k="' + f.k + '">' + f.options.map(function (x) { return opt(x, x); }).join('') + '</select>'
        : f.area ? '<textarea id="askf-' + f.k + '" data-k="' + f.k + '"' + (f.req ? ' data-req="1"' : '') + '></textarea>'
        : '<input id="askf-' + f.k + '" data-k="' + f.k + '"' + (f.req ? ' data-req="1"' : '') + ' value="' + esc(v) + '">';
      return '<div class="field"><label for="askf-' + f.k + '">' + esc(f.label) + '</label>' + ctl + '</div>';
    }).join('');
    $('ask-err').hidden = true; askCb = cb; $('ask').hidden = false;
    var first = $('ask-fields').querySelector('input,textarea'); if (first) first.focus();
  }
  function closeAsk() { $('ask').hidden = true; askCb = null; }
  $('ask-close').addEventListener('click', closeAsk);
  $('ask-cancel').addEventListener('click', closeAsk);
  $('ask').addEventListener('click', function (e) { if (e.target === this) closeAsk(); });
  $('ask-ok').addEventListener('click', function () {
    var v = {}, miss = null;
    $('ask-fields').querySelectorAll('[data-k]').forEach(function (el) { v[el.getAttribute('data-k')] = el.value.trim(); if (el.getAttribute('data-req') && !el.value.trim() && !miss) miss = el; });
    if (miss) { $('ask-err').textContent = '필수 칸을 채운다.'; $('ask-err').hidden = false; miss.focus(); return; }
    if (v.actor || v.by) store('actor', v.actor || v.by);
    var btn = this;
    busy(btn, askCb(v)).then(closeAsk).catch(function (e) { $('ask-err').textContent = e.message; $('ask-err').hidden = false; });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (!$('ask').hidden) closeAsk(); else if (!$('reg').hidden) closeReg();
    else if (!$('scn').hidden && !SC.draw && !SC.dirty) closeScene();   // 그리던 것이 있으면 Esc 로 닫지 않는다
  });

  /* ---------- 화면 전환 (시안 그대로) ---------- */
  var screens = document.querySelectorAll('.screen'), links = document.querySelectorAll('.nav a[data-go]');
  var LOADERS = {live: loadLive, iso: function (o) { return loadIso(o && o.ptw); }, log: function (o) { return loadLog(o); }, replay: function () { return loadReplay(); },
    feedback: loadFb, stats: loadStats, home: loadHome, duty: loadDuty, voice: loadVoice, archive: loadArchive,
    docs: function (o) { var t = (o && o.tab) || DOCS.tab; pickTabOnly('docs', t); return loadDocTab(t, o || {}); }};
  function pickTabOnly(group, tab) {
    var bar = document.querySelector('.subtabs[data-group="' + group + '"]'); if (!bar) return;
    bar.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === tab); });
    document.querySelectorAll('[data-pane^="' + group + ':"]').forEach(function (p) { p.hidden = p.getAttribute('data-pane') !== group + ':' + tab; });
  }
  function show(id, o) {
    var target = document.querySelector('.screen[data-screen="' + id + '"]'); if (!target) return;
    if (id !== 'replay') stopPlay();
    curScreen = id;
    $('popups').classList.toggle('dock-b', id === 'live');
    screens.forEach(function (s) { s.hidden = (s !== target); });
    links.forEach(function (a) { a.classList.toggle('on', a.getAttribute('data-go') === id); });
    $('title').textContent = target.getAttribute('data-title');
    $('crumb').textContent = target.getAttribute('data-crumb');
    try { history.replaceState(null, '', '#' + id); } catch (e) { /* 미리 보기 등 */ }
    window.scrollTo(0, 0);
    if (LOADERS[id]) LOADERS[id](o || {});
  }
  document.addEventListener('click', function (e) {
    if (e.target.closest('#popups')) return;
    var go = e.target.closest('[data-go]');
    if (go) { e.preventDefault(); show(go.getAttribute('data-go'), {tab: go.getAttribute('data-tab'), ev: go.getAttribute('data-ev'), ptw: go.getAttribute('data-ptw'), q: go.getAttribute('data-q')}); return; }
    if (e.target.closest('[data-reopen]')) { popClosed = {}; if (STATUS) popups(STATUS); return; }
    var zt = e.target.closest('[data-zone]'); if (zt) { curZone = zt.getAttribute('data-zone'); curCam = 0; zonePickedAt = Date.now(); if (LIVE) { renderZones(); renderZoneDetail(); } return; }
    var cb = e.target.closest('[data-cam]'); if (cb && cb.tagName === 'BUTTON') { curCam = +cb.getAttribute('data-cam'); renderZoneDetail(); return; }
    var pk = e.target.closest('[data-ptw]'); if (pk && pk.classList.contains('pick')) { ISO.cur = pk.getAttribute('data-ptw'); renderIsoPicks(); return; }
    var sc = e.target.closest('[data-sc]'); if (sc) { RP.cur = sc.getAttribute('data-sc'); renderScPicks(); loadSc(); return; }
    var rc = e.target.closest('[data-rc]'); if (rc) { if (FB.rc !== rc.getAttribute('data-rc')) FB.review = false; FB.rc = rc.getAttribute('data-rc'); renderFb(); return; }
    var ev = e.target.closest('tr[data-ev]'); if (ev) { selectEv(ev.getAttribute('data-ev')); return; }
    var st = e.target.closest('.subtabs button'); if (st) { pickTab(st.parentElement.getAttribute('data-group'), st.getAttribute('data-tab')); return; }
    var sb = e.target.closest('.seg button');
    if (sb && !sb.closest('#fb-seg') && !sb.closest('#lv-speed')) { sb.parentElement.querySelectorAll('button').forEach(function (x) { x.classList.remove('on'); }); sb.classList.add('on'); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    var ev = e.target.closest && e.target.closest('tr[data-ev]'); if (ev) { selectEv(ev.getAttribute('data-ev')); }
  });
  document.querySelectorAll('.nav a').forEach(function (a) {
    a.setAttribute('tabindex', '0'); a.setAttribute('role', 'button');
    a.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); a.click(); } });
  });
  $('ft-llm').addEventListener('change', function () {
    var el = this, v = el.value;
    api('/api/llm', {provider: v}).then(function (d) { flash('문장 생성 → ' + d.llm); tickStatus(); }).catch(function (e) { fail(e); if (STATUS) el.value = STATUS.llm; });
  });

  /* ---------- 영상 장면 — 영상 올리기 · 첫 프레임 위에 구역 그리기 ----------
   * 영상을 올리면 첫 프레임이 뜨고, 그 위에 구역(폴리곤)을 찍어 장면으로 저장한다.
   * 구역 종류(위험구역 · 작업 구역 · 출입 제한)가 규칙(rules.json)과 불꽃 탐지에 그대로 걸린다.
   * 저장하면 그 스케줄의 scenario.json scenes 에 들어가고, 새 세션 시작부터 그 장면의 구역으로 판정한다. */
  var SC = {opt: null, polys: [], sel: -1, draw: null, drag: null, img: null, iw: 0, ih: 0, video: '', orig: '', hover: null, dirty: false};

  function scType(k) { return (SC.opt ? SC.opt.types : []).filter(function (t) { return t.key === k; })[0] || {label: k, color: '#9aa4af', prefix: 'P'}; }
  function scCam(id) { return (SC.opt ? SC.opt.cameras : []).filter(function (c) { return c.id === id; })[0]; }
  function scSelScene() {
    var sc = META && META.schedules.filter(function (x) { return x.key === $('lv-sched').value; })[0];
    return sc ? sc.scenes.filter(function (x) { return x.name === $('lv-scene').value; })[0] : null;
  }
  function sceneHint() {
    var x = scSelScene();
    $('sc-edit').disabled = !x;
    $('lv-scene-now').disabled = !x;
    $('sc-up').disabled = !$('lv-sched').value;
    $('sc-hint').textContent = !$('lv-sched').value ? '영상 장면은 신호 스케줄마다 따로 둔다 — 스케줄을 먼저 고른다'
      : !x ? '영상 없이 신호로만 판정한다. 영상을 쓰려면 장면을 고르거나 영상을 올린다'
      : x.own ? '구역: 이 장면에 그린 구역으로 판정한다'
      : '구역: 카메라 기본 구역(' + (x.camera || '') + ') — 영상과 안 맞으면 \'고른 장면 구역 고치기\'';
  }
  $('lv-scene').addEventListener('change', function () { sceneHint(); if (LIVE) renderRun(); });

  function scErr(msg) { $('scn-err').textContent = msg || ''; $('scn-err').hidden = !msg; }
  function scNextName(type) {
    var pre = scType(type).prefix || 'P', n = 1;
    var used = SC.polys.map(function (p) { return p.name; });
    while (used.indexOf(pre + n) >= 0) n++;
    return pre + n;
  }

  function openScene(edit) {
    var sched = $('lv-sched').value;
    if (!sched) { flash('신호 스케줄을 먼저 고른다 — 영상 장면은 스케줄마다 따로 둔다', true); return; }
    scErr('');
    api('/api/scene/options?schedule=' + encodeURIComponent(sched)).then(function (o) {
      SC.opt = o; SC.polys = []; SC.sel = -1; SC.draw = null; SC.drag = null; SC.img = null; SC.video = ''; SC.orig = ''; SC.dirty = false;
      var cam0 = o.cameras.filter(function (c) { return c.zone === o.zone; })[0] || o.cameras[0];
      scRenderCams(cam0 ? cam0.id : '');
      $('scn-file').value = ''; $('scn-vinfo').textContent = '';
      $('scn-cm').hidden = true; $('scn-cam-add').setAttribute('aria-expanded', 'false');
      $('scn-tm').hidden = true; $('scn-tm-open').setAttribute('aria-expanded', 'false');
      scRenderTypes();
      var x = edit ? o.scenes.filter(function (s) { return s.name === $('lv-scene').value; })[0] : null;
      if (edit && !x) { flash('고른 장면을 찾지 못했다', true); return; }
      if (x) {
        SC.orig = x.name; SC.video = x.video;
        $('scn-h').textContent = '장면 구역 고치기 — ' + x.name;
        $('scn-file-lb').textContent = '영상 바꾸기 (선택) — 지금: ' + (x.video || '').split('/').pop();
        $('scn-name').value = x.name; $('scn-at').value = x.at || '';
        if (x.camera) $('scn-cam').value = x.camera;
        SC.polys = (x.polygons || []).map(function (p) { return {name: p.name, type: p.type, zone: p.zone, label: p.label || '', points: p.points.map(function (q) { return [q[0], q[1]]; })}; });
        $('scn-lead').textContent = x.own
          ? '이 장면에 그린 구역이다. 점을 끌어 옮기거나 구역을 더하고 지운 뒤 저장한다.'
          : '지금은 카메라 기본 구역(' + (x.camera || '') + '.json)을 쓰고 있다 — 영상에 맞게 점을 옮기고 저장하면 이 장면만의 구역이 된다(카메라 파일은 그대로).';
        $('scn-del').hidden = false;
        scLoadFrame(x.video);
      } else {
        $('scn-h').textContent = '영상 올리기 · 구역 설정';
        $('scn-file-lb').textContent = '영상 파일 (mp4)';
        $('scn-name').value = ''; $('scn-at').value = o.suggest_at || '';
        $('scn-lead').textContent = '스케줄 ‘' + o.title + '’에 영상 장면을 더한다. 영상을 고르면 첫 프레임이 뜨고, 그 위에 구역을 찍는다. 저장하면 영상 장면 목록에 들어간다.';
        $('scn-del').hidden = true;
        $('scn-draw').hidden = true;
      }
      scFillSrc(); scList(); scHelp(); scSaveState();
      $('scn').hidden = false;
      (x ? $('scn-name') : $('scn-file')).focus();
    }).catch(fail);
  }
  function scRenderCams(pick) {
    var o = SC.opt, keep = pick || $('scn-cam').value;
    $('scn-cam').innerHTML = o.cameras.map(function (c) { return opt(c.id, c.id + ' · ' + (c.zone || '') + (c.label ? ' · ' + c.label : '') + (c.polygons.length ? '' : ' · 기본 구역 없음')); }).join('');
    if (keep && scCam(keep)) $('scn-cam').value = keep;
  }
  function scRenderTypes() {
    var o = SC.opt;
    $('scn-types').innerHTML = o.types.map(function (t) {
      return '<button class="btn sm tbtn" type="button" data-add="' + esc(t.key) + '" title="' + esc(t.desc || '') + '"><span class="sw" style="background:' + esc(t.color) + '"></span>' + esc(t.label) + '</button>';
    }).join('');
    $('scn-tm-list').innerHTML = o.types.map(function (t) {
      return '<div class="tm-row"><span class="sw" style="background:' + esc(t.color) + '"></span><b>' + esc(t.label) + '</b><span class="mono">' + esc(t.key) + '</span>' +
        (t.builtin ? '<span class="lv info">판정에 쓰임 · 고정</span>' : '<span class="lv mute">표시 · 기록용</span>') +
        '<span class="note">' + (t.used ? '구역 ' + t.used + '개에서 씀' : '아직 안 씀') + '</span>' +
        (t.builtin ? '' : '<span class="btnrow"><button class="btn sm" type="button" data-tm-edit="' + esc(t.key) + '">고치기</button><button class="btn sm" type="button" data-tm-del="' + esc(t.key) + '"' + (t.used ? ' disabled title="이 종류를 쓰는 구역이 있다 — 그 구역의 종류를 바꾼 뒤 지운다"' : '') + '>지우기</button></span>') + '</div>';
    }).join('');
  }
  /* 종류 · 카메라를 더하거나 지운 뒤 — 그리던 구역은 그대로 두고 고를 거리만 다시 받는다 */
  function scReloadOpt(pickCam) {
    return api('/api/scene/options?schedule=' + encodeURIComponent($('lv-sched').value)).then(function (o) {
      SC.opt.types = o.types; SC.opt.cameras = o.cameras;
      scRenderTypes(); scRenderCams(pickCam); scFillSrc(); scList(); scPaint();
      return api('/api/meta').then(function (m) { META.zone_types = m.zone_types; META.schedules = m.schedules; });
    });
  }
  function tmReset() {
    $('tm-label').value = ''; $('tm-desc').value = ''; $('tm-key').value = ''; $('tm-key').disabled = false;
    $('tm-color').value = '#8fd17a'; $('tm-save').textContent = '종류 더하기'; $('tm-save').removeAttribute('data-key'); $('tm-new').hidden = true;
  }
  $('scn-tm-open').addEventListener('click', function () {
    var p = $('scn-tm'); p.hidden = !p.hidden; this.setAttribute('aria-expanded', p.hidden ? 'false' : 'true');
    if (!p.hidden) { tmReset(); $('tm-label').focus(); }
  });
  $('tm-new').addEventListener('click', tmReset);
  $('tm-save').addEventListener('click', function () {
    var key = this.getAttribute('data-key') || $('tm-key').value.trim();
    var body = {label: $('tm-label').value.trim(), color: $('tm-color').value, desc: $('tm-desc').value.trim(), key: key};
    busy(this, api('/api/scene/type', body)).then(function (d) { flash(d.msg); tmReset(); return scReloadOpt(); }).catch(function (e) { scErr(e.message); });
  });
  $('scn-tm-list').addEventListener('click', function (e) {
    var b = e.target.closest('[data-tm-edit],[data-tm-del]'); if (!b) return;
    var k = b.getAttribute('data-tm-edit') || b.getAttribute('data-tm-del'), t = scType(k);
    if (b.hasAttribute('data-tm-edit')) {
      $('tm-label').value = t.label; $('tm-color').value = t.color; $('tm-desc').value = t.desc || ''; $('tm-key').value = k; $('tm-key').disabled = true;
      $('tm-save').textContent = '고친 내용 저장'; $('tm-save').setAttribute('data-key', k); $('tm-new').hidden = false; $('tm-label').focus();
      return;
    }
    busy(b, api('/api/scene/type/remove', {key: k})).then(function (d) { flash(d.msg); return scReloadOpt(); }).catch(function (e) { scErr(e.message); });
  });
  $('scn-cam-add').addEventListener('click', function () {
    var p = $('scn-cm'); p.hidden = !p.hidden; this.setAttribute('aria-expanded', p.hidden ? 'false' : 'true');
    if (p.hidden) return;
    var zs = (SC.opt.zones || []);
    $('cm-zone').innerHTML = zs.map(function (x) { return opt(x.id, x.id + ' ' + x.name); }).join('');
    var c = scCam($('scn-cam').value), z = (c && c.zone) || SC.opt.zone || (zs[0] && zs[0].id);
    $('cm-zone').value = z;
    var n = 1; while (scCam('CAM-' + z + '-' + ('0' + n).slice(-2))) n++;
    $('cm-id').value = 'CAM-' + z + '-' + ('0' + n).slice(-2); $('cm-label').value = '';
    $('cm-id').focus(); $('cm-id').select();
  });
  $('cm-zone').addEventListener('change', function () {
    var z = this.value, n = 1; if (!/^CAM-/.test($('cm-id').value)) return;
    while (scCam('CAM-' + z + '-' + ('0' + n).slice(-2))) n++;
    $('cm-id').value = 'CAM-' + z + '-' + ('0' + n).slice(-2);
  });
  $('cm-save').addEventListener('click', function () {
    busy(this, api('/api/scene/camera', {camera_id: $('cm-id').value.trim(), zone: $('cm-zone').value, label: $('cm-label').value.trim()}))
      .then(function (d) { flash(d.msg); $('scn-cm').hidden = true; $('scn-cam-add').setAttribute('aria-expanded', 'false'); SC.dirty = true; return scReloadOpt(d.camera_id).then(scSaveState); })
      .catch(function (e) { scErr(e.message); });
  });
  $('cm-del').addEventListener('click', function () {
    var id = $('scn-cam').value; if (!id) return;
    busy(this, api('/api/scene/camera/remove', {camera_id: id})).then(function (d) { flash(d.msg); return scReloadOpt(''); }).catch(function (e) { scErr(e.message); });
  });
  function closeScene() { $('scn').hidden = true; SC.draw = null; SC.drag = null; $('sc-up').focus(); }
  $('sc-up').addEventListener('click', function () { openScene(false); });
  $('sc-edit').addEventListener('click', function () { openScene(true); });
  $('scn-close').addEventListener('click', closeScene);
  $('scn-cancel').addEventListener('click', closeScene);

  function scFillSrc() {
    var o = SC.opt, h = opt('', '다른 구역 불러오기 …');
    o.cameras.forEach(function (c) { if (c.polygons.length) h += opt('cam:' + c.id, '카메라 기본 구역 — ' + c.id + ' (' + c.polygons.length + '개)'); });
    o.scenes.forEach(function (s) { if (s.own && s.name !== SC.orig) h += opt('scene:' + s.name, '장면 ‘' + s.name + '’ 구역 (' + s.polygons.length + '개)'); });
    $('scn-src').innerHTML = h;
  }
  $('scn-load').addEventListener('click', function () {
    var v = $('scn-src').value; if (!v) return;
    var src = v.indexOf('cam:') === 0 ? (scCam(v.slice(4)) || {}).polygons
      : (SC.opt.scenes.filter(function (s) { return 'scene:' + s.name === v; })[0] || {}).polygons;
    SC.polys = (src || []).map(function (p) { return {name: p.name, type: p.type, zone: p.zone, label: p.label || '', points: p.points.map(function (q) { return [q[0], q[1]]; })}; });
    SC.sel = SC.polys.length ? 0 : -1; SC.draw = null; SC.dirty = true;
    scList(); scPaint(); scHelp(); scSaveState();
    flash('구역 ' + SC.polys.length + '개를 불러왔다 — 영상에 맞게 점을 끌어 옮긴다');
  });

  /* 영상 올리기 → 첫 프레임 */
  $('scn-file').addEventListener('change', function () {
    var f = this.files && this.files[0]; if (!f) return;
    var fd = new FormData(); fd.append('schedule', $('lv-sched').value); fd.append('file', f);
    scErr(''); $('scn-vinfo').textContent = '올리는 중 … ' + f.name + ' (' + (f.size / 1048576).toFixed(1) + 'MB)';
    $('scn-save').disabled = true;
    api('/api/scene/upload', fd).then(function (d) {
      SC.video = d.video;
      if (!$('scn-name').value.trim()) $('scn-name').value = f.name.replace(/\.[^.]+$/, '');
      flash(d.msg);
      scLoadFrame(d.video);
    }).catch(function (e) { $('scn-vinfo').textContent = ''; scErr(e.message); scSaveState(); });
  });
  function scLoadFrame(video) {
    var q = '?schedule=' + encodeURIComponent($('lv-sched').value) + '&video=' + encodeURIComponent(video);
    api('/api/scene/info' + q).then(function (info) {
      SC.iw = info.w; SC.ih = info.h;
      $('scn-vinfo').textContent = '영상: ' + video.split('/').pop() + ' · ' + info.w + '×' + info.h + (info.fps ? ' · ' + info.fps + 'fps' : '') + (info.seconds ? ' · ' + info.seconds + '초' : '') +
        ' — 첫 프레임 위에 그린다. 좌표는 화면 비율로 저장돼 해상도가 달라도 같다.';
      var im = new Image();
      im.onload = function () { SC.img = im; $('scn-draw').hidden = false; scSize(); scList(); scHelp(); scSaveState(); };
      im.onerror = function () { scErr('첫 프레임을 불러오지 못했다'); };
      im.src = '/api/scene/frame' + q + '&t=' + Date.now();
    }).catch(function (e) { scErr(e.message); });
  }

  /* 캔버스 크기 · 그리기 */
  var cv = $('scn-cv');
  function scSize() {
    if (!SC.img) return;
    var w = $('scn-stage').clientWidth || 800, h = Math.round(w * SC.img.naturalHeight / SC.img.naturalWidth);
    var r = window.devicePixelRatio || 1;
    cv.width = Math.round(w * r); cv.height = Math.round(h * r); cv.style.height = h + 'px';
    scPaint();
  }
  window.addEventListener('resize', function () { if (!$('scn').hidden) scSize(); });
  function hexA(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function scPaint() {
    if (!SC.img) return;
    var c = cv.getContext('2d'), W = cv.width, H = cv.height, r = window.devicePixelRatio || 1;
    c.clearRect(0, 0, W, H);
    c.drawImage(SC.img, 0, 0, W, H);
    SC.polys.forEach(function (p, i) {
      var col = scType(p.type).color, on = i === SC.sel, pts = p.points;
      if (SC.draw && SC.draw.i === i) return;
      if (pts.length < 2) return;
      c.beginPath(); pts.forEach(function (q, k) { c[k ? 'lineTo' : 'moveTo'](q[0] * W, q[1] * H); }); c.closePath();
      c.fillStyle = hexA(col, on ? 0.30 : 0.16); c.fill();
      c.lineWidth = (on ? 3 : 2) * r; c.strokeStyle = col; c.setLineDash(on ? [] : [7 * r, 5 * r]); c.stroke(); c.setLineDash([]);
      var x0 = Math.min.apply(null, pts.map(function (q) { return q[0]; })) * W, y0 = Math.min.apply(null, pts.map(function (q) { return q[1]; })) * H;
      var tag = p.name + ' · ' + scType(p.type).label;
      c.font = '700 ' + (12 * r) + 'px "IBM Plex Sans KR","Malgun Gothic",sans-serif';
      var tw = c.measureText(tag).width + 10 * r;
      c.fillStyle = col; c.fillRect(x0, Math.max(0, y0 - 18 * r), tw, 18 * r);
      c.fillStyle = '#fff'; c.fillText(tag, x0 + 5 * r, Math.max(0, y0 - 18 * r) + 13 * r);
      if (on) pts.forEach(function (q) { c.fillStyle = '#fff'; c.strokeStyle = col; c.lineWidth = 2 * r; c.fillRect(q[0] * W - 5 * r, q[1] * H - 5 * r, 10 * r, 10 * r); c.strokeRect(q[0] * W - 5 * r, q[1] * H - 5 * r, 10 * r, 10 * r); });
    });
    if (SC.draw) {                                   // 찍는 중인 구역
      var p = SC.polys[SC.draw.i], col = scType(p.type).color, pts = SC.draw.pts;
      c.lineWidth = 2.5 * r; c.strokeStyle = col; c.fillStyle = hexA(col, 0.18);
      if (pts.length) {
        c.beginPath(); pts.forEach(function (q, k) { c[k ? 'lineTo' : 'moveTo'](q[0] * W, q[1] * H); });
        if (SC.hover) c.lineTo(SC.hover[0] * W, SC.hover[1] * H);
        if (pts.length > 2) { c.closePath(); c.fill(); }
        c.stroke();
      }
      pts.forEach(function (q, k) {
        c.beginPath(); c.arc(q[0] * W, q[1] * H, (k === 0 && pts.length > 2 ? 8 : 5) * r, 0, Math.PI * 2);
        c.fillStyle = k === 0 ? col : '#fff'; c.fill(); c.lineWidth = 2 * r; c.strokeStyle = col; c.stroke();
      });
    }
  }
  function scPt(e) {
    var b = cv.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))];
  }
  function scNear(a, b, px) {
    var bb = cv.getBoundingClientRect();
    return Math.abs((a[0] - b[0]) * bb.width) <= px && Math.abs((a[1] - b[1]) * bb.height) <= px;
  }
  function scInside(pt, pts) {
    var x = pt[0], y = pt[1], ins = false;
    for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      var xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) ins = !ins;
    }
    return ins;
  }

  /* 찍기 · 끌기 */
  function scStartDraw(i) {
    SC.draw = {i: i, pts: [], old: SC.polys[i].points};
    SC.sel = i; SC.hover = null;
    scList(); scPaint(); scHelp();
  }
  function scFinishDraw() {
    if (!SC.draw) return;
    if (SC.draw.pts.length < 3) { scErr('점이 3개 이상이어야 한다 — 꼭짓점을 더 찍는다'); return; }
    SC.polys[SC.draw.i].points = SC.draw.pts;
    SC.draw = null; SC.dirty = true; scErr('');
    scList(); scPaint(); scHelp(); scSaveState();
  }
  function scCancelDraw() {
    if (!SC.draw) return;
    var i = SC.draw.i;
    if (SC.draw.old && SC.draw.old.length >= 3) SC.polys[i].points = SC.draw.old;
    else { SC.polys.splice(i, 1); SC.sel = -1; }
    SC.draw = null;
    scList(); scPaint(); scHelp(); scSaveState();
  }
  cv.addEventListener('pointerdown', function (e) {
    if (!SC.img) return;
    var pt = scPt(e);
    if (SC.draw) {
      var d = SC.draw;
      if (d.pts.length > 2 && scNear(pt, d.pts[0], 12)) { scFinishDraw(); return; }
      d.pts.push(pt); scPaint(); scHelp(); return;
    }
    var order = SC.sel >= 0 ? [SC.sel].concat(SC.polys.map(function (_, i) { return i; }).filter(function (i) { return i !== SC.sel; })) : SC.polys.map(function (_, i) { return i; });
    for (var a = 0; a < order.length; a++) {             // 꼭짓점 — 고른 구역부터
      var pi = order[a], pts = SC.polys[pi].points;
      for (var v = 0; v < pts.length; v++) {
        if (scNear(pt, pts[v], 10)) {
          SC.drag = {pi: pi, vi: v}; SC.sel = pi;
          cv.setPointerCapture(e.pointerId); scList(); scPaint(); e.preventDefault(); return;
        }
      }
    }
    for (var k = SC.polys.length - 1; k >= 0; k--) {    // 구역 안 — 고르기
      if (SC.polys[k].points.length > 2 && scInside(pt, SC.polys[k].points)) { SC.sel = k; scList(); scPaint(); return; }
    }
    SC.sel = -1; scList(); scPaint();
  });
  cv.addEventListener('pointermove', function (e) {
    if (SC.drag) {
      SC.polys[SC.drag.pi].points[SC.drag.vi] = scPt(e); SC.dirty = true; scPaint(); return;
    }
    if (SC.draw) { SC.hover = scPt(e); scPaint(); }
  });
  function scEndDrag() { if (SC.drag) { SC.drag = null; scList(); scSaveState(); } }
  cv.addEventListener('pointerup', scEndDrag);
  cv.addEventListener('pointercancel', scEndDrag);
  cv.addEventListener('pointerleave', function () { if (SC.draw) { SC.hover = null; scPaint(); } });
  cv.addEventListener('contextmenu', function (e) { if (SC.draw) { e.preventDefault(); SC.draw.pts.pop(); scPaint(); scHelp(); } });
  document.addEventListener('keydown', function (e) {
    if ($('scn').hidden || !SC.draw) return;
    var tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    if (e.key === 'Enter') { e.preventDefault(); scFinishDraw(); }
    else if (e.key === 'Escape') { e.preventDefault(); scCancelDraw(); }
    else if (e.key === 'Backspace') { e.preventDefault(); SC.draw.pts.pop(); scPaint(); scHelp(); }
  });

  function scHelp() {
    var h = $('scn-help');
    $('scn-stage').classList.toggle('idle', !SC.draw);
    if (!SC.img) { h.innerHTML = ''; return; }
    if (SC.draw) {
      var p = SC.polys[SC.draw.i], n = SC.draw.pts.length;
      h.innerHTML = '<span><b>' + esc(p.name) + ' · ' + esc(scType(p.type).label) + '</b> — 꼭짓점을 차례로 누른다 (' + n + '개). 첫 점을 다시 누르거나 Enter 로 닫는다</span>' +
        '<button class="btn sm" type="button" data-h="done"' + (n < 3 ? ' disabled' : '') + '>완료</button>' +
        '<button class="btn sm" type="button" data-h="undo"' + (n ? '' : ' disabled') + '>점 하나 지우기</button>' +
        '<button class="btn sm" type="button" data-h="cancel">취소</button>';
    } else {
      h.innerHTML = SC.polys.length ? '<span>구역을 누르면 고르고, 흰 네모(꼭짓점)를 끌면 옮긴다. 새 구역은 위 ‘구역 추가’ 버튼</span>'
        : '<span>위 ‘구역 추가’에서 종류를 고른 뒤, 첫 프레임 위에 꼭짓점을 차례로 누른다</span>';
    }
  }
  $('scn-help').addEventListener('click', function (e) {
    var b = e.target.closest('[data-h]'); if (!b) return;
    var k = b.getAttribute('data-h');
    if (k === 'done') scFinishDraw(); else if (k === 'cancel') scCancelDraw();
    else if (k === 'undo' && SC.draw) { SC.draw.pts.pop(); scPaint(); scHelp(); }
  });
  $('scn-types').addEventListener('click', function (e) {
    var b = e.target.closest('[data-add]'); if (!b || !SC.img) return;
    if (SC.draw) scCancelDraw();
    var t = b.getAttribute('data-add'), cam = scCam($('scn-cam').value);
    SC.polys.push({name: scNextName(t), type: t, zone: (cam && cam.zone) || SC.opt.zone || (SC.opt.zones[0] || {}).id, label: scType(t).label, points: []});
    scStartDraw(SC.polys.length - 1);
  });

  /* 구역 목록 */
  function scList() {
    var o = SC.opt, el = $('scn-list');
    if (!o) return;
    if (!SC.polys.length) { el.innerHTML = '<div class="empty">아직 구역이 없다. 위험구역(상시 또는 작업 중)이 하나는 있어야 영상 불꽃이 점화원으로 잡힌다.</div>'; return; }
    el.innerHTML = SC.polys.map(function (p, i) {
      var t = scType(p.type), drawing = SC.draw && SC.draw.i === i;
      return '<div class="scn-item' + (i === SC.sel ? ' on' : '') + (p.points.length < 3 && !drawing ? ' bad' : '') + '" data-i="' + i + '">' +
        '<div class="r"><span class="sw" style="background:' + esc(t.color) + '"></span>' +
        '<input class="nm" data-f="name" value="' + esc(p.name) + '" aria-label="구역 이름 (영문 · 숫자)" maxlength="20">' +
        '<select data-f="type" aria-label="구역 종류">' + o.types.map(function (x) { return opt(x.key, x.label, x.key === p.type); }).join('') + '</select></div>' +
        '<div class="r"><select data-f="zone" aria-label="구역">' + o.zones.map(function (z) { return opt(z.id, z.id + ' ' + z.name, z.id === p.zone); }).join('') + '</select></div>' +
        '<div class="r"><input class="lbl" data-f="label" value="' + esc(p.label) + '" placeholder="설명 (경보 문장에 쓰인다)" aria-label="구역 설명"></div>' +
        '<div class="r"><span class="meta">' + (drawing ? '찍는 중 …' : '점 ' + p.points.length + '개') + ' · ' + esc(t.desc) + '</span></div>' +
        '<div class="r"><button class="btn sm" type="button" data-a="redraw">다시 찍기</button><button class="btn sm" type="button" data-a="del">지우기</button></div>' +
        '</div>';
    }).join('');
  }
  $('scn-list').addEventListener('input', function (e) {
    var it = e.target.closest('.scn-item'), f = e.target.getAttribute('data-f'); if (!it || !f) return;
    var p = SC.polys[+it.getAttribute('data-i')];
    if (f === 'name') p.name = e.target.value.trim();
    else if (f === 'label') p.label = e.target.value;
    SC.dirty = true; scPaint(); scSaveState();
  });
  $('scn-list').addEventListener('change', function (e) {
    var it = e.target.closest('.scn-item'), f = e.target.getAttribute('data-f'); if (!it || !f) return;
    var p = SC.polys[+it.getAttribute('data-i')];
    if (f === 'type') {
      var old = scType(p.type);
      if (!p.label || p.label === old.label) p.label = scType(e.target.value).label;
      p.type = e.target.value; scList();
    } else if (f === 'zone') p.zone = e.target.value;
    SC.dirty = true; scPaint(); scHelp(); scSaveState();
  });
  $('scn-list').addEventListener('click', function (e) {
    var it = e.target.closest('.scn-item'); if (!it) return;
    var i = +it.getAttribute('data-i'), b = e.target.closest('[data-a]');
    if (!b) { if (SC.sel !== i && !SC.draw) { SC.sel = i; scPaint(); it.parentNode.querySelectorAll('.scn-item').forEach(function (n) { n.classList.toggle('on', n === it); }); } return; }
    if (SC.draw) scCancelDraw();
    if (b.getAttribute('data-a') === 'del') {
      SC.polys.splice(i, 1); SC.sel = -1; SC.dirty = true;
      scList(); scPaint(); scHelp(); scSaveState();
    } else scStartDraw(i);
  });

  /* 저장 */
  function scProblem() {
    if (!SC.video) return '영상을 올린다';
    if (!SC.img) return '첫 프레임을 불러오는 중이다';
    if (SC.draw) return '찍는 중인 구역을 먼저 닫는다 (완료 또는 Enter)';
    if (!SC.polys.length) return '구역을 하나 이상 그린다';
    var names = {};
    for (var i = 0; i < SC.polys.length; i++) {
      var p = SC.polys[i];
      if (p.points.length < 3) return p.name + ': 점이 3개 이상이어야 한다';
      if (!/^[A-Za-z0-9_.-]{1,20}$/.test(p.name)) return (i + 1) + '번 구역: 이름은 영문 · 숫자로 (영상 위에 적힌다 — 예: E1, W1)';
      if (names[p.name]) return '구역 이름 ‘' + p.name + '’ 가 두 번 나온다';
      names[p.name] = 1;
    }
    if (!SC.polys.some(function (p) { return p.type === 'hazard' || p.type === 'hazard_repair'; })) return '위험구역(상시 또는 작업 중)을 하나 이상 그린다 — 없으면 영상 불꽃이 점화원으로 잡히지 않는다';
    return '';
  }
  function scSaveState() {
    var why = scProblem();
    $('scn-save').disabled = $('scn-save-play').disabled = !!why;
    $('scn-save').title = why;
    $('scn-save-play').title = why || '저장하고 이 장면으로 관제 화면에서 바로 영상을 튼다';
  }
  function scSave(btn, play) {
    var why = scProblem(); if (why) { scErr(why); return; }
    var body = {schedule: $('lv-sched').value, orig: SC.orig, name: $('scn-name').value.trim(), at: $('scn-at').value.trim(),
      camera: $('scn-cam').value, video: SC.video, polygons: SC.polys};
    scErr('');
    busy(btn, api('/api/scene/save', body)).then(function (d) {
      flash(d.msg); SC.dirty = false; closeScene();
      return scRefresh(d.name).then(function () {
        if (!play) return;
        $('lv-panel').hidden = false; $('lv-more').setAttribute('aria-expanded', 'true');
        window.scrollTo({top: 0, behavior: 'smooth'});
        return sceneNow(null, liveForm());
      });
    }).catch(function (e) { scErr(e.message); });
  }
  $('scn-save').addEventListener('click', function () { scSave(this, false); });
  $('scn-save-play').addEventListener('click', function () { scSave(this, true); });
  $('scn-del').addEventListener('click', function () {
    var name = SC.orig; if (!name) return;
    ask({title: '장면 빼기', note: '‘' + name + '’ 을 영상 장면 목록에서 뺀다. 영상 파일은 지우지 않는다(사업장 패키지 videos/ 에 남는다).', fields: []}, function () {
      return api('/api/scene/remove', {schedule: $('lv-sched').value, name: name}).then(function (d) { flash(d.msg); closeScene(); scRefresh(''); });
    });
  });
  function scRefresh(pick) {
    return api('/api/meta').then(function (m) {
      META.schedules = m.schedules; META.zone_types = m.zone_types || META.zone_types; META.cameras = m.cameras || META.cameras;
      var keep = pick != null ? pick : $('lv-scene').value;
      fillScenes(); $('lv-scene').value = keep; if ($('lv-scene').value !== keep) $('lv-scene').value = '';
      sceneHint();
    }).catch(fail);
  }

  /* ---------- 시작 ---------- */
  function fillMeta() {
    $('brand-sub').textContent = (META.site_name || META.package) + ' · 구역 ' + META.zones[0].id + '~' + META.zones[META.zones.length - 1].id;
    $('ft-pkg').textContent = META.package + (META.sample ? ' · 예시 데이터 켜짐' : '');
    $('ft-in').textContent = 'CSV 스케줄 · 버튼 · 카메라 ' + META.cams_total + '대';
    var zOpts = META.zones.map(function (x) { return opt(x.id, x.id + ' ' + x.name); }).join('');
    $('f-zone').innerHTML = opt('전체', '전체') + zOpts;
    $('vc-zone').innerHTML = zOpts; $('sg-zone').innerHTML = zOpts;
    $('sg-zone').value = META.focus_zone;
    $('reg-zone').innerHTML = META.zones.map(function (x) { return opt(x.id, x.id + ' ' + x.name + (x.piping ? '' : ' (계통도 없음)')); }).join('');
    $('reg-mode').innerHTML = META.work_types.map(function (w) { return opt(w, w); }).join('');
    $('lv-sched').innerHTML = opt('', '스케줄 없음 — 버튼으로만') + META.schedules.map(function (s) { return opt(s.key, s.title, s.key === META.live.schedule); }).join('');
    $('lv-rs').innerHTML = META.rulesets.map(function (r) { return opt(r.key, r.label, r.key === META.live.ruleset); }).join('');
    fillScenes(); $('lv-scene').value = META.live.scene || '';
    $('lv-start').value = META.live.start;
    $('lv-btns').innerHTML = META.buttons.map(function (b) { return '<button class="btn sm" type="button" data-press="' + esc(b.key) + '">' + esc(b.key) + ' · ' + esc(b.label) + '</button>'; }).join('') || '<span class="note">사업장 패키지 buttons.json 이 비어 있다</span>';
    $('sg-sig').innerHTML = META.signals.map(function (s) { return opt(s.key, s.key + ' · ' + s.label); }).join('');
    $('dt-ind').innerHTML = META.industries.map(function (x) { return opt(x, x, x === META.profile.industry); }).join('');
    $('dt-n').value = META.profile.workers;
    $('dt-cat').innerHTML = opt('전체', '전체') + META.duty_cats.map(function (c) { return opt(c, c); }).join('');
    $('dt-who').innerHTML = META.staff.map(function (p) { return opt(p.id, p.label); }).join('');
    VC.kind = META.voice.kinds[0]; VC.state = META.voice.states[1] || META.voice.states[0];
    $('vc-kind').innerHTML = META.voice.kinds.map(function (k, i) { return '<button type="button" data-v="' + esc(k) + '"' + (i === 0 ? ' class="on"' : '') + '>' + esc(k) + '</button>'; }).join('');
    $('vc-state').innerHTML = META.voice.states.map(function (k) { return '<button type="button" data-v="' + esc(k) + '"' + (k === VC.state ? ' class="on"' : '') + '>' + esc(k) + '</button>'; }).join('');
    $('iso-by').value = store('iso-by') || '';
    curZone = META.focus_zone;
    var sp = META.live.speed;
    $('lv-speed').querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', +b.getAttribute('data-v') === sp); });
  }
  function tick() {
    tickStatus();
    if (curScreen === 'live') return api('/api/live').then(function (d) { LIVE = d; renderLive(); }).catch(function () {});
  }
  api('/api/meta').then(function (m) {
    META = m; fillMeta();
    var start = (location.hash || '').replace('#', '');
    show(start && document.querySelector('.screen[data-screen="' + start + '"]') ? start : 'live');
    tickStatus();
    setInterval(function () { if (!document.hidden) tickStatus(); }, 2000);
    setInterval(function () { if (!document.hidden && curScreen === 'live') api('/api/live').then(function (d) { LIVE = d; renderLive(); }).catch(function () {}); }, 1000);
  }).catch(function (e) {
    document.querySelector('.main').insertAdjacentHTML('afterbegin', '<div class="bar crit"><span>' + esc(e.message) + '</span></div>');
  });
})();
