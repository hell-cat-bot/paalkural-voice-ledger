/* PaalKural console. Vanilla JS, no build step. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const state = {
    source: "clip",
    clips: {},
    members: [],
    turn: null,
    busy: false,
    bench: null,
    mic: { recorder: null, stream: null, chunks: [], timer: null, started: 0, stopTimer: null },
    audio: null,
  };

  const SCENES = {
    society_hall: "Society hall",
    fan_cans: "Fan + cans",
    generator: "Generator",
  };
  const DEMO_NOTES = {
    d01: "A straight pour: member, litres, fat, shift.",
    d02: "The speaker corrects the litres mid-sentence.",
    d03: "Fat is never said. The gate has to ask again.",
    d04: "An evening pour with a single-digit fat.",
  };
  const SLOT_DEFS = [
    { key: "member_id", label: "Member", unit: "", fmt: (v) => String(v) },
    { key: "litres", label: "Litres", unit: "L", fmt: (v) => Number(v).toFixed(1) },
    { key: "fat", label: "Fat", unit: "%", fmt: (v) => Number(v).toFixed(1) },
    { key: "shift", label: "Shift", unit: "", fmt: (v) => (v === "morning" ? "Morning" : "Evening") },
  ];

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let body = null;
    try {
      body = await res.json();
    } catch {
      body = {};
    }
    if (!res.ok) {
      const err = new Error(body.message || body.error || `Request failed (${res.status})`);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const inr = (n) => "₹" + Number(n || 0).toFixed(2);
  const pct = (n) => Number(n || 0).toFixed(1) + "%";
  const nowTime = () => new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

  /* ── stage & waveform ─────────────────────────────────────── */
  const wave = $("#wave");
  const ctx2d = wave.getContext("2d");
  let lastWave = null;

  function fitCanvas() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = wave.clientWidth || 600;
    const h = wave.clientHeight || 238;
    wave.width = Math.round(w * dpr);
    wave.height = Math.round(h * dpr);
    ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawWave(lastWave?.raw, lastWave?.mit);
  }

  function drawWave(raw, mit) {
    const w = wave.clientWidth || 600;
    const h = wave.clientHeight || 238;
    const mid = h / 2;
    ctx2d.clearRect(0, 0, w, h);
    ctx2d.fillStyle = "#12211f";
    ctx2d.fillRect(0, 0, w, h);

    ctx2d.strokeStyle = "rgba(251,248,241,0.07)";
    ctx2d.lineWidth = 1;
    for (let i = 1; i < 6; i++) {
      const x = (w / 6) * i;
      ctx2d.beginPath();
      ctx2d.moveTo(x, 0);
      ctx2d.lineTo(x, h);
      ctx2d.stroke();
    }
    for (const ratio of [0.25, 0.5, 0.75]) {
      ctx2d.beginPath();
      ctx2d.moveTo(0, h * ratio);
      ctx2d.lineTo(w, h * ratio);
      ctx2d.stroke();
    }

    if (!raw || !raw.length) {
      ctx2d.fillStyle = "rgba(251,248,241,0.35)";
      ctx2d.font = '10px "IBM Plex Mono", monospace';
      ctx2d.fillText("NO LINE YET — PLAY A CLIP, START THE MIC, OR TYPE", 14, h - 16);
      ctx2d.strokeStyle = "rgba(217,154,27,0.65)";
      ctx2d.beginPath();
      ctx2d.moveTo(0, mid);
      ctx2d.lineTo(w, mid);
      ctx2d.stroke();
      return;
    }

    const drawSeries = (series, stroke, fill, width) => {
      const n = series.length;
      const step = w / Math.max(1, n - 1);
      ctx2d.beginPath();
      ctx2d.moveTo(0, mid);
      series.forEach((v, i) => ctx2d.lineTo(i * step, mid - Math.min(1, v) * (mid - 12)));
      ctx2d.lineTo(w, mid);
      ctx2d.closePath();
      ctx2d.fillStyle = fill;
      ctx2d.fill();
      ctx2d.beginPath();
      series.forEach((v, i) => {
        const x = i * step;
        const y = mid - Math.min(1, v) * (mid - 12);
        if (i === 0) ctx2d.moveTo(x, y);
        else ctx2d.lineTo(x, y);
      });
      ctx2d.strokeStyle = stroke;
      ctx2d.lineWidth = width;
      ctx2d.lineJoin = "round";
      ctx2d.stroke();
    };

    if (raw) drawSeries(raw, "#7e8b86", "rgba(126,139,134,0.16)", 1.1);
    if (mit) drawSeries(mit, "#d99a1b", "rgba(217,154,27,0.15)", 1.6);
  }

  function setWave(raw, mit) {
    lastWave = { raw, mit };
    drawWave(raw, mit);
  }

  window.addEventListener("resize", fitCanvas);

  /* ── stage helpers ───────────────────────────────────────── */
  function setBadge(text, kind = "") {
    const el = $("#stage-badge");
    el.textContent = text;
    el.className = "stage-badge" + (kind ? ` ${kind}` : "");
  }
  function setCondition(text) {
    $("#stage-condition").textContent = text;
  }
  function scan(on) {
    $("#scan").classList.toggle("on", on);
  }
  function setBusy(on, what = "reading") {
    state.busy = on;
    scan(on);
    if (on) setBadge(what + "…", "is-busy");
    $$("#panel-line button").forEach((b) => {
      if (!b.closest(".source-tabs") && b.id !== "reask-btn" && b.id !== "next-pour") b.disabled = on;
    });
    if (!on) {
      $$("#panel-line button").forEach((b) => (b.disabled = false));
      updateAudioButtons();
    }
  }
  function showError(message) {
    const box = $("#sheet-error");
    box.textContent = message;
    box.hidden = !message;
  }

  function describeLine(line) {
    if (!line) return "line";
    if (line.input === "typed") return "Typed entry · ASR bypassed";
    if (line.input === "microphone") return "Microphone · this device";
    if (line.input === "fixture") {
      if (line.clean_studio) return `${SCENES[line.scene] || "clip"} · clean studio · synthetic clip`;
      return `${SCENES[line.scene] || line.scene} · ${line.snr_db} dB · synthetic clip`;
    }
    return "line";
  }

  /* ── turn flow ───────────────────────────────────────────── */
  async function runTurn(payload, what = "Reading the line") {
    if (state.busy) return;
    showError("");
    setBusy(true, what);
    setBadge(what + "…", "is-busy");
    if (payload.fixture_id) {
      const clip = state.clips[payload.fixture_id];
      const scene = payload.scene ? SCENES[payload.scene] : SCENES[clip?.scene] || "Society hall";
      setCondition(payload.snr === null ? `${scene} · clean studio · reading` : `${scene} · ${payload.snr} dB · reading`);
    } else if (payload.text) {
      setCondition("Typed entry · reading the slots");
    } else {
      setCondition("Microphone · reading this device");
    }
    try {
      const turn = await api("/api/turn", { method: "POST", body: JSON.stringify(payload) });
      state.turn = turn;
      setCondition(describeLine(turn.line));
      renderTurn(turn);
      const split = turn.agreement === "disagree";
      setBadge(
        !turn.validation.ok ? "needs a detail" : split ? "listens disagree" : "ready to confirm",
        !turn.validation.ok || split ? "is-live" : "is-done"
      );
    } catch (err) {
      setBadge("line error", "is-live");
      showError(err.message || "The line could not be read.");
      const sheet = $("#sheet-title");
      sheet.textContent = "Line error";
    } finally {
      setBusy(false);
    }
  }

  function confidenceLevel(slot) {
    if (!slot) return 0;
    const c = slot.confidence ?? 0;
    if (slot.method === "member+number") return 4;
    if (c >= 0.95) return 4;
    if (c >= 0.9) return 3;
    if (c >= 0.8) return 2;
    return 1;
  }

  function renderTurn(t) {
    $("#sheet-empty").hidden = true;
    $("#receipt").hidden = true;
    $("#sheet-body").hidden = false;
    const stamp = !t.validation.ok
      ? "RE-ASK"
      : t.agreement === "disagree"
      ? "CHECK"
      : t.agreement === "raw_only" || t.agreement === "mit_only"
      ? "ONE PATH"
      : t.agreement === "typed"
      ? "TYPED"
      : "AGREED";
    const stampColor = stamp === "RE-ASK" ? "var(--red)" : stamp === "AGREED" ? "var(--indigo)" : "var(--turmeric)";
    $("#sheet-stamp").textContent = stamp;
    $("#sheet-stamp").style.color = stampColor;
    $("#sheet-stamp").style.borderColor = stampColor;

    const mid = t.slots.member_id?.value;
    const litres = t.slots.litres?.value;
    $("#sheet-title").textContent = mid ? `Member ${mid}${litres ? ` · ${Number(litres).toFixed(1)} L` : ""}` : "Pour sheet";

    $("#transcript").textContent = t.transcript || "—";
    const asr = t.asr || {};
    const lat = t.latency || {};
    const asrPaths = lat.asr_paths_ms || 0;
    $("#transcript-meta").textContent =
      `${asr.provider || "ASR"} · ${((asrPaths || lat.asr_ms) / 1000).toFixed(1)} s ASR${asrPaths ? " ×2 listens" : ""} · ${lat.total_ms} ms end to end`;

    const slotsBox = $("#slots");
    slotsBox.innerHTML = "";
    const member = t.member;
    for (const def of SLOT_DEFS) {
      const slot = t.slots[def.key];
      const row = document.createElement("div");
      row.className = "slot" + (slot ? "" : " slot-missing");
      const dt = document.createElement("dt");
      dt.textContent = def.label;
      const dd = document.createElement("dd");
      if (!slot) {
        dd.innerHTML = `<span class="slot-value">not heard</span>`;
      } else {
        const val = document.createElement("span");
        val.className = "slot-value";
        val.textContent = def.fmt(slot.value);
        dd.appendChild(val);
        if (def.unit) {
          const unit = document.createElement("span");
          unit.className = "slot-unit";
          unit.textContent = def.unit;
          dd.appendChild(unit);
        }
        if (def.key === "member_id" && member) {
          const nm = document.createElement("span");
          nm.className = "slot-name";
          nm.textContent = member.name;
          dd.appendChild(nm);
        }
        if (def.key === "litres" && member?.recent?.length) {
          const nm = document.createElement("span");
          nm.className = "slot-name";
          nm.textContent = "last " + member.recent[member.recent.length - 1].litres + " L";
          dd.appendChild(nm);
        }
      }
      const conf = document.createElement("div");
      conf.className = "slot-conf";
      const bars = document.createElement("div");
      bars.className = "conf-bars";
      const level = confidenceLevel(slot);
      for (let i = 0; i < 4; i++) {
        const bar = document.createElement("i");
        if (slot && i < level) bar.className = level <= 2 ? "on warn" : "on";
        bars.appendChild(bar);
      }
      bars.title = slot ? `${slot.method} · ${Math.round((slot.confidence || 0) * 100)}%` : "missing";
      const word = document.createElement("span");
      word.className = "conf-word";
      word.textContent = slot ? (level >= 4 ? "heard" : level >= 3 ? "close" : "check") : "ask";
      conf.append(bars, word);
      row.append(dt, dd, conf);
      slotsBox.appendChild(row);
    }

    const secondBox = $("#second-listen");
    const second = t.second;
    if (!second) {
      secondBox.hidden = true;
    } else {
      secondBox.hidden = false;
      const statusMap = {
        agree: ["both listens agree", "is-agree"],
        disagree: ["listens disagree", "is-disagree"],
        raw_only: ["raw passed · conditioned failed", "is-single"],
        mit_only: ["conditioned passed · raw failed", "is-single"],
        none: ["neither listen passed", "is-disagree"],
      };
      const [label, cls] = statusMap[t.agreement] || ["second listen", ""];
      const chip = $("#second-status");
      chip.textContent = label;
      chip.className = "second-status " + cls;
      const copyMap = {
        agree: "The raw line and the conditioned line parse to the same four values.",
        disagree: "The two listens heard different values. Check the sheet before confirming, or re-ask.",
        raw_only: "Only the raw listen passed every roster and range gate. The other listen is not trusted for this pour.",
        mit_only: "Only the conditioned listen passed every roster and range gate. The raw listen is not trusted for this pour.",
        none: "Neither listen produced a valid sheet. Re-ask the member.",
      };
      $("#second-copy").textContent = copyMap[t.agreement] || "";
      const differing = SLOT_DEFS.map((d) => d.key).filter((k) => (second.differing || []).includes(k));
      const primaryPath = second.path === "processed" ? "raw" : "conditioned";
      if (differing.length) {
        $("#second-slots").innerHTML = differing
          .map((key) => {
            const def = SLOT_DEFS.find((d) => d.key === key);
            const chosen = t.slots[key]?.value;
            const other = second.slots[key];
            const fmt = (v) => (v === undefined || v === null ? "not heard" : def.fmt(v));
            return `<div class="second-row"><span class="second-key">${esc(def.label)}</span>
              <span class="second-val">${esc(primaryPath)} · ${esc(fmt(chosen))}</span>
              <span class="second-val">${esc(second.path)} · ${esc(fmt(other))}</span></div>`;
          })
          .join("");
      } else if (!second.ok) {
        const missing = (second.missing || []).join(", ") || (second.flags || []).join(", ") || "no valid sheet";
        $("#second-slots").innerHTML = `<div class="second-row"><span class="second-key">Other listen</span><span class="second-val">${esc(
          second.path
        )} · ${esc(missing)}</span></div>`;
      } else {
        $("#second-slots").innerHTML = "";
      }
    }

    $("#readback-ta").textContent = t.readback?.ta || "—";
    $("#readback-en").textContent = t.readback?.en || "—";
    const rbUrl = t.readback?.audio?.url;
    $("#play-readback").disabled = !rbUrl;
    $("#play-readback").dataset.url = rbUrl || "";

    const flags = $("#flags");
    if (t.validation.flags?.length) {
      flags.hidden = false;
      flags.innerHTML = t.validation.flags
        .map(
          (f) =>
            `<div class="flag"><span class="flag-code">${esc(f.code)}</span><span>${esc(f.message)}</span></div>`
        )
        .join("");
    } else {
      flags.hidden = true;
      flags.innerHTML = "";
    }

    const strip = $("#member-strip");
    if (member) {
      strip.hidden = false;
      $("#member-id").textContent = `${member.id} · ${member.name}`;
      $("#member-history").innerHTML = member.recent.length
        ? member.recent
            .slice()
            .reverse()
            .map(
              (e) =>
                `<div><b>${esc(e.id)}</b> · ${esc(e.shift)} · ${Number(e.litres).toFixed(1)} L · ${Number(
                  e.fat
                ).toFixed(1)}% · ${inr(e.amount)}</div>`
            )
            .join("")
        : "First pour on record for this member.";
    } else {
      strip.hidden = true;
    }

    const preview = $("#preview");
    if (t.preview) {
      preview.hidden = false;
      $("#preview-rate").textContent = inr(t.preview.rate) + "/L";
      $("#preview-amount").textContent = inr(t.preview.amount);
    } else {
      preview.hidden = true;
    }

    const ok = t.validation.ok;
    const split = t.agreement === "disagree";
    const confirm = $("#confirm-btn");
    confirm.textContent = ok ? (split ? "Resolve & log" : "Confirm & log") : "Fix & log";
    confirm.dataset.mode = ok ? (split ? "resolve" : "confirm") : "fix";
    $("#sheet-note").textContent = ok
      ? split
        ? "The listens disagree. Resolve the sheet before anything is written."
        : "Confirming writes one entry with an audit hash."
      : "The machine is not allowed to log this. Correct the sheet, or ask again.";

    setWave(t.waveform.raw, t.waveform.mitigated);
    const rawUrl = t.audio?.raw_url;
    const mitUrl = t.audio?.mitigated_url;
    $("#play-raw").dataset.url = rawUrl || "";
    $("#play-mit").dataset.url = mitUrl || "";
    updateAudioButtons();
    $("#play-raw").textContent = t.line?.input === "microphone" ? "Play mic" : "Play raw";
    $("#play-mit").textContent = "Play processed";

    const xray = $("#xray-copy");
    if (t.line?.input === "typed") {
      xray.textContent = "Typed input bypasses the line: no audio, no ASR, same slot compiler and same confirmation gate.";
    } else if (t.line?.fixture) {
      xray.textContent = `Frozen clip ${t.line.fixture}. Raw line against the bandlimited, gated signal; both are decoded and compared. VAD is off: it clipped trailing slots in our tests.`;
    } else {
      xray.textContent = "This device's raw capture against the conditioned signal; both are decoded and compared. VAD is off: it clipped trailing slots in our tests.";
    }

    const l = t.latency || {};
    const listens = l.asr_paths_ms ? 2 : 1;
    $("#latency-strip").innerHTML =
      `<span>ASR ×${listens} ${((l.asr_paths_ms || l.asr_ms) / 1000).toFixed(1)} s</span>` +
      `<span>DSP ${l.dsp_ms || 0} ms</span>` +
      `<span>readback ${l.tts_ms || 0} ms</span>` +
      `<span>total ${(l.total_ms / 1000).toFixed(1)} s</span>`;

    $("#wave-time").textContent = t.line?.fixture ? t.line.fixture : t.line?.input === "typed" ? "typed" : "mic";
    if (window.innerWidth < 1080) $("#sheet").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function updateAudioButtons() {
    for (const id of ["play-raw", "play-mit", "play-readback"]) {
      const b = $("#" + id);
      const url = b.dataset.url;
      b.disabled = state.busy || !url;
    }
  }

  async function confirmTurn(corrections = {}) {
    if (!state.turn) return;
    showError("");
    const btn = $("#confirm-btn");
    btn.disabled = true;
    btn.textContent = "Writing…";
    try {
      const out = await api("/api/confirm", {
        method: "POST",
        body: JSON.stringify({ turn_id: state.turn.turn_id, corrections }),
      });
      renderReceipt(out.entry, out.receipt_url, out.corrections_applied);
      loadLedger();
    } catch (err) {
      if (err.status === 409) {
        showError(err.message);
        if (err.body?.error === "incomplete" || err.body?.error === "member_unknown" || err.body?.error?.includes("range")) {
          openEdit();
        }
      } else {
        showError(err.message || "Could not write the entry.");
      }
      btn.disabled = false;
      btn.textContent = "Confirm & log";
    }
  }

  function renderReceipt(entry, url, corrected) {
    $("#sheet-body").hidden = true;
    $("#receipt").hidden = false;
    $("#sheet-stamp").textContent = "LOGGED";
    $("#sheet-stamp").style.color = "var(--red)";
    $("#sheet-stamp").style.borderColor = "var(--red)";
    $("#sheet-title").textContent = "Pour logged";
    $("#receipt-title").textContent = corrected ? "Logged with a correction" : "Logged as heard";
    $("#receipt-lines").innerHTML = `
      <div class="receipt-row"><span>Receipt</span><strong>${esc(entry.id)}</strong></div>
      <div class="receipt-row"><span>Member</span><span>${entry.member_id} · ${esc(entry.member_name)}</span></div>
      <div class="receipt-row"><span>Shift</span><span>${esc(entry.shift)}</span></div>
      <div class="receipt-row"><span>Pour</span><span>${Number(entry.litres).toFixed(2)} L · ${Number(entry.fat).toFixed(1)}% fat</span></div>
      <div class="receipt-row total"><span>Amount</span><span>${inr(entry.amount)}</span></div>
      <div class="receipt-row"><span>Audit hash</span><span>${esc(entry.hash)}</span></div>`;
    $("#receipt-link").href = url;
  }

  /* ── edit dialog ─────────────────────────────────────────── */
  function openEdit() {
    if (!state.turn) return;
    const t = state.turn;
    const sel = $("#edit-member");
    sel.innerHTML = state.members
      .map((m) => `<option value="${m.id}">${m.id} · ${esc(m.name)}</option>`)
      .join("");
    if (t.slots.member_id) sel.value = String(t.slots.member_id.value);
    $("#edit-litres").value = t.slots.litres?.value ?? "";
    $("#edit-fat").value = t.slots.fat?.value ?? "";
    $("#edit-shift").value = t.slots.shift?.value ?? "morning";
    const note = $("#edit-dialog .edit-note");
    if (t.agreement === "disagree") {
      const labels = { member_id: "member", litres: "litres", fat: "fat", shift: "shift" };
      const diff = (t.second?.differing || []).map((k) => labels[k] || k).join(", ");
      note.textContent = `The two listens disagree on ${diff}. Keep the raw value, or correct it before logging.`;
    } else {
      note.textContent = "Corrections are stored with the entry and change the audit hash.";
    }
    const dialog = $("#edit-dialog");
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeEdit() {
    const dialog = $("#edit-dialog");
    if (dialog.close) dialog.close();
    else dialog.removeAttribute("open");
  }

  function saveEdit() {
    if (!state.turn) return;
    const original = state.turn.slots;
    const values = {
      member_id: Number($("#edit-member").value),
      litres: Number($("#edit-litres").value),
      fat: Number($("#edit-fat").value),
      shift: $("#edit-shift").value,
    };
    const corrections = {};
    for (const key of Object.keys(values)) {
      if (!original[key] || original[key].value !== values[key]) corrections[key] = values[key];
    }
    closeEdit();
    confirmTurn(corrections);
  }

  /* ── source controls ─────────────────────────────────────── */
  function switchSource(src) {
    state.source = src;
    $$(".src").forEach((b) => {
      const on = b.dataset.src === src;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-selected", String(on));
    });
    $("#src-clip").hidden = src !== "clip";
    $("#src-mic").hidden = src !== "mic";
    $("#src-typed").hidden = src !== "typed";
    if (src !== "mic") stopMic(false);
  }

  function updateClipScenario() {
    const id = $("#clip-select").value;
    const clip = state.clips[id];
    $("#clip-scenario").textContent =
      DEMO_NOTES[id] || (clip ? `Frozen benchmark clip · ${SCENES[clip.scene] || "society hall"} · ground truth in Evidence.` : "");
    const snr = $("#snr-select").value;
    const scene = SCENES[$("#scene-select").value] || "Society hall";
    setCondition(snr === "clean" ? `${scene} · clean studio · ready` : `${scene} · ${snr} dB · ready`);
  }

  function onClipChange() {
    const clip = state.clips[$("#clip-select").value];
    if (clip?.scene) $("#scene-select").value = clip.scene;
    updateClipScenario();
  }

  function payloadForClip() {
    const snr = $("#snr-select").value;
    return {
      fixture_id: $("#clip-select").value,
      scene: $("#scene-select").value,
      snr: snr === "clean" ? null : Number(snr),
    };
  }

  /* ── microphone ──────────────────────────────────────────── */
  function fmtTimer(ms) {
    return (ms / 1000).toFixed(1) + " s";
  }

  async function startMic() {
    if (state.mic.recorder) {
      stopMic(true);
      return;
    }
    showError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true },
      });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      state.mic = { recorder: rec, stream, chunks: [], timer: null, started: performance.now(), stopTimer: null };
      rec.ondataavailable = (e) => {
        if (e.data.size) state.mic.chunks.push(e.data);
      };
      rec.onstop = () => finishMic();
      rec.start();
      $("#mic-btn").setAttribute("aria-pressed", "true");
      $("#mic-label").textContent = "Stop & read";
      setBadge("listening…", "is-live");
      setCondition("Microphone · listening");
      state.mic.timer = setInterval(() => {
        $("#mic-timer").textContent = fmtTimer(performance.now() - state.mic.started);
      }, 100);
      state.mic.stopTimer = setTimeout(() => stopMic(true), 12000);
    } catch (err) {
      showError("Microphone unavailable: " + (err.message || "permission denied") + " Use a line clip or type instead.");
    }
  }

  function stopMic(transcribe) {
    const mic = state.mic;
    if (!mic.recorder) return;
    clearInterval(mic.timer);
    clearTimeout(mic.stopTimer);
    mic.transcribe = transcribe;
    try {
      mic.recorder.stop();
    } catch {
      mic.recorder = null;
    }
    mic.stream?.getTracks().forEach((t) => t.stop());
    $("#mic-btn").setAttribute("aria-pressed", "false");
    $("#mic-label").textContent = "Start listening";
    if (!transcribe) {
      state.mic.recorder = null;
      $("#mic-timer").textContent = "0.0 s";
    }
  }

  async function finishMic() {
    const mic = state.mic;
    const elapsed = performance.now() - mic.started;
    const chunks = mic.chunks.slice();
    mic.recorder = null;
    $("#mic-timer").textContent = fmtTimer(elapsed);
    if (!mic.transcribe) return;
    if (elapsed < 700 || !chunks.length) {
      showError("That recording was too short. Hold the line for a full sentence.");
      return;
    }
    setBadge("decoding…", "is-busy");
    try {
      const blob = new Blob(chunks, { type: "audio/webm" });
      const b64 = await blobToWav16kBase64(blob);
      await runTurn({ audio_b64: b64 }, "Reading the line");
    } catch (err) {
      showError("Could not decode that recording: " + (err.message || "unknown audio error"));
      setBadge("line error", "is-live");
    }
  }

  async function blobToWav16kBase64(blob) {
    const array = await blob.arrayBuffer();
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const decoded = await audioCtx.decodeAudioData(array);
    await audioCtx.close();
    const src = decoded.getChannelData(0);
    const mono = new Float32Array(src.length);
    for (let c = 0; c < decoded.numberOfChannels; c++) {
      const data = decoded.getChannelData(c);
      for (let i = 0; i < data.length; i++) mono[i] += data[i] / decoded.numberOfChannels;
    }
    const target = new Float32Array(Math.max(1, Math.round((decoded.duration * 16000))));
    const ratio = decoded.sampleRate / 16000;
    for (let i = 0; i < target.length; i++) {
      const pos = i * ratio;
      const lo = Math.floor(pos);
      const hi = Math.min(mono.length - 1, lo + 1);
      const frac = pos - lo;
      target[i] = (mono[lo] || 0) * (1 - frac) + (mono[hi] || 0) * frac;
    }
    const buf = new ArrayBuffer(44 + target.length * 2);
    const view = new DataView(buf);
    const writeStr = (off, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i));
    };
    writeStr(0, "RIFF");
    view.setUint32(4, 36 + target.length * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, 16000, true);
    view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, target.length * 2, true);
    let off = 44;
    for (let i = 0; i < target.length; i++, off += 2) {
      const s = Math.max(-1, Math.min(1, target[i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    const bytes = new Uint8Array(buf);
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    return btoa(binary);
  }

  /* ── ledger ──────────────────────────────────────────────── */
  async function loadLedger() {
    try {
      const data = await api("/api/ledger");
      const entries = data.entries || [];
      $("#ledger-count").textContent = String(entries.length);
      const t = data.totals || {};
      const cell = (label, v) =>
        `<div class="daybook-cell"><span>${label}</span><strong>${Number(v?.litres || 0).toFixed(
          1
        )} L</strong><span>${v?.count || 0} pours · ${inr(v?.amount || 0)}</span></div>`;
      $("#daybook-totals").innerHTML = cell("Morning", t.morning) + cell("Evening", t.evening) + cell("Day", t.all);
      $("#ledger-body").innerHTML = entries
        .map((e) => {
          const time = e.created_at?.slice(11, 16) || "—";
          return `<tr>
            <td><a class="receipt-link" href="/api/receipt/${encodeURIComponent(e.id)}" target="_blank" rel="noopener">${esc(
            e.id
          )}</a></td>
            <td>${esc(time)}</td>
            <td>${e.member_id} · ${esc(e.member_name)}</td>
            <td><span class="shift-tag ${esc(e.shift)}">${esc(e.shift)}</span></td>
            <td class="num">${Number(e.litres).toFixed(2)}</td>
            <td class="num">${Number(e.fat).toFixed(1)}</td>
            <td class="num">${inr(e.rate)}</td>
            <td class="num amount">${inr(e.amount)}</td>
            <td><span class="source-tag">${esc(e.source)}${e.override ? " · corrected" : ""}</span></td>
          </tr>`;
        })
        .join("");
      $("#ledger-note").textContent = `${data.note} Synthetic receipt ${entries[0]?.id || ""} is safe to publish.`;
    } catch (err) {
      $("#ledger-body").innerHTML = `<tr><td colspan="9">Ledger unavailable: ${esc(err.message)}</td></tr>`;
    }
  }

  /* ── evidence ────────────────────────────────────────────── */
  function buildChart(summary) {
    const svg = $("#chart");
    const cells = summary.cells || [];
    const conds = [...new Set(cells.map((c) => c.condition))];
    const W = 560, H = 260, left = 46, bottom = 34, top = 12, right = 8;
    const plotW = W - left - right;
    const plotH = H - top - bottom;
    const groupW = plotW / Math.max(1, conds.length);
    const barW = Math.min(30, groupW * 0.26);
    let out = "";
    for (let i = 0; i <= 4; i++) {
      const y = top + plotH - (plotH * i) / 4;
      out += `<line x1="${left}" y1="${y}" x2="${W - right}" y2="${y}" stroke="#e9e3d6" stroke-width="1"/>`;
      out += `<text x="${left - 8}" y="${y + 3}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="8" fill="#7e8b86">${i * 25}</text>`;
    }
    conds.forEach((cond, gi) => {
      const cx = left + groupW * gi + groupW / 2;
      out += `<text x="${cx}" y="${H - 12}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9" fill="#12211f">${esc(
        cond
      )}</text>`;
      for (const [bi, arm] of ["raw", "mitigated"].entries()) {
        const cell = cells.find((c) => c.condition === cond && c.arm === arm);
        if (!cell) continue;
        const h = (plotH * cell.exact_pct) / 100;
        const x = cx + (bi === 0 ? -barW - 3 : 3);
        const y = top + plotH - h;
        const fill = arm === "raw" ? "#7e8b86" : "#d99a1b";
        out += `<rect x="${x}" y="${y}" width="${barW}" height="${Math.max(1, h)}" fill="${fill}"/>`;
        out += `<text x="${x + barW / 2}" y="${y - 4}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="8" fill="#12211f">${cell.exact_pct.toFixed(
          0
        )}</text>`;
        const [lo, hi] = cell.exact_ci95 || [0, 0];
        const yLo = top + plotH - (plotH * lo) / 100;
        const yHi = top + plotH - (plotH * hi) / 100;
        const mx = x + barW / 2;
        out += `<line x1="${mx}" y1="${yHi}" x2="${mx}" y2="${yLo}" stroke="#12211f" stroke-width="0.8" opacity="0.55"/>`;
        out += `<line x1="${mx - 3}" y1="${yHi}" x2="${mx + 3}" y2="${yHi}" stroke="#12211f" stroke-width="0.8" opacity="0.55"/>`;
        out += `<line x1="${mx - 3}" y1="${yLo}" x2="${mx + 3}" y2="${yLo}" stroke="#12211f" stroke-width="0.8" opacity="0.55"/>`;
      }
    });
    out += `<line x1="${left}" y1="${top + plotH}" x2="${W - right}" y2="${top + plotH}" stroke="#12211f" stroke-width="1.2"/>`;
    out += `<text x="${left}" y="${top - 1}" font-family="IBM Plex Mono, monospace" font-size="8" fill="#7e8b86">% of clips, all four slots exact</text>`;
    svg.innerHTML = out;
  }

  function renderEvidence(data) {
    if (!data || data.status !== "complete") {
      $("#evidence-empty").hidden = false;
      $("#evidence-run").hidden = true;
      return;
    }
    state.bench = data;
    $("#evidence-empty").hidden = true;
    $("#evidence-run").hidden = false;
    $("#claim").textContent = data.claim;

    const s = data.summary;
    buildChart(s);
    const note = $("#chart-note");
    const base = s.cells.find((c) => c.condition === "clean" && c.arm === "mitigated");
    note.textContent = base
      ? `n=${data.n_per_cell} clips per cell · error bars are Wilson 95% CIs · ${data.cells} scored runs · ${data.elapsed_s}s`
      : "";

    $("#cells").innerHTML = [...new Set(s.cells.map((c) => c.condition))]
      .map((cond) => {
        const raw = s.cells.find((c) => c.condition === cond && c.arm === "raw");
        const mit = s.cells.find((c) => c.condition === cond && c.arm === "mitigated");
        const delta = Number(mit.exact_pct) - Number(raw.exact_pct);
        const cls = delta > 0 ? "up" : delta < 0 ? "down" : "";
        return `<div class="cell-row"><span class="cell-cond">${esc(cond)}</span>
          <span class="cell-raw">${raw.exact_pct.toFixed(0)}%</span>
          <span class="cell-arrow">→</span>
          <span class="cell-mit">${mit.exact_pct.toFixed(0)}%</span>
          <span class="cell-delta ${cls}">${delta > 0 ? "+" : ""}${delta.toFixed(0)} pp</span></div>`;
      })
      .join("");

    const policy = data.policy;
    if (policy?.cells?.length) {
      $("#policy-card").hidden = false;
      $("#policy-copy").textContent = policy.definition + " Scored from the same runs below; no third decode.";
      $("#policy-rows").innerHTML = policy.cells
        .map((p) => {
          const silent = Number(p.plausible_wrong || 0);
          return `<div class="policy-row">
            <span class="policy-cond">${esc(p.condition)}</span>
            <span class="policy-main"><b>${p.exact}/${p.n}</b> correct pre-fill</span>
            <span class="policy-silent ${silent ? "bad" : "ok"}">${silent} silent</span>
            <span class="policy-ask">${p.reask} to readback / re-ask</span>
          </div>`;
        })
        .join("");
    } else {
      $("#policy-card").hidden = true;
    }

    $("#evidence-body").innerHTML = s.cells
      .map(
        (c) => `<tr class="${c.arm === "mitigated" ? "mit" : ""}">
        <td>${esc(c.condition)}</td>
        <td>${esc(c.arm)}</td>
        <td class="num">${c.exact}/${c.n} · ${pct(c.exact_pct)}</td>
        <td class="num">${c.exact_ci95[0]}–${c.exact_ci95[1]}%</td>
        <td class="num">${pct(c.wer_pct)}</td>
        <td class="num">${pct(c.validation_pct)}</td>
        <td class="num">${c.plausible_wrong}/${c.n} · ${pct(c.plausible_wrong_pct)}</td>
        <td class="num">${(c.asr_ms_p50 / 1000).toFixed(1)} s</td>
      </tr>`
      )
      .join("");

    $("#caveats").textContent = "Limits: " + (data.caveats || []).join(" ");
    const env = data.environment || {};
    $("#environment-line").textContent = `${env.asr?.model || "ASR"} · ${env.asr?.compute || ""} · chain: ${
      env.chain || "band+gate"
    } · ${env.machine?.platform || ""} · ${env.machine?.processor || ""}`;
  }

  function renderProviderCheck(data) {
    const card = $("#provider-card");
    if (!data || data.status !== "complete" || !data.policy?.cells?.length) {
      card.hidden = true;
      return;
    }
    const provider = data.provider || {};
    const label = provider.name || "Gnani Prisma v3.0";
    const checks = data.policy.cells.filter((c) => ["clean", "15 dB", "5 dB", "0 dB"].includes(c.condition));
    const localPolicy = state.bench?.policy?.cells || [];
    $("#provider-tag").textContent = label.replace(" · live API", "");
    $("#provider-copy").textContent =
      `${label} decoded the same 24 clips × 4 line conditions × 2 paths: ${data.cells} calls, ` +
      `${(data.errors || []).length} errors, ${data.elapsed_s}s. The gate is scored below; ` +
      `this is a separate book from the frozen local benchmark.`;
    $("#provider-rows").innerHTML = checks
      .map((c) => {
        const local = localPolicy.find((l) => l.condition === c.condition);
        const localText = local ? `local ${local.exact}/${local.n}` : "local —";
        const silent = Number(c.plausible_wrong || 0);
        return `<div class="provider-row">
          <span class="provider-cond">${esc(c.condition)}</span>
          <span class="provider-main"><b>${c.exact}/${c.n}</b> correct pre-fill</span>
          <span class="policy-silent ${silent ? "bad" : "ok"}">${silent} silent</span>
          <span class="provider-ask">${c.reask} to readback / re-ask</span>
          <span class="provider-local">${esc(localText)}</span>
        </div>`;
      })
      .join("");
    $("#provider-note").textContent =
      "Same authored scripts and seeded noise. Prisma returns Tanglish, so WER is not comparable to the Tamil reference. " +
      "This check does not replace the frozen benchmark; calls were metered and no key material is stored.";
    card.hidden = false;
  }

  async function loadEvidence() {
    try {
      const data = await api("/api/benchmark");
      renderEvidence(data);
    } catch (err) {
      $("#evidence-empty").hidden = false;
      $("#evidence-empty").innerHTML = `<p class="old-note">Evidence unavailable</p><p>${esc(err.message)}</p>`;
    }
    try {
      renderProviderCheck(await api("/api/benchmark-gnani"));
    } catch {
      $("#provider-card").hidden = true;
    }
  }

  async function runReplay() {
    const btn = $("#run-replay");
    const box = $("#replay-result");
    btn.disabled = true;
    btn.textContent = "Running…";
    box.hidden = false;
    $("#replay-text").textContent = "Reading the clip…";
    $("#replay-diff").innerHTML = "";
    $("#replay-meta").textContent = "";
    try {
      const snrVal = $("#replay-snr").value;
      const data = await api("/api/benchmark/replay", {
        method: "POST",
        body: JSON.stringify({
          clip_id: $("#replay-clip").value,
          snr: snrVal === "clean" ? null : Number(snrVal),
          arm: $("#replay-arm").value,
        }),
      });
      $("#replay-text").textContent = data.transcript || "—";
      $("#replay-meta").textContent = `${data.clip_text ? "Script: " + data.clip_text : ""}`;
      $("#replay-diff").innerHTML = SLOT_DEFS.map((def) => {
        const pred = data.slots[def.key];
        const gt = data.ground_truth[def.key];
        const ok = data.matches[def.key];
        return `<div class="diff-row ${ok ? "ok" : "bad"}">
          <span class="diff-key">${def.label}</span>
          <span class="diff-val">heard: ${pred === undefined ? "—" : def.fmt(pred)}</span>
          <span class="diff-val">script: ${gt === null || gt === undefined ? "—" : def.fmt(gt)}</span>
          <span class="diff-mark">${ok ? "match" : "miss"}</span>
        </div>`;
      }).join("");
      $("#replay-meta").textContent += ` · ${data.arm} · ${(data.wall_ms / 1000).toFixed(1)} s · WER ${pct(
        data.wer * 100
      )}`;
    } catch (err) {
      $("#replay-text").textContent = "Replay failed: " + err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "Run replay";
    }
  }

  /* ── audio ───────────────────────────────────────────────── */
  function play(url) {
    if (!url) return;
    try {
      if (state.audio) {
        state.audio.pause();
        state.audio.currentTime = 0;
      }
      state.audio = new Audio(url);
      state.audio.play().catch(() => {});
    } catch {
      /* ignore playback errors */
    }
  }

  function speak(text) {
    if (!text || !window.speechSynthesis) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ta-IN";
    u.rate = 0.9;
    speechSynthesis.speak(u);
  }

  /* ── boot ────────────────────────────────────────────────── */
  async function loadFixtures() {
    const data = await api("/api/fixtures");
    const clipSel = $("#clip-select");
    const replaySel = $("#replay-clip");
    const demo = data.demo || [];
    const bench = data.benchmark || [];
    demo.forEach((c) => {
      state.clips[c.id] = c;
      const label = `${c.id} — ${DEMO_NOTES[c.id] || "synthetic pour"}`;
      clipSel.insertAdjacentHTML("beforeend", `<option value="${c.id}">${esc(label)}</option>`);
    });
    const group = document.createElement("optgroup");
    group.label = "Frozen benchmark clips";
    bench.forEach((c) => {
      state.clips[c.id] = c;
      group.insertAdjacentHTML(
        "beforeend",
        `<option value="${c.id}">${c.id} — ${esc(SCENES[c.scene] || c.scene)}</option>`
      );
      replaySel.insertAdjacentHTML("beforeend", `<option value="${c.id}">${c.id} — ${esc(SCENES[c.scene] || c.scene)}</option>`);
    });
    clipSel.appendChild(group);
    clipSel.value = demo.find((c) => c.id === "d02") ? "d02" : demo[0]?.id || bench[0]?.id;
    onClipChange();
  }

  /* ── tabs ────────────────────────────────────────────────── */
  function activateTab(name, updateHash = true) {
    const tab = $("#tab-" + name);
    if (!tab) return;
    $$(".tab").forEach((t) => {
      t.classList.toggle("is-on", t === tab);
      t.setAttribute("aria-selected", String(t === tab));
    });
    for (const panel of ["line", "ledger", "evidence"]) {
      $("#panel-" + panel).hidden = name !== panel;
    }
    if (updateHash && location.hash !== "#" + name) {
      history.replaceState(null, "", "#" + name);
    }
    if (name === "ledger") loadLedger();
    if (name === "evidence") loadEvidence();
    if (name === "line") requestAnimationFrame(fitCanvas);
  }

  function tabFromHash() {
    const name = (location.hash || "").replace("#", "");
    return ["line", "ledger", "evidence"].includes(name) ? name : "line";
  }

  function wire() {
    $$(".tab").forEach((tab) => {
      tab.addEventListener("click", () => activateTab(tab.id.replace("tab-", "")));
    });

    $$(".src").forEach((b) => b.addEventListener("click", () => switchSource(b.dataset.src)));

    $("#run-clip").addEventListener("click", () => runTurn(payloadForClip(), "Reading the line"));
    $("#run-typed").addEventListener("click", () => {
      const text = $("#typed-text").value.trim();
      if (!text) {
        showError("Type what the member said, or use the sample.");
        return;
      }
      runTurn({ text }, "Compiling typed entry");
    });
    $("#fill-typed").addEventListener("click", () => {
      $("#typed-text").value = "நம்பர் 124. மூன்றரை லிட்டர். ஃபேட் நாலு பாயிண்ட் எட்டு. காலை.";
      $("#typed-text").focus();
    });
    $("#mic-btn").addEventListener("click", startMic);

    $("#clip-select").addEventListener("change", onClipChange);
    $("#scene-select").addEventListener("change", updateClipScenario);
    $("#snr-select").addEventListener("change", updateClipScenario);

    $("#confirm-btn").addEventListener("click", () => {
      const mode = $("#confirm-btn").dataset.mode;
      if (mode === "fix" || mode === "resolve") openEdit();
      else confirmTurn({});
    });
    $("#edit-btn").addEventListener("click", openEdit);
    $("#reask-btn").addEventListener("click", () => {
      if (state.turn?.reask?.audio?.url) play(state.turn.reask.audio.url);
      else speak(state.turn?.reask?.ta || "மீண்டும் சொல்லுங்கள்.");
      if (state.source === "typed") $("#typed-text").focus();
      else if (state.source === "mic") setBadge("ready for another take", "is-done");
      else setBadge("play the line again or re-ask", "is-done");
    });
    $("#next-pour").addEventListener("click", resetSheet);

    $("#play-readback").addEventListener("click", (e) => {
      const url = e.currentTarget.dataset.url;
      if (url) play(url);
      else speak($("#readback-ta").textContent);
    });
    $("#play-raw").addEventListener("click", (e) => play(e.currentTarget.dataset.url));
    $("#play-mit").addEventListener("click", (e) => play(e.currentTarget.dataset.url));

    $("#edit-cancel").addEventListener("click", closeEdit);
    $("#edit-save").addEventListener("click", saveEdit);
    $("#edit-dialog").addEventListener("close", () => {});

    $("#run-replay").addEventListener("click", runReplay);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("#edit-dialog").open) closeEdit();
    });
    window.addEventListener("hashchange", () => activateTab(tabFromHash(), false));
  }

  function resetSheet() {
    state.turn = null;
    $("#receipt").hidden = true;
    $("#sheet-body").hidden = true;
    $("#sheet-empty").hidden = false;
    $("#sheet-title").textContent = "No pour on the line";
    $("#sheet-stamp").textContent = "OPEN";
    $("#sheet-stamp").style.color = "var(--red)";
    $("#sheet-stamp").style.borderColor = "var(--red)";
    $("#sheet-error").hidden = true;
    setBadge("idle");
    setWave(null, null);
    $("#wave-time").textContent = "";
    $("#play-raw").dataset.url = "";
    $("#play-mit").dataset.url = "";
    updateAudioButtons();
    updateClipScenario();
  }

  async function health() {
    try {
      const data = await api("/api/health");
      $("#health-dot").className = "status-dot ok";
      $("#health-text").textContent = data.provider?.stt || "engine ready";
      $("#provider-chip").textContent = data.provider?.gnani_live
        ? "Gnani Prisma · live"
        : data.provider?.gnani_key_present
        ? "key loaded · local"
        : "local demo";
      const integ = $("#integrity-provider");
      if (integ) {
        integ.innerHTML = data.provider?.gnani_live
          ? "<strong>Live Gnani Prisma and Timbre.</strong> Enabled with a participant-supplied key. The frozen 192-run benchmark and its claim remain local faster-whisper runs; the live provider check is separate."
          : data.provider?.gnani_key_present
          ? "<strong>Local inference for this run.</strong> A key is loaded, but DEMO_MODE=1 keeps this console on faster-whisper and edge-tts. The adapters were validated separately with the key."
          : "<strong>Local inference.</strong> No Gnani key is loaded; this console uses faster-whisper and edge-tts. The frozen benchmark is a local run.";
      }
    } catch {
      $("#health-dot").className = "status-dot bad";
      $("#health-text").textContent = "engine offline — start server/app.py";
    }
  }

  async function boot() {
    fitCanvas();
    wire();
    health();
    try {
      const data = await api("/api/members");
      state.members = data.members || [];
    } catch {
      state.members = [];
    }
    try {
      await loadFixtures();
    } catch (err) {
      showError("Could not load the synthetic clips: " + err.message);
    }
    loadLedger();
    activateTab(tabFromHash(), false);
  }

  boot();
})();
