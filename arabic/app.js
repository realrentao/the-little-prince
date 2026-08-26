/* ===== الأمير الصغير · 阿中双语朗读阅读器 ===== */
(function () {
  "use strict";

  const BOOK = window.__BOOK__;
  const LEX = window.__LEX__ || {};
  const ILLUST = window.__ILLUST__ || [];
  if (!BOOK) {
    document.getElementById("content").innerHTML =
      '<p style="color:#c00">数据未加载：请确认 data/book.js 存在。</p>';
    return;
  }

  // Per-chapter illustration tables. Each entry: {file, position: "header"|"inline", after_sentence, pdf_page}
  const illByCh = {};
  ILLUST.forEach((it) => {
    if (!illByCh[it.chapter]) illByCh[it.chapter] = [];
    illByCh[it.chapter].push(it);
  });
  function illustImg(file, alt, isHeader) {
    const wrap = document.createElement("figure");
    wrap.className = "illust";
    const img = document.createElement("img");
    // WebP 体积仅原 PNG 的 ~8%，限宽导出；加载失败回退到原 PNG。
    // 插图复用 russian 站已部署资源（../russian/illustrations-webp/）。
    img.loading = isHeader ? "eager" : "lazy";
    if (isHeader) img.fetchPriority = "high";
    img.decoding = "async";
    const webp = "../russian/illustrations-webp/" + file.replace(/\.png$/i, ".webp");
    const png = "../russian/illustrations/" + file;
    img.src = webp;
    img.onerror = () => { if (img.src.indexOf(".png") < 0) img.src = png; };
    img.alt = alt || "";
    const cap = document.createElement("figcaption");
    cap.className = "illust-cap";
    cap.textContent = "圣埃克苏佩里 原版插画";
    wrap.appendChild(img);
    wrap.appendChild(cap);
    return wrap;
  }

  const $ = (id) => document.getElementById(id);
  const audio = $("audio");

  /* ---------- 偏好持久化 ---------- */
  const PREF_KEY = "lp_ar_prefs_v1";
  const prefs = Object.assign(
    {
      mode: "pair", ipa: true, follow: true, auto: true,
      loop: false,            // 单句循环（跟读用）
      rate: 1, fs: 19, ch: 0
    },
    JSON.parse(localStorage.getItem(PREF_KEY) || "{}")
  );
  const savePrefs = () => localStorage.setItem(PREF_KEY, JSON.stringify(prefs));

  /* ---------- 播放状态 ---------- */
  let curChapter = Math.min(prefs.ch || 0, BOOK.chapters.length - 1);
  let curPid = null;      // 当前音频段落 id
  let curSi = null;       // 单句点读时的句索引
  let stopAt = null;      // 毫秒；到点停止
  let activeEl = null;
  let playMode = "para";  // "para" = 段落/连读，"sent" = 单句点读
  let playToken = 0;      // 打断令牌：自增即让所有在途的异步播放请求作废
  let pendingSeek = null; // 定位保险：{ms, token, tries}
  let chapterChain = -1;  // 朗读本章：进行中的章索引，>=0 时 ended 自动续播本章下一段
  let wholeChapter = false; // 整章连读模式（一章当作一个段落播放，文案/高亮不显示分段）
  let preAudio = null;      // 预加载的下一音频段，用于段间无缝续播

  // 缓存高频 DOM
  const elSeek = $("seek"), elTCur = $("tCur"), elTDur = $("tDur");

  /* =======================================================
     分词 + 音标渲染（阿语：逐词查 lexicon.js 拉丁转写）
     ======================================================= */
  const AR_RANGE = "\\u0600-\\u06FF\\u0750-\\u077F\\u08A0-\\u08FF\\uFB50-\\uFDFF\\uFE70-\\uFEFF";
  const AR_RE = new RegExp("^([^" + AR_RANGE + "]*)([" + AR_RANGE + "]+)([\\s\\S]*)$");

  function renderAr(text) {
    const frag = document.createDocumentFragment();
    const chunks = text.split(/(\s+)/);
    for (const chunk of chunks) {
      if (chunk === "") continue;
      if (/^\s+$/.test(chunk)) {
        frag.appendChild(document.createTextNode(chunk));
        continue;
      }
      const m = chunk.match(AR_RE);
      if (!m || !m[2]) {
        frag.appendChild(document.createTextNode(chunk));
        continue;
      }
      const [, pre, word, post] = m;
      const tok = document.createElement("span");
      tok.className = "tok";
      const wd = document.createElement("span");
      wd.className = "wd";
      wd.textContent = (pre || "") + word + (post || "");
      const ph = document.createElement("span");
      ph.className = "ph";
      // 去掉 harakat(变音符号)/tatweel(拉长符)/上标 alef 再查表，提高命中
      const norm = word.replace(/[؜-؝ؠ-﹯ﹰ-ﻼ]/g, "");
      ph.textContent = LEX[word] || LEX[norm] || "";
      tok.appendChild(wd);
      tok.appendChild(ph);
      frag.appendChild(tok);
    }
    return frag;
  }

  /* =======================================================
     渲染章节导航
     ======================================================= */
  function renderNav() {
    const nav = $("chapterNav");
    nav.innerHTML = "";
    BOOK.chapters.forEach((ch, i) => {
      const a = document.createElement("a");
      a.innerHTML =
        '<span class="cn-es"></span><span class="cn-zh"></span>';
      a.querySelector(".cn-es").textContent = ch.title_ar || ch.title_en;
      a.querySelector(".cn-zh").textContent = ch.title_zh;
      a.onclick = () => { openChapter(i); closeSidebarOnMobile(); };
      nav.appendChild(a);
    });
    $("bookAuthor").textContent =
      BOOK.meta.author_ar + " · " + BOOK.meta.author_zh;
    const m = BOOK.meta;
    $("sideStats").innerHTML =
      `全书 ${m.n_chapters} 章 · ${m.n_paras} 段 · ${m.n_sents} 句<br>` +
      `配音 ${m.voice}<br>音标：${m.ipa_note}` +
      `<hr class="sf-hr"><b>点读</b>：单击句子 = 只读这一句<br>` +
      `Shift+单击 / <b>⏵起读</b> = 从这句往下连读<br>` +
      `<b>←/→</b> 上一句 / 下一句 · <b>R</b> 重复本句 · <b>空格</b> 播放暂停`;
  }

  function markNav() {
    [...$("chapterNav").children].forEach((a, i) =>
      a.classList.toggle("on", i === curChapter)
    );
  }

  /* =======================================================
     渲染正文
     ======================================================= */
  function openChapter(i, keepScroll) {
    curChapter = Math.max(0, Math.min(i, BOOK.chapters.length - 1));
    prefs.ch = curChapter;
    savePrefs();
    const ch = BOOK.chapters[curChapter];
    const box = $("content");
    activeEl = null;          // 旧节点已随重渲染销毁
    box.innerHTML = "";

    const head = document.createElement("div");
    head.className = "chapter-head";
    const h = document.createElement("h1");
    h.className = "ch-es";
    h.textContent = ch.title_ar || ch.title_en;
    const sub = document.createElement("div");
    sub.className = "ch-zh";
    sub.textContent = ch.title_zh;
    head.appendChild(h);
    head.appendChild(sub);

    // Header illustration for this chapter (position == "header")
    const chIll = illByCh[curChapter] || [];
    const headerIll = chIll.find((x) => x.position === "header");
    if (headerIll) {
      const fig = illustImg(headerIll.file, (ch.title_ar || ch.title_en) + " 原版插画", true);
      fig.classList.add("illust-header");
      head.appendChild(fig);
    }

    box.appendChild(head);

    // For inline illustrations, place by per-chapter sentence index
    const inlineIlls = chIll.filter((x) => x.position === "inline");
    const inlineBySent = {};
    inlineIlls.forEach((it) => {
      const idx = (typeof it.after_sentence === "number") ? it.after_sentence : 0;
      if (!inlineBySent[idx]) inlineBySent[idx] = [];
      inlineBySent[idx].push(it);
    });
    let runningSentIdx = -1;

    const div = document.createElement("div");
    div.className = "para para-merged";
    div.dataset.pid = ch.paras[0] ? ch.paras[0].id : "";

    const bar = document.createElement("div");
    bar.className = "para-bar";
    const btn = document.createElement("button");
    btn.className = "para-play";
    btn.textContent = "▶ 朗读本章";
    btn.onclick = (e) => { e.stopPropagation(); playChapter(curChapter); };
    const idx = document.createElement("span");
    idx.className = "para-idx";
    const totalSents = ch.paras.reduce((a, p) => a + p.sents.length, 0);
    idx.textContent = `本章 ${totalSents} 句`;
    bar.appendChild(btn);
    bar.appendChild(idx);
    div.appendChild(bar);

    ch.paras.forEach((p, pi) => {
      p.sents.forEach((s, si) => {
        const sd = document.createElement("div");
        sd.className = "sent";
        sd.dataset.pid = p.id;
        sd.dataset.si = si;

        const esLine = document.createElement("div");
        esLine.className = "es-line";
        esLine.appendChild(renderAr(s.ar));

        const zh = document.createElement("div");
        zh.className = "zh-line";
        zh.textContent = s.zh || "";

        sd.appendChild(esLine);
        sd.appendChild(zh);

        if (p.audio && s.t) {
          /* --- 句级操作按钮（悬停浮现） --- */
          const ops = document.createElement("div");
          ops.className = "sent-ops";

          const bSolo = document.createElement("button");
          bSolo.className = "s-btn";
          bSolo.type = "button";
          bSolo.title = "只朗读这一句，读完即停";
          bSolo.textContent = "🔊 单句";
          bSolo.onclick = (e) => { e.stopPropagation(); playSentence(p.id, si, false); };

          const bChain = document.createElement("button");
          bChain.className = "s-btn ghost";
          bChain.type = "button";
          bChain.title = "从这一句开始往下连读";
          bChain.textContent = "⏵ 起读";
          bChain.onclick = (e) => { e.stopPropagation(); playSentence(p.id, si, true); };

          ops.appendChild(bSolo);
          ops.appendChild(bChain);
          sd.appendChild(ops);

          sd.title = "单击：只读这一句　Shift+单击：从这句起连读";
          sd.onclick = (e) => playSentence(p.id, si, e.shiftKey === true);
        } else {
          sd.classList.add("no-audio");
        }

        div.appendChild(sd);

        runningSentIdx += 1;
        const illustList = inlineBySent[runningSentIdx];
        if (illustList && illustList.length) {
          illustList.forEach((it) => {
            const fig = illustImg(it.file, (ch.title_ar || ch.title_en) + " 插画", false);
            fig.classList.add("illust-inline");
            div.appendChild(fig);
          });
        }
      });
    });

    box.appendChild(div);

    markNav();
    $("btnPrev").disabled = curChapter === 0;
    $("btnNext").disabled = curChapter === BOOK.chapters.length - 1;
    $("chapterFootLabel").textContent =
      `${(ch.title_ar || ch.title_en)} · ${ch.title_zh}`;
    $("readProgress").textContent =
      `第 ${curChapter + 1} / ${BOOK.chapters.length} 章`;
    if (!keepScroll) $("reader").scrollTop = 0;

    if (curPid) {
      updateNow(curPid);
      if (playMode === "sent" && curSi !== null) {
        markSolo(curPid, curSi);
        setActive(curPid, curSi);
      }
    }
  }

  /* =======================================================
     播放控制
     ======================================================= */
  function paraById(pid) {
    for (const ch of BOOK.chapters)
      for (const p of ch.paras) if (p.id === pid) return p;
    return null;
  }
  function chapterIdxOfPara(pid) {
    for (let i = 0; i < BOOK.chapters.length; i++)
      if (BOOK.chapters[i].paras.some((p) => p.id === pid)) return i;
    return -1;
  }

  function stopPlayback() {
    playToken++;
    stopAt = null;
    pendingSeek = null;
    chapterChain = -1;
    wholeChapter = false;
    preAudio = null;
    if (!audio.paused) { try { audio.pause(); } catch (e) { /* noop */ } }
  }

  function safePlay() {
    const pr = audio.play();
    if (pr && typeof pr.catch === "function") pr.catch(() => {});
  }

  function seekTo(ms) {
    pendingSeek = { ms: ms, token: playToken, tries: 0 };
    try { audio.currentTime = ms / 1000; } catch (e) { /* noop */ }
  }

  function fixSeek() {
    if (!pendingSeek) return;
    if (pendingSeek.token !== playToken) { pendingSeek = null; return; }
    const off = Math.abs(audio.currentTime * 1000 - pendingSeek.ms);
    if (off > 400 && pendingSeek.tries < 6) {
      pendingSeek.tries++;
      try { audio.currentTime = pendingSeek.ms / 1000; } catch (e) { /* noop */ }
    } else if (off <= 400) {
      pendingSeek = null;
    }
  }
  audio.addEventListener("canplay", fixSeek);
  audio.addEventListener("playing", fixSeek);
  audio.addEventListener("seeked", fixSeek);
  audio.addEventListener("timeupdate", fixSeek);

  function ensureSrc(pid, cb) {
    const token = playToken;
    const run = () => { if (token === playToken) cb(); };

    if (curPid === pid && audio.src && audio.readyState >= 1) { run(); return; }

    curPid = pid;
    audio.src = "audio/" + pid + ".mp3";

    const cleanup = () => {
      audio.removeEventListener("loadedmetadata", onReady);
      audio.removeEventListener("error", onErr);
    };
    const onReady = () => { cleanup(); run(); };
    const onErr = () => {
      cleanup();
      if (token !== playToken) return;
      $("nowSub").textContent = "音频加载失败：audio/" + pid + ".mp3";
    };
    audio.addEventListener("loadedmetadata", onReady);
    audio.addEventListener("error", onErr);
    audio.load();
  }

  function applyRate() {
    audio.playbackRate = prefs.rate;
    audio.preservesPitch = true;
    audio.mozPreservesPitch = true;
    audio.webkitPreservesPitch = true;
  }

  function playParagraph(pid, fromMs, whole) {
    stopPlayback();
    playMode = "para";
    curSi = null;
    markSolo(null, null);
    if (whole) { chapterChain = chapterIdxOfPara(pid); wholeChapter = true; }
    ensureSrc(pid, () => {
      audio.currentTime = (fromMs || 0) / 1000;
      stopAt = null;
      applyRate();
      safePlay();
      updateNow(pid);
    });
    if (whole) preloadNextPara(pid);
  }

  function nextParaInChapter(pid) {
    const ci = chapterIdxOfPara(pid);
    if (ci < 0) return null;
    const ch = BOOK.chapters[ci];
    const pi = ch.paras.findIndex((p) => p.id === pid);
    for (let k = pi + 1; k < ch.paras.length; k++)
      if (ch.paras[k].audio) return ch.paras[k].id;
    return null;
  }
  function preloadNextPara(pid) {
    const nx = nextParaInChapter(pid);
    preAudio = null;
    if (!nx) return;
    preAudio = new Audio();
    preAudio.preload = "auto";
    preAudio.src = "audio/" + nx + ".mp3";
  }

  function playChapter(ci) {
    const ch = BOOK.chapters[ci];
    if (!ch) return;
    const first = ch.paras.find((p) => p.audio);
    if (!first) return;
    chapterChain = ci;
    wholeChapter = true;
    playParagraph(first.id, 0, true);
  }

  function chapterSentInfo(pid, siInPara) {
    const ci = chapterIdxOfPara(pid);
    const ch = BOOK.chapters[ci];
    let acc = 0;
    for (const p of ch.paras) {
      if (p.id === pid) break;
      acc += p.sents.length;
    }
    const total = ch.paras.reduce((a, p) => a + p.sents.length, 0);
    return { globalIdx: acc + (siInPara != null ? siInPara : 0) + 1, total };
  }

  function playSentence(pid, si, chain) {
    const p = paraById(pid);
    if (!p || !p.audio) return;
    const s = p.sents[si];
    if (!s || !s.t) return;

    stopPlayback();
    playMode = chain ? "para" : "sent";
    curSi = chain ? null : si;

    markSolo(chain ? null : pid, si);
    setActive(pid, si);

    ensureSrc(pid, () => {
      audio.currentTime = s.t[0] / 1000;
      stopAt = chain ? null : s.t[1];
      applyRate();
      safePlay();
      updateNow(pid);
    });
  }

  function currentSentence() {
    if (curSi === null || !curPid) return null;
    const p = paraById(curPid);
    return p ? p.sents[curSi] : null;
  }

  function replaySentence() {
    if (curPid && curSi !== null) return playSentence(curPid, curSi, false);
    if (activeEl) return playSentence(activeEl.dataset.pid, +activeEl.dataset.si, false);
    const ch = BOOK.chapters[curChapter];
    const p = ch.paras.find((x) => x.audio);
    if (p) playSentence(p.id, 0, false);
  }

  function stepSentence(delta) {
    let pid = curPid, si = curSi;
    if (pid == null || si == null) {
      if (activeEl) { pid = activeEl.dataset.pid; si = +activeEl.dataset.si; }
      else {
        const ch0 = BOOK.chapters[curChapter];
        const p0 = ch0.paras.find((x) => x.audio);
        if (!p0) return;
        pid = p0.id;
        si = delta > 0 ? -1 : 0;
      }
    }
    const ci = chapterIdxOfPara(pid);
    if (ci < 0) return;
    const ch = BOOK.chapters[ci];
    let pi = ch.paras.findIndex((p) => p.id === pid);
    let t = si + delta;
    let guard = 0;
    while (guard++ < 5000) {
      const p = ch.paras[pi];
      if (!p) return;
      if (t >= 0 && t < p.sents.length) {
        if (p.audio && p.sents[t].t) {
          if (ci !== curChapter) openChapter(ci, true);
          playSentence(p.id, t, false);
          scrollToSent(p.id, t);
          return;
        }
        t += delta;
        continue;
      }
      if (t < 0) {
        pi--;
        if (pi < 0) return;
        t = ch.paras[pi].sents.length - 1;
      } else {
        pi++;
        if (pi >= ch.paras.length) return;
        t = 0;
      }
    }
  }

  function scrollToSent(pid, si) {
    const el = document.querySelector(`.sent[data-pid="${pid}"][data-si="${si}"]`);
    if (!el) return;
    const r = $("reader").getBoundingClientRect();
    const b = el.getBoundingClientRect();
    if (b.top < r.top + 60 || b.bottom > r.bottom - 60)
      el.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function setActive(pid, si) {
    const el = document.querySelector(`.sent[data-pid="${pid}"][data-si="${si}"]`);
    if (!el) return;
    if (activeEl && activeEl !== el) activeEl.classList.remove("active");
    activeEl = el;
    el.classList.add("active");
  }

  function markSolo(pid, si) {
    document.querySelectorAll(".sent.solo").forEach((e) => e.classList.remove("solo"));
    if (pid == null) return;
    const el = document.querySelector(`.sent[data-pid="${pid}"][data-si="${si}"]`);
    if (el) el.classList.add("solo");
  }

  function updateNow(pid) {
    const ci = chapterIdxOfPara(pid);
    const ch = BOOK.chapters[ci];
    const p = paraById(pid);
    const pi = ch ? ch.paras.findIndex((x) => x.id === pid) : -1;
    $("nowTitle").textContent = ch ? `${(ch.title_ar || ch.title_en)} · ${ch.title_zh}` : "";
    let sub;
    if (wholeChapter && chapterChain >= 0) {
      const info = chapterSentInfo(pid, null);
      sub = `朗读本章 · 本章 ${info.total} 句`;
    } else if (playMode === "sent" && curSi !== null) {
      sub = `第 ${pi + 1} / ${ch.paras.length} 段 · 单句点读 第 ${curSi + 1} 句`;
      if (prefs.loop) sub += "（循环）";
    } else {
      sub = `第 ${pi + 1} / ${ch.paras.length} 段 · ${p.sents.length} 句`;
    }
    $("nowSub").textContent = sub;
    document.querySelectorAll(".para").forEach((d) =>
      d.classList.toggle("playing", wholeChapter ? true : d.dataset.pid === pid)
    );
  }

  function nextParagraph() {
    const ci = chapterIdxOfPara(curPid);
    if (ci < 0) return null;
    const ch = BOOK.chapters[ci];
    const pi = ch.paras.findIndex((p) => p.id === curPid);
    for (let k = pi + 1; k < ch.paras.length; k++)
      if (ch.paras[k].audio) return { ci, pid: ch.paras[k].id };
    for (let c = ci + 1; c < BOOK.chapters.length; c++)
      for (const p of BOOK.chapters[c].paras)
        if (p.audio) return { ci: c, pid: p.id };
    return null;
  }

  audio.addEventListener("ended", () => {
    if (playMode === "sent") {
      if (prefs.loop && curPid && curSi !== null) {
        playSentence(curPid, curSi, false);
      } else {
        setPlayIcon(false);
      }
      return;
    }
    if (!prefs.auto && chapterChain < 0) { setPlayIcon(false); return; }
    if (chapterChain >= 0 && chapterChain === curChapter) {
      const ch = BOOK.chapters[curChapter];
      let pi = ch.paras.findIndex((p) => p.id === curPid);
      while (pi + 1 < ch.paras.length) {
        pi++;
        if (ch.paras[pi].audio) {
          wholeChapter = true;
          playParagraph(ch.paras[pi].id, 0, true);
          return;
        }
      }
      chapterChain = -1;
      wholeChapter = false;
      setPlayIcon(false);
      return;
    }
    if (!prefs.auto) { setPlayIcon(false); return; }
    const nx = nextParagraph();
    if (!nx) { setPlayIcon(false); return; }
    if (nx.ci !== curChapter) openChapter(nx.ci);
    playParagraph(nx.pid, 0);
  });

  audio.addEventListener("play", () => setPlayIcon(true));
  audio.addEventListener("pause", () => setPlayIcon(false));

  function setPlayIcon(playing) {
    $("playIcon").textContent = playing ? "❙❙" : "▶";
  }

  /* ---------- 进度 / 高亮 ---------- */
  let seeking = false;
  function fmt(t) {
    if (!isFinite(t)) return "0:00";
    const m = Math.floor(t / 60), s = Math.floor(t % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  function tick() {
    if (!audio.paused && curPid) {
      const ms = audio.currentTime * 1000;
      if (stopAt !== null && ms >= stopAt) {
        const s = playMode === "sent" ? currentSentence() : null;
        if (s && s.t && prefs.loop) {
          audio.currentTime = s.t[0] / 1000;
        } else {
          audio.pause();
          stopAt = null;
        }
      } else if (playMode !== "sent") {
        highlight(ms);
      }
    }
    if (!seeking && audio.duration) {
      elSeek.value = Math.round((audio.currentTime / audio.duration) * 1000);
      elTCur.textContent = fmt(audio.currentTime);
      elTDur.textContent = fmt(audio.duration);
    }
    requestAnimationFrame(tick);
  }

  function highlight(ms) {
    const p = paraById(curPid);
    if (!p) return;
    let idx = -1;
    for (let i = 0; i < p.sents.length; i++) {
      const t = p.sents[i].t;
      if (t && ms >= t[0] && ms < t[1]) { idx = i; break; }
    }
    if (idx < 0) return;
    const el = document.querySelector(
      `.sent[data-pid="${curPid}"][data-si="${idx}"]`
    );
    if (!el || el === activeEl) {
      if (wholeChapter) updateWholeSub(idx);
      return;
    }
    if (activeEl) activeEl.classList.remove("active");
    activeEl = el;
    el.classList.add("active");
    if (wholeChapter) updateWholeSub(idx);
    if (prefs.follow) {
      const r = $("reader").getBoundingClientRect();
      const b = el.getBoundingClientRect();
      if (b.top < r.top + 60 || b.bottom > r.bottom - 60) {
        el.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }
  }

  function updateWholeSub(siInPara) {
    const info = chapterSentInfo(curPid, siInPara);
    $("nowSub").textContent = `朗读本章 · 本章第 ${info.globalIdx} / ${info.total} 句`;
    document.querySelectorAll(".para").forEach((d) =>
      d.classList.add("playing")
    );
  }
  requestAnimationFrame(tick);

  /* =======================================================
     控件绑定
     ======================================================= */
  $("btnPlay").onclick = () => {
    if (audio.paused) {
      if (!curPid) {
        const ch = BOOK.chapters[curChapter];
        const p = ch.paras.find((x) => x.audio);
        if (p) playParagraph(p.id, 0);
        return;
      }
      if (playMode === "sent" && curSi !== null) {
        const s = currentSentence();
        if (s && s.t) {
          if (audio.currentTime * 1000 >= s.t[1] - 40)
            audio.currentTime = s.t[0] / 1000;
          stopAt = s.t[1];
          applyRate();
          safePlay();
          return;
        }
      }
      stopAt = null;
      applyRate();
      safePlay();
    } else audio.pause();
  };

  $("btnRepeat").onclick = () => replaySentence();
  $("btnPrevSent").onclick = () => stepSentence(-1);
  $("btnNextSent").onclick = () => stepSentence(1);

  const seek = elSeek;
  seek.addEventListener("input", () => { seeking = true; });
  seek.addEventListener("change", () => {
    if (audio.duration) {
      audio.currentTime = (seek.value / 1000) * audio.duration;
      stopAt = null;
      playMode = "para";
      curSi = null;
      markSolo(null, null);
      if (curPid) updateNow(curPid);
    }
    seeking = false;
  });

  const rate = $("rate");
  function setRate(v) {
    prefs.rate = Math.min(2, Math.max(0.5, +v));
    rate.value = prefs.rate;
    $("rateVal").textContent = prefs.rate.toFixed(2) + "×";
    applyRate();
    savePrefs();
  }
  rate.addEventListener("input", () => setRate(rate.value));
  $("btnRateReset").onclick = () => setRate(1);

  function setMode(m) {
    prefs.mode = m;
    document.body.classList.remove("mode-pair", "mode-col", "mode-es", "mode-zh");
    document.body.classList.add("mode-" + m);
    [...$("modeSeg").children].forEach((b) =>
      b.classList.toggle("on", b.dataset.mode === m)
    );
    savePrefs();
  }
  [...$("modeSeg").children].forEach((b) => {
    b.onclick = () => setMode(b.dataset.mode);
  });

  $("chkIpa").onchange = (e) => {
    prefs.ipa = e.target.checked;
    document.body.classList.toggle("no-ipa", !prefs.ipa);
    savePrefs();
  };
  $("chkFollow").onchange = (e) => { prefs.follow = e.target.checked; savePrefs(); };
  $("chkAuto").onchange = (e) => { prefs.auto = e.target.checked; savePrefs(); };
  $("chkLoop").onchange = (e) => {
    prefs.loop = e.target.checked;
    savePrefs();
    if (curPid) updateNow(curPid);
  };

  function setFs(v) {
    prefs.fs = Math.min(30, Math.max(14, v));
    document.documentElement.style.setProperty("--fs", prefs.fs + "px");
    savePrefs();
  }
  $("btnFontUp").onclick = () => setFs(prefs.fs + 1);
  $("btnFontDn").onclick = () => setFs(prefs.fs - 1);

  $("btnPrev").onclick = () => openChapter(curChapter - 1);
  $("btnNext").onclick = () => openChapter(curChapter + 1);

  $("btnMenu").onclick = () => {
    $("sidebar").classList.toggle("hidden");
    if (window.innerWidth <= 900)
      $("overlay").classList.toggle("on", !$("sidebar").classList.contains("hidden"));
  };
  $("overlay").onclick = () => {
    $("sidebar").classList.add("hidden");
    $("overlay").classList.remove("on");
  };
  function closeSidebarOnMobile() {
    if (window.innerWidth <= 900) {
      $("sidebar").classList.add("hidden");
      $("overlay").classList.remove("on");
    }
  }

  document.addEventListener("keydown", (e) => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.code === "Space") { e.preventDefault(); $("btnPlay").onclick(); return; }
    if (e.code === "ArrowRight") { e.preventDefault(); stepSentence(1); return; }
    if (e.code === "ArrowLeft") { e.preventDefault(); stepSentence(-1); return; }
    if (e.key === "r" || e.key === "R") { e.preventDefault(); replaySentence(); return; }
  });

  /* =======================================================
     初始化
     ======================================================= */
  renderNav();
  setMode(prefs.mode);
  setFs(prefs.fs);
  setRate(prefs.rate);
  $("chkIpa").checked = prefs.ipa;
  document.body.classList.toggle("no-ipa", !prefs.ipa);
  $("chkFollow").checked = prefs.follow;
  $("chkAuto").checked = prefs.auto;
  $("chkLoop").checked = prefs.loop;
  if (window.innerWidth <= 900) $("sidebar").classList.add("hidden");
  openChapter(curChapter);
})();
