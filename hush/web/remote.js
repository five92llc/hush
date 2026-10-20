/* Hush phone remote: talks to the server's relay, which passes commands to a screen and its playback state back. */
(() => {
  const $ = (s) => document.querySelector(s);
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
    return el;
  };
  const fmt = (s) => {
    s = Math.max(0, Math.round(s || 0));
    const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
  };
  const initials = (t) => (t || "?").replace(/[\[(][^\])]*[\])]/g, " ").split(/[^\p{L}\p{N}]+/u).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  const title = (n) => (n || "").replace(/\s*[\[(][^\])]*[\])]/g, "").trim() || n;
  let toastTimer;
  const toast = (msg) => { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 2200); };

  let ws = null, retry = 0, screens = [], states = {}, stateAt = 0;
  let current = localStorage.getItem("hush.remote.screen") || "";
  let tab = "continue", cache = {}, view = null;

  async function api(path, opts = {}) {
    const r = await fetch(path, { credentials: "same-origin", ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
    if (r.status === 401) { showLogin(); throw new Error("Sign in"); }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
    return r.json();
  }

  /* ---------- connection ---------- */
  function connect() {
    if (ws && ws.readyState <= 1) return;
    ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/remote/ws`);
    ws.onopen = () => { retry = 0; ws.send(JSON.stringify({ type: "hello", role: "remote" })); $("#dot").className = "dot"; };
    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.type === "screens") { screens = m.screens; for (const s of screens) states[s.id] = s.state; stateAt = Date.now(); render(); }
      else if (m.type === "state") { states[m.id] = m.state; stateAt = Date.now(); render(); }
      else if (m.type === "error") toast(m.message || "That didn't work");
    };
    ws.onclose = (ev) => {
      $("#dot").className = "dot off";
      if (ev.code === 4401) { showLogin(); return; }
      // A refused handshake (not signed in, or the session ended) has no close code: check the session before retrying.
      if (retry >= 1) api("/api/session").then((x) => { if (x.auth_required && !x.logged_in) showLogin(); }).catch(() => {});
      setTimeout(connect, Math.min(10000, 800 * 2 ** retry++));
    };
  }
  function send(cmd, args = {}) {
    if (!current) { toast("Choose a screen first"); return; }
    if (!ws || ws.readyState !== 1) { toast("Reconnecting…"); return; }
    ws.send(JSON.stringify({ type: "cmd", to: current, cmd, args }));
    if (navigator.vibrate) navigator.vibrate(8);
  }

  /* ---------- now playing ---------- */
  function render() {
    const sel = $("#screen");
    if (!screens.some((s) => s.id === current)) current = screens.length === 1 ? screens[0].id : (screens.find((s) => s.state?.playing)?.id || screens[0]?.id || "");
    sel.replaceChildren(...screens.map((s) => h("option", { value: s.id, selected: s.id === current }, s.name)));
    $("#none").hidden = screens.length > 0;
    sel.hidden = screens.length < 2 && screens.length > 0 ? true : false;
    $("#now").hidden = !current;
    if (!current) return;
    const st = states[current] || {};
    const live = !!st.live;
    $("#title").textContent = st.active ? st.title || "Playing" : "Nothing playing";
    $("#chan-line").hidden = !st.channel; if (st.channel) $("#chan-line").textContent = `Channel ${st.channel.num}`;
    $("#sub").textContent = !st.active ? `On ${screens.find((s) => s.id === current)?.name || "screen"}` : live ? "Live" : (st.playing ? "Playing" : "Paused");
    const art = $("#art"), wrap = art.parentElement, fb = $("#art-fallback");
    const src = st.channel?.logo || (st.mediaKey ? `/api/art/${st.mediaKey}.jpg` : null);
    wrap.className = "art" + (st.channel ? " wide logo" : "");
    if (src && art.dataset.src !== src) { art.dataset.src = src; art.hidden = false; art.onerror = () => { art.hidden = true; }; art.src = src; }
    if (!src) art.hidden = true;
    fb.textContent = art.hidden ? initials(st.title) : "";
    $("#bar").hidden = $("#times").hidden = !st.active || live;
    $("#pp").textContent = st.playing ? "⏸" : "▶";
    $("#live-pad").hidden = !st.channel;
    renderKeyboard(st);
    const f = $("#filter"); f.textContent = st.filterOn === false ? "Filter off" : "Filter on"; f.setAttribute("aria-pressed", String(st.filterOn !== false));
    ticker();
  }
  function ticker() {
    const st = states[current] || {};
    if (!st.active || st.live) return;
    const pos = st.position + (st.playing ? (Date.now() - stateAt) / 1000 : 0);
    $("#t-now").textContent = fmt(pos); $("#t-dur").textContent = fmt(st.duration);
    $("#bar-i").style.width = `${st.duration ? Math.min(100, (pos / st.duration) * 100) : 0}%`;
  }
  setInterval(ticker, 500);

  /* ---------- typing on the phone into the screen's text box ---------- */
  let kbdTimer, kbdWasEditing = false;
  function renderKeyboard(st) {
    const t = st.text || { on: false }, box = $("#kbd"), input = $("#kbd-input");
    box.hidden = !current;
    $("#kbd-label").textContent = t.on ? t.label : "Keyboard";
    $("#kbd-hint").textContent = t.on ? (t.password ? "Typing a password: it is sent as you type." : "Typed text appears on the screen as you type.") : "Highlight a text box on the screen, then type here.";
    input.disabled = !t.on; input.type = t.password ? "password" : "text";
    if (t.on && document.activeElement !== input) input.value = t.value || "";             // never overwrite what is being typed right now
    if (!t.on && document.activeElement !== input) input.value = "";
    if (t.editing && !kbdWasEditing) setTimeout(() => input.focus(), 50);                  // the screen opened its keyboard: bring up the phone's
    kbdWasEditing = !!t.editing;
  }
  function sendText(submit) {
    clearTimeout(kbdTimer);
    send("text", { value: $("#kbd-input").value, submit: !!submit });
  }
  $("#kbd-input").addEventListener("input", () => { clearTimeout(kbdTimer); kbdTimer = setTimeout(() => sendText(false), 80); });
  $("#kbd-input").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); sendText(true); } });
  $("#kbd-go").addEventListener("click", () => sendText(true));
  $("#kbd-clear").addEventListener("click", () => { $("#kbd-input").value = ""; sendText(false); $("#kbd-input").focus(); });

  /* ---------- browse and play on the screen ---------- */
  const play = (a) => { send("open", a); toast(`Playing on ${screens.find((s) => s.id === current)?.name || "the screen"}`); };
  const row = ({ thumb, wide, logo, name, small, go, onTap }) => h("li", {}, h("button", { type: "button", onclick: onTap },
    h("span", { class: `th${wide ? " wide" : ""}${logo ? " logo" : ""}` }, thumb ? h("img", { src: thumb, alt: "", loading: "lazy", onerror: (e) => { e.target.remove(); } }) : initials(name)),
    h("span", { class: "nm" }, name, small ? h("small", {}, small) : null), h("span", { class: "go" }, go || "▶")));

  async function loadTab() {
    const q = $("#q").value.trim().toLowerCase(), list = $("#list"), note = $("#list-note");
    note.textContent = ""; $("#q").hidden = tab === "continue";
    try {
      if (tab === "continue") {
        const items = await api("/api/progress/recent?limit=20");
        note.textContent = items.length ? "" : "Nothing started yet.";
        list.replaceChildren(...items.map((it) => row({ thumb: it.art_url, wide: true, name: it.title, small: [it.subtitle, it.duration ? `${fmt(it.duration - it.position)} left` : ""].filter(Boolean).join(" · "),
          onTap: () => play({ src: it.source_id, item: it.item_id, title: it.title }) })));
      } else if (tab === "movies") {
        const all = cache.movies ||= await api("/api/library/movies");
        const shown = all.filter((m) => !q || m.title.toLowerCase().includes(q)).slice(0, 80);
        note.textContent = `${shown.length} of ${all.length}`;
        list.replaceChildren(...shown.map((m) => row({ thumb: m.art_url, name: m.title, small: m.year || "", onTap: () => play({ src: m.source_id, item: m.item_id, title: m.title }) })));
      } else if (tab === "shows") {
        if (view) return showEpisodes(view);
        const all = cache.shows ||= await api("/api/library/shows");
        const shown = all.filter((s) => !q || s.title.toLowerCase().includes(q)).slice(0, 80);
        note.textContent = `${shown.length} of ${all.length}`;
        list.replaceChildren(...shown.map((s) => row({ thumb: s.art_url, name: s.title, small: `${s.episodes} episodes`, go: "›", onTap: () => { view = s.show_key; loadTab(); } })));
      } else {
        const path = q ? `/api/live/channels?q=${encodeURIComponent(q)}&limit=60` : "/api/live/channels?recent=true&limit=30";
        const r = await api(path);
        note.textContent = q ? `${r.total} channels` : (r.channels.length ? "Recently watched. Search to find any channel." : "Search for a channel.");
        list.replaceChildren(...r.channels.map((c) => row({ thumb: c.logo_url, wide: true, logo: true, name: title(c.name), small: c.groups.slice(0, 2).join(" · "),
          onTap: () => play({ src: "url", item: c.item_id, title: c.name, chan: c.key, logo: c.logo_url, groups: c.groups }) })));
      }
    } catch (e) { note.textContent = e.message; }
  }
  async function showEpisodes(key) {
    const d = await api(`/api/library/shows/${key}`);
    $("#list-note").textContent = d.show.title;
    $("#list").replaceChildren(
      h("li", {}, h("button", { type: "button", onclick: () => { view = null; loadTab(); } }, h("span"), h("span", { class: "nm" }, "‹ All shows"), h("span"))),
      ...d.episodes.map((e) => row({ thumb: e.art_url, wide: true, name: `S${String(e.season).padStart(2, "0")}E${String(e.episode).padStart(2, "0")}${e.title ? ` · ${e.title}` : ""}`,
        small: e.watched ? "Watched" : (e.position ? `Resume ${fmt(e.position)}` : ""), onTap: () => play({ src: e.source_id, item: e.item_id, title: e.title || d.show.title }) })));
  }

  /* ---------- wiring ---------- */
  function bind() {
    document.addEventListener("click", (e) => {
      const b = e.target.closest("[data-cmd]");
      if (b) { let args = {}; try { args = JSON.parse(b.dataset.args || "{}"); } catch { /* none */ } send(b.dataset.cmd, args); }
    });
    $("#screen").addEventListener("change", (e) => { current = e.target.value; localStorage.setItem("hush.remote.screen", current); render(); });
    $("#digits").replaceChildren(..."1234567890".split("").map((d) => h("button", { type: "button", onclick: () => send("digits", { digits: d }) }, d)));
    document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
      tab = b.dataset.tab; view = null; $("#q").value = "";
      document.querySelectorAll(".tabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      loadTab();
    }));
    let t; $("#q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(loadTab, 300); });
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") connect(); });
  }
  function showLogin() { $("#remote").hidden = true; $("#login").hidden = false; }
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault(); $("#login-error").textContent = "";
    try { await api("/api/login", { method: "POST", body: JSON.stringify({ password: $("#password").value }) }); $("#password").value = ""; startRemote(); }
    catch (err) { $("#login-error").textContent = err.message; }
  });
  function startRemote() { $("#login").hidden = true; $("#remote").hidden = false; connect(); loadTab(); }

  bind();
  api("/api/session").then((s) => (s.auth_required && !s.logged_in ? showLogin() : startRemote())).catch(showLogin);
})();
