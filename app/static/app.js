(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let S = null;

  const api = async (method, url, body) => {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    return r.json();
  };
  const toast = (msg) => {
    const t = $("#toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2400);
  };
  const daysAgo = (iso) => {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    return d <= 0 ? "today" : d === 1 ? "1 day ago" : `${d} days ago`;
  };

  async function load() {
    S = await api("GET", "/api/state");
    render();
  }

  const DEFAULT_COLORS = { color_primary: "#006a7a", color_highlight: "#f4c430", color_ink: "#0b2d3a" };
  function applyBrand() {
    const s = S.settings, root = document.documentElement.style;
    const name = s.brand_name || s.company_name || "HQ";
    const hl = (s.brand_highlight || "").trim();
    const i = hl ? name.indexOf(hl) : -1;
    $("#wordmark").innerHTML = i < 0 ? esc(name) : esc(name.slice(0, i)) + `<span class="g">${esc(hl)}</span>` + esc(name.slice(i + hl.length));
    $("#brand-label").textContent = s.brand_label || "";
    $(".sub-rule").style.display = s.brand_label ? "" : "none";
    $("#brand-tagline").textContent = s.brand_tagline || "";
    document.title = s.brand_label ? `${name} ${s.brand_label}` : name;
    const v = `?v=${s.logo_version || 0}`;
    ["#brand-mark", "#ob-mark", "#logo-preview"].forEach((q) => ($(q).src = "/brand/logo" + v));
    $("#favicon").href = s.has_logo ? "/brand/logo" + v : "/static/icon.png";
    const p = s.color_primary, g = s.color_highlight, k = s.color_ink;
    const set = (n, val) => root.setProperty(n, val), unset = (n) => root.removeProperty(n);
    if (p && p !== DEFAULT_COLORS.color_primary) {
      set("--ocean-deep", p);
      set("--tropical-teal", `color-mix(in srgb, ${p} 62%, white)`);
      set("--lagoon", `color-mix(in srgb, ${p} 40%, white)`);
    } else ["--ocean-deep", "--tropical-teal", "--lagoon"].forEach(unset);
    if (g && g !== DEFAULT_COLORS.color_highlight) set("--paradise-gold", g); else unset("--paradise-gold");
    if (k && k !== DEFAULT_COLORS.color_ink) set("--island-night", k); else unset("--island-night");
  }

  function render() {
    applyBrand();
    const now = new Date();
    const h = now.getHours();
    const who = (S.settings.owner_name || "").trim();
    $("#greeting").textContent = `Good ${h < 12 ? "morning" : h < 17 ? "afternoon" : "evening"}${who ? ", " + who : ""}.`;
    $("#today-label").textContent = now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    renderBrief(); renderToday(); renderBoard(); renderLinks(); renderUsage();
  }

  function renderBrief() {
    const b = S.brief;
    const body = $("#brief-body");
    if (!b) {
      body.innerHTML = `<p class="muted">No brief yet. It writes itself each morning at ${esc(niceTime(S.settings.brief_time))}, or tap Refresh brief.</p>`;
      $("#brief-source").textContent = ""; $("#brief-meta").textContent = "";
      return;
    }
    const lines = b.text.split("\n").map((l) => l.trim()).filter(Boolean);
    const paras = lines.filter((l) => !l.startsWith("- "));
    const bullets = lines.filter((l) => l.startsWith("- ")).map((l) => l.slice(2));
    body.innerHTML = paras.map((p) => `<p>${esc(p)}</p>`).join("") +
      (bullets.length ? `<ul>${bullets.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
    const src = $("#brief-source");
    src.textContent = b.source === "claude" ? "Written by Claude" : "Plain brief";
    src.className = "pill" + (b.source === "claude" ? " claude" : "");
    const t = new Date(b.generated_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    const stale = b.date !== S.today ? ` (from ${b.date})` : "";
    $("#brief-meta").textContent = `Updated ${t}${stale}${b.note ? ". " + b.note : ""}`;
  }

  function renderToday() {
    const f = S.brief?.facts;
    const w = f?.weather;
    $("#weather").innerHTML = w && w.high_f !== undefined
      ? `<div class="temp">${esc(w.now_f)}&deg;</div>
         <div><div class="cond">${esc(w.conditions)}</div>
         <div class="muted small">High ${esc(w.high_f)}&deg;, low ${esc(w.low_f)}&deg;, ${esc(w.rain_chance)}% rain. ${esc(w.location)}</div></div>`
      : `<div class="muted small">${esc(w?.error === "no location set" ? "Add your town in Settings to see weather." : (w?.error || "Weather shows up with the first brief."))}</div>`;

    const cal = f?.calendar;
    const ev = $("#events");
    if (cal?.events?.length) {
      ev.innerHTML = cal.events.map((e) => `<li><span class="when">${e.all_day ? "All day" : esc(e.start)}</span>
        <span>${esc(e.title)}${e.location ? `<span class="loc">${esc(e.location)}</span>` : ""}</span></li>`).join("");
    } else if (cal?.events) {
      ev.innerHTML = `<li><span class="when">Open</span><span class="muted">Nothing on the calendar.</span></li>`;
    } else {
      ev.innerHTML = `<li><span class="when">&nbsp;</span><span class="muted small">${esc(cal?.error === "no calendar connected" ? "Add your calendar's iCal address in Settings." : (cal?.error || ""))}</span></li>`;
    }
  }

  function renderBoard() {
    const stall = S.settings.stall_days || 14;
    $("#board").innerHTML = S.stages.map((stage) => {
      const apps = S.pipeline.filter((a) => a.stage === stage);
      return `<div class="col" data-stage="${esc(stage)}">
        <div class="col-head"><h3>${esc(stage)}</h3><span class="count">${apps.length}</span></div>
        ${apps.length ? apps.map((a) => {
          const d = Math.floor((Date.now() - new Date(a.updated).getTime()) / 86400000);
          const stalled = stage !== "Live" && d >= stall;
          return `<button class="app" data-id="${esc(a.id)}">
            <div class="name">${esc(a.name)}</div>
            ${a.tagline ? `<div class="line">${esc(a.tagline)}</div>` : ""}
            ${a.next_step ? `<div class="next"><b>Next:</b> ${esc(a.next_step)}</div>` : ""}
            <div class="meta"><span>${daysAgo(a.updated)}</span>${stalled ? `<span class="stall">Needs a look</span>` : ""}</div>
          </button>`;
        }).join("") : `<div class="empty-col">Nothing here.</div>`}
      </div>`;
    }).join("");
  }

  function renderLinks() {
    const groups = {};
    S.links.forEach((l) => (groups[l.group] ||= []).push(l));
    $("#links").innerHTML = Object.entries(groups).map(([g, ls]) => `<div class="link-group"><h3>${esc(g)}</h3>
      ${ls.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}<span>${esc(l.url.replace(/^https?:\/\//, ""))}</span></a>`).join("")}
    </div>`).join("") || `<p class="muted">No links yet.</p>`;
  }

  function renderUsage() {
    const u = S.usage;
    $("#usage").textContent = `Claude briefs this month: ${u.calls} of ${u.cap}`;
  }

  // ----- app dialog -----
  const appDlg = $("#app-dialog"), appForm = $("#app-form");
  let editingId = null;
  $("#stage-select").innerHTML = ["Idea", "Building", "Testing", "Submitted", "Live"].map((s) => `<option>${s}</option>`).join("");

  function openApp(a) {
    editingId = a?.id || null;
    $("#app-dialog-title").textContent = a ? "Edit app" : "Add app";
    $("#delete-app").style.visibility = a ? "visible" : "hidden";
    ["name", "tagline", "stage", "next_step", "notes"].forEach((k) => (appForm.elements[k].value = a?.[k] ?? (k === "stage" ? "Idea" : "")));
    appDlg.showModal();
  }
  $("#board").addEventListener("click", (e) => {
    const b = e.target.closest(".app"); if (!b) return;
    openApp(S.pipeline.find((a) => a.id === b.dataset.id));
  });
  $("#add-app").onclick = () => openApp(null);
  appForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(appForm));
    try {
      if (editingId) await api("PUT", `/api/pipeline/${editingId}`, body);
      else await api("POST", "/api/pipeline", body);
      appDlg.close(); await load(); toast("Saved");
    } catch (err) { toast(err.message); }
  });
  $("#delete-app").onclick = async () => {
    if (!editingId || !confirm("Delete this app from the board?")) return;
    await api("DELETE", `/api/pipeline/${editingId}`); appDlg.close(); await load(); toast("Removed");
  };

  // ----- bulk import -----
  const impDlg = $("#import-dialog"), impForm = $("#import-form");
  $("#import-apps").onclick = () => { impForm.elements.text.value = ""; impDlg.showModal(); };
  impForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const r = await api("POST", "/api/pipeline/import", { text: impForm.elements.text.value });
      impDlg.close(); await load(); toast(`Added ${r.added} app${r.added === 1 ? "" : "s"}`);
    } catch (err) { toast(err.message); }
  });

  // ----- links dialog -----
  const linksDlg = $("#links-dialog");
  const linkRow = (l = {}) => `<div class="link-row" data-id="${esc(l.id || "")}">
    <input placeholder="Group" value="${esc(l.group || "")}" aria-label="Group">
    <input placeholder="Label" value="${esc(l.label || "")}" aria-label="Label">
    <input placeholder="https://" value="${esc(l.url || "")}" aria-label="Address"></div>`;
  $("#edit-links").onclick = () => { $("#links-rows").innerHTML = S.links.map(linkRow).join(""); linksDlg.showModal(); };
  $("#add-link-row").onclick = () => $("#links-rows").insertAdjacentHTML("beforeend", linkRow({ group: "General" }));
  $("#links-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const rows = [...document.querySelectorAll(".link-row")].map((r) => {
      const [g, l, u] = r.querySelectorAll("input");
      return { id: r.dataset.id, group: g.value, label: l.value, url: u.value };
    });
    try { await api("PUT", "/api/links", rows); linksDlg.close(); await load(); toast("Links saved"); }
    catch (err) { toast(err.message); }
  });

  // ----- settings -----
  const setDlg = $("#settings-dialog"), setForm = $("#settings-form");
  $("#open-settings").onclick = () => {
    const s = S.settings;
    ["owner_name", "company_name", "brand_name", "brand_highlight", "brand_label", "brand_tagline", "color_primary", "color_highlight", "color_ink", "model", "monthly_call_cap", "brief_time", "stall_days", "location_name", "latitude", "longitude"].forEach((k) => (setForm.elements[k].value = s[k] ?? ""));
    setForm.elements.anthropic_api_key.value = ""; setForm.elements.ical_url.value = "";
    $("#key-status").textContent = s.has_api_key ? `Key saved (${s.api_key_hint}). Leave blank to keep it.` : "No key yet. Without one, you still get a plain brief.";
    $("#ical-status").textContent = s.has_ical_url ? "Calendar connected. Leave blank to keep it." : "Google Calendar: Settings, your calendar, Integrate calendar, Secret address in iCal format.";
    setDlg.showModal();
  };
  setForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/api/settings", Object.fromEntries(new FormData(setForm))); setDlg.close(); await load(); toast("Settings saved"); }
    catch (err) { toast(err.message); }
  });
  $("#logo-file").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    if (f.size > 1000000) { toast("Pick an image under 1 MB"); return; }
    try {
      const r = await fetch("/api/brand/logo", { method: "POST", headers: { "Content-Type": f.type }, body: f });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "Upload failed");
      await load(); toast("Logo updated");
    } catch (err) { toast(err.message); }
    e.target.value = "";
  };
  $("#logo-remove").onclick = async () => { await api("DELETE", "/api/brand/logo"); await load(); toast("Using the default logo"); };
  $("#reset-brand").onclick = async () => {
    if (!confirm("Reset the wordmark, tagline, and colors to the defaults?")) return;
    await api("POST", "/api/settings", { reset_brand: true }); setDlg.close(); await load(); toast("Look reset");
  };
  $("#clear-key").onclick = async () => {
    if (!confirm("Remove the saved API key?")) return;
    await api("POST", "/api/settings", { clear_api_key: true }); setDlg.close(); await load(); toast("Key removed");
  };

  document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => b.closest("dialog").close()));

  // ----- brief -----
  $("#regen").onclick = async (e) => {
    const btn = e.currentTarget;
    const u = S.usage;
    if (S.settings.has_api_key && !confirm(`This uses one Claude call (${u.calls} of ${u.cap} used this month). Go ahead?`)) return;
    btn.disabled = true; btn.textContent = "Writing...";
    try { await api("POST", "/api/brief/regenerate"); await load(); toast("Brief updated"); }
    catch (err) { toast(err.message); }
    finally { btn.disabled = false; btn.textContent = "Refresh brief"; }
  };


  const niceTime = (hm) => { const [h, m] = (hm || "06:00").split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };

  // ----- first-run setup -----
  const ob = $("#onboard"), obf = $("#ob-form");
  const STEPS = 5;
  let step = 0, town = null;

  function showStep(n) {
    step = Math.max(0, Math.min(STEPS - 1, n));
    document.querySelectorAll(".ob-step").forEach((el) => (el.hidden = Number(el.dataset.step) !== step));
    document.querySelectorAll(".ob-dots i").forEach((d, i) => d.classList.toggle("on", i === step));
    $("#ob-back").style.visibility = step === 0 || step === STEPS - 1 ? "hidden" : "visible";
    $("#ob-skip").style.visibility = step === 0 || step === STEPS - 1 ? "hidden" : "visible";
    $("#ob-next").textContent = step === STEPS - 1 ? "Open Intranet HQ" : step === STEPS - 2 ? "Finish" : "Next";
    const first = document.querySelector(`.ob-step[data-step="${step}"] input, .ob-step[data-step="${step}"] textarea`);
    if (first) setTimeout(() => first.focus(), 50);
  }

  function openOnboarding() {
    const s = S.settings;
    obf.elements.owner_name.value = s.owner_name || "";
    obf.elements.company_name.value = s.company_name || "";
    obf.elements.town_q.value = s.location_name || "";
    obf.elements.brief_time.value = s.brief_time || "06:00";
    obf.elements.apps.value = ""; obf.elements.anthropic_api_key.value = ""; obf.elements.ical_url.value = "";
    $("#ob-apps-note").textContent = S.pipeline.length ? `You already have ${S.pipeline.length} on the board. Anything here gets added.` : "";
    town = null; $("#ob-towns").innerHTML = "";
    $("#ob-town-picked").textContent = s.location_name ? `Current: ${s.location_name}` : "";
    showStep(0); ob.showModal();
  }

  async function findTown() {
    const q = obf.elements.town_q.value.trim(); if (!q) return;
    $("#ob-towns").innerHTML = `<p class="muted small">Looking...</p>`;
    try {
      const r = await api("GET", "/api/geocode?q=" + encodeURIComponent(q));
      if (!r.results.length) {
        $("#ob-towns").innerHTML = `<p class="muted small">${esc(r.error ? "Lookup isn't reachable right now. You can skip and set it later in Settings." : "No matches. Try just the town name.")}</p>`;
        return;
      }
      $("#ob-towns").innerHTML = r.results.map((t, i) => `<button type="button" class="ob-town" data-i="${i}">${esc(t.label)}</button>`).join("");
      $("#ob-towns").onclick = (e) => {
        const b = e.target.closest(".ob-town"); if (!b) return;
        town = r.results[Number(b.dataset.i)];
        document.querySelectorAll(".ob-town").forEach((x) => x.classList.toggle("on", x === b));
        $("#ob-town-picked").textContent = `Got it: ${town.label}`;
      };
    } catch (err) { $("#ob-towns").innerHTML = `<p class="muted small">${esc(err.message)}</p>`; }
  }
  $("#ob-find").onclick = findTown;
  obf.elements.town_q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); findTown(); } });

  async function saveStep() {
    const f = obf.elements;
    if (step === 0) await api("POST", "/api/settings", { owner_name: f.owner_name.value, company_name: f.company_name.value });
    if (step === 1 && town) await api("POST", "/api/settings", { location_name: town.label, latitude: town.latitude, longitude: town.longitude });
    if (step === 2 && f.apps.value.trim()) {
      const r = await api("POST", "/api/pipeline/import", { text: f.apps.value });
      $("#ob-apps-note").textContent = `Added ${r.added}.`;
    }
    if (step === 3) {
      await api("POST", "/api/settings", { anthropic_api_key: f.anthropic_api_key.value, ical_url: f.ical_url.value, brief_time: f.brief_time.value, onboarded: true });
      await load();
      const bits = [];
      bits.push(S.pipeline.length ? `${S.pipeline.length} apps on the board` : "an empty board, ready for your first app");
      bits.push(S.settings.location_name ? `weather for ${S.settings.location_name}` : "no weather yet");
      bits.push(S.settings.has_api_key ? "Claude writing your brief" : "a plain brief (add a key anytime)");
      bits.push(S.settings.has_ical_url ? "your calendar connected" : "no calendar yet");
      $("#ob-summary").textContent = `You've got ${bits.join(", ")}. Your first brief arrives tomorrow at ${niceTime(S.settings.brief_time)}, or tap Refresh brief now.`;
    }
  }

  obf.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (step === STEPS - 1) { ob.close(); await load(); return; }
    const btn = $("#ob-next"); btn.disabled = true;
    try { await saveStep(); showStep(step + 1); }
    catch (err) { toast(err.message); }
    finally { btn.disabled = false; }
  });
  $("#ob-back").onclick = () => showStep(step - 1);
  $("#ob-skip").onclick = async () => {
    if (step === 3) { await api("POST", "/api/settings", { onboarded: true }); await load(); $("#ob-summary").textContent = "You can finish connecting things anytime in Settings."; }
    showStep(step + 1);
  };
  ob.addEventListener("cancel", async () => { await api("POST", "/api/settings", { onboarded: true }).catch(() => {}); });
  $("#rerun-setup").onclick = () => { setDlg.close(); openOnboarding(); };

  load().then(() => { if (!S.settings.onboarded) openOnboarding(); }).catch((e) => { $("#brief-body").innerHTML = `<p class="muted">Couldn't load: ${esc(e.message)}</p>`; });
})();
