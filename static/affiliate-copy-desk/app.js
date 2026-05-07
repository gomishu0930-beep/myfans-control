const state = {
  rows: [],
  filtered: [],
  selected: null,
  query: "巨乳",
  creator: "all",
  duration: "all",
  rate: "all",
  activeTab: "post",
  imageCount: 2,
  generatedImageUrls: [],
};

const els = {
  resultSummary: document.querySelector("#resultSummary"),
  genreSearch: document.querySelector("#genreSearch"),
  creatorFilter: document.querySelector("#creatorFilter"),
  durationFilter: document.querySelector("#durationFilter"),
  rateFilter: document.querySelector("#rateFilter"),
  resultList: document.querySelector("#resultList"),
  selectedMeta: document.querySelector("#selectedMeta"),
  selectedTitle: document.querySelector("#selectedTitle"),
  previewImage: document.querySelector("#previewImage"),
  durationBadge: document.querySelector("#durationBadge"),
  rateBadge: document.querySelector("#rateBadge"),
  affiliateLink: document.querySelector("#affiliateLink"),
  postOutput: document.querySelector("#postOutput"),
  assetOutput: document.querySelector("#assetOutput"),
  promptOutput: document.querySelector("#promptOutput"),
  generatedGrid: document.querySelector("#generatedGrid"),
  generateImages: document.querySelector("#generateImages"),
  copyImageList: document.querySelector("#copyImageList"),
  copyAll: document.querySelector("#copyAll"),
  resetFilters: document.querySelector("#resetFilters"),
  toast: document.querySelector("#toast"),
};

const safeWords = [
  ["中出し", "本編の見どころ"],
  ["ハメ撮り", "リアル系作品"],
  ["セックス", "濃密な時間"],
  ["おっぱい", "スタイル"],
  ["爆乳", "存在感のあるスタイル"],
  ["巨乳", "グラマラス"],
  ["童貞", "初心者"],
  ["肉便器", "攻めたコンセプト"],
  ["まんこ", "本編"],
  ["ちんこ", "本編"],
  ["イキ", "盛り上がり"],
  ["潮", "迫力"],
  ["顔出し", "表情まで楽しめる"],
];

function sanitize(text = "") {
  let value = String(text).replace(/\s+/g, " ").trim();
  for (const [from, to] of safeWords) value = value.replaceAll(from, to);
  return value;
}

function compact(text = "", length = 72) {
  const clean = sanitize(text);
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean;
}

function durationSeconds(duration = "") {
  const parts = duration.split(":").map(Number);
  if (parts.some(Number.isNaN)) return 0;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return 0;
}

function durationBucket(row) {
  const seconds = durationSeconds(row.duration);
  if (seconds < 300) return "short";
  if (seconds < 1800) return "middle";
  return "long";
}

function angleFor(row) {
  const seconds = durationSeconds(row.duration);
  const description = row.description || "";
  if (row.affiliate_reward_rate === "50") return "高報酬率";
  if (/限定|先着|割引|販売終了|値下げ|特別/i.test(description)) return "限定感";
  if (seconds >= 3600) return "長尺";
  if (seconds < 300) return "短尺";
  return "王道";
}

function postText(row) {
  const title = compact(row.description || row.image_alt, 62);
  const angle = angleFor(row);
  const duration = row.duration || "尺不明";
  const hooks = {
    高報酬率: "ちょっと濃いめで、見始めたら止まらないやつ。",
    限定感: "このムード、今だけ感あって妙にそそられる。",
    長尺: "じっくり見たい夜に刺さる、かなり濃いめの長尺。",
    短尺: "短いのに妙に色っぽくて、続きが気になる。",
    王道: "サムネの時点で空気がもう色っぽい。",
  };

  return `${hooks[angle] || hooks.王道} ${title} / ${duration} ${row.affiliate_url}`;
}

function assetText(row) {
  return [
    `【作品No.${row.index} 添付素材】`,
    `サムネイル画像: ${row.thumbnail_url}`,
    `Markdown画像: ![sample](${row.thumbnail_url})`,
    `投稿URL: ${row.post_url}`,
    `アフィリURL: ${row.affiliate_url}`,
    "",
    "添付メモ:",
    `- 作者: ${row.creator || ""}`,
    `- 尺: ${row.duration || ""}`,
    `- 報酬率: ${row.affiliate_reward_rate || ""}%`,
    `- 訴求軸: ${angleFor(row)}`,
  ].join("\n");
}

function promptText(row) {
  const title = compact(row.description || row.image_alt, 58);
  const angle = angleFor(row);

  return [
    `【作品No.${row.index} 生成プロンプト】`,
    "",
    "image2 写真生成プロンプト 1:",
    `投稿サムネに近い雰囲気の日本人女性ポートレート写真。成人女性、室内、スマホ自撮り風、やわらかい照明、少し色っぽい表情、上半身中心、露出は控えめ、下着や裸は不可、実在人物の再現不可、1:1、自然な肌、SNS投稿用。作品の訴求軸: ${angle}。参考メモ: ${title}`,
    "",
    "image2 写真生成プロンプト 2:",
    `成人女性の雰囲気写真。暗めの部屋、ベッドサイドの自然光、顔は少しぼかし気味、親密な距離感、グラビア風だが露骨ではない、服を着ている、性的行為なし、実在サムネの完全コピー不可、1:1。テキストなし。`,
    "",
    "image2 写真生成プロンプト 3:",
    `プレミアム投稿のサンプル画像風。成人女性、鏡越しの自撮り、落ち着いた背景、肌の露出は控えめ、少し誘惑的な視線、リアル写真調、広告素材として使いやすい余白、1:1、no nudity, no explicit sexual content, no minors.`,
    "",
    "image2 写真生成プロンプト 4:",
    `myfans系アフィリエイト投稿に合う写真素材。成人女性、クローズアップ、柔らかい影、親密で少し危うい空気、服あり、露骨な体の強調なし、実写風、高解像度、SNSサムネイル向け、1:1。`,
    "",
    "短尺プレビュー動画プロンプト:",
    `6-second vertical teaser video, non-explicit adult lifestyle promotion, close-up of phone screen scrolling a premium content page, quick cuts of soft lighting and blurred silhouette, overlay Japanese captions "${title}" and "本編はリンクから", polished SNS ad style, no nudity, no sexual act, no minors`,
    "",
    "投稿文生成メモ:",
    `訴求軸は「${angle}」。説明は露骨にせず、尺・作者・雰囲気・詳細確認のCTAを中心にする。`,
    "",
    `アフィリURL: ${row.affiliate_url}`,
  ].join("\n");
}

function imagePrompts(row) {
  const title = compact(row.description || row.image_alt, 58);
  const angle = angleFor(row);
  return [
    `投稿サムネに近い雰囲気の日本人女性ポートレート写真。成人女性、室内、スマホ自撮り風、やわらかい照明、少し色っぽい表情、上半身中心、露出は控えめ、下着や裸は不可、実在人物の再現不可、1:1、自然な肌、SNS投稿用。作品の訴求軸: ${angle}。参考メモ: ${title}`,
    `成人女性の雰囲気写真。暗めの部屋、ベッドサイドの自然光、顔は少しぼかし気味、親密な距離感、グラビア風だが露骨ではない、服を着ている、性的行為なし、実在サムネの完全コピー不可、1:1。テキストなし。`,
    `プレミアム投稿のサンプル画像風。成人女性、鏡越しの自撮り、落ち着いた背景、肌の露出は控えめ、少し誘惑的な視線、リアル写真調、広告素材として使いやすい余白、1:1、no nudity, no explicit sexual content, no minors.`,
    `myfans系アフィリエイト投稿に合う写真素材。成人女性、クローズアップ、柔らかい影、親密で少し危うい空気、服あり、露骨な体の強調なし、実写風、高解像度、SNSサムネイル向け、1:1。`,
  ];
}

function allText(row) {
  return [postText(row), "", "==== 添付素材 ====", assetText(row), "", "==== 生成プロンプト ====", promptText(row)].join("\n");
}

function fillFilters() {
  const creators = [...new Set(state.rows.map((row) => row.creator).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ja"));
  els.creatorFilter.innerHTML = `<option value="all">すべて</option>${creators
    .map((creator) => `<option value="${escapeAttr(creator)}">${escapeHtml(creator)}</option>`)
    .join("")}`;

  const rates = [...new Set(state.rows.map((row) => row.affiliate_reward_rate).filter(Boolean))].sort((a, b) => Number(b) - Number(a));
  els.rateFilter.innerHTML = `<option value="all">すべて</option>${rates
    .map((rate) => `<option value="${escapeAttr(rate)}">${rate}%</option>`)
    .join("")}`;
}

function applyFilters() {
  const q = state.query.trim().toLowerCase();
  state.filtered = state.rows.filter((row) => {
    const haystack = [
      "巨乳",
      row.creator,
      row.description,
      row.image_alt,
      row.duration,
      row.affiliate_reward_rate ? `${row.affiliate_reward_rate}%` : "",
      angleFor(row),
    ]
      .join(" ")
      .toLowerCase();

    const queryOk = !q || haystack.includes(q);
    const creatorOk = state.creator === "all" || row.creator === state.creator;
    const durationOk = state.duration === "all" || durationBucket(row) === state.duration;
    const rateOk = state.rate === "all" || row.affiliate_reward_rate === state.rate;
    return queryOk && creatorOk && durationOk && rateOk;
  });

  if (!state.filtered.includes(state.selected)) state.selected = state.filtered[0] || null;
  render();
}

function render() {
  els.resultSummary.textContent = `${state.filtered.length}件 / ${state.rows.length}件`;
  els.resultList.innerHTML = state.filtered.map(renderCard).join("");
  renderDetail();
  lucide.createIcons();
}

function renderCard(row) {
  const selected = state.selected && row.index === state.selected.index ? " selected" : "";
  return `
    <button class="work-card${selected}" type="button" data-index="${row.index}">
      <div class="thumb">
        <img src="${escapeAttr(row.thumbnail_url)}" alt="" loading="lazy" />
        <span class="duration">${escapeHtml(row.duration || "--:--")}</span>
      </div>
      <div class="card-body">
        <div class="card-title">${escapeHtml(compact(row.description || row.image_alt, 80))}</div>
        <div class="meta-row">
          <span>${escapeHtml(compact(row.creator || "", 18))}</span>
          <span class="rate">${escapeHtml(row.affiliate_reward_rate || "--")}%</span>
        </div>
      </div>
    </button>
  `;
}

function renderDetail() {
  const row = state.selected;
  const disabled = !row;
  els.copyAll.disabled = disabled;

  if (!row) {
    els.selectedMeta.textContent = "未選択";
    els.selectedTitle.textContent = "作品を選択";
    els.previewImage.removeAttribute("src");
    els.durationBadge.textContent = "--:--";
    els.rateBadge.textContent = "報酬率 --%";
    els.affiliateLink.href = "#";
    els.postOutput.value = "";
    els.assetOutput.value = "";
    els.promptOutput.value = "";
    els.generatedGrid.innerHTML = "";
    return;
  }

  els.selectedMeta.textContent = `No.${row.index} / ${row.creator || "作者不明"} / ${row.published || ""}`;
  els.selectedTitle.textContent = compact(row.description || row.image_alt, 74);
  els.previewImage.src = row.thumbnail_url;
  els.durationBadge.textContent = row.duration || "--:--";
  els.rateBadge.textContent = `報酬率 ${row.affiliate_reward_rate || "--"}%`;
  els.affiliateLink.href = row.affiliate_url;
  els.postOutput.value = postText(row);
  els.assetOutput.value = assetText(row);
  els.promptOutput.value = promptText(row);
  renderGeneratedImages();
}

function renderGeneratedImages() {
  const row = state.selected;
  if (!row) return;
  state.generatedImageUrls = [];

  const styles = [
    ["自撮り風", "近距離・柔らかい照明", "#c8745e", "#223d57", "58"],
    ["ベッドサイド風", "暗め・親密な距離感", "#2c6b55", "#c6b4a4", "20"],
    ["鏡越し風", "落ち着いた背景・余白あり", "#315f8f", "#9b6b64", "42"],
    ["広告サムネ風", "クローズアップ・高コントラスト", "#231f20", "#e65f2b", "64"],
  ];

  els.generatedGrid.innerHTML = styles
    .slice(0, state.imageCount)
    .map(([name, note, toneA, toneB, left], index) => {
      const label = compact(row.description || row.image_alt, 30);
      const imageUrl = generatedImageDataUrl({ row, index, name, label, toneA, toneB, left });
      return `
        <article class="generated-card">
          <div class="generated-photo">
            <img src="${escapeAttr(imageUrl)}" alt="${escapeAttr(name)} generated image ${index + 1}" />
            <span class="photo-badge">image2 ${index + 1}</span>
            <div class="photo-shade"></div>
            <div class="photo-label">${escapeHtml(label)}</div>
          </div>
          <div class="generated-caption">
            <strong>${escapeHtml(name)}</strong>
            <p>${escapeHtml(note)}。露骨な描写を避けた投稿近似素材。</p>
            <p class="image-link">${escapeHtml(imageUrl.slice(0, 92))}...</p>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderGeneratedApiImages(images) {
  const row = state.selected;
  if (!row) return;
  state.generatedImageUrls = images.map((image) => image.url);
  els.generatedGrid.innerHTML = images
    .map((image, index) => {
      const label = compact(row.description || row.image_alt, 30);
      return `
        <article class="generated-card">
          <div class="generated-photo">
            <img src="${escapeAttr(image.url)}" alt="image2 generated image ${index + 1}" />
            <span class="photo-badge">image2 ${index + 1}</span>
            <div class="photo-shade"></div>
            <div class="photo-label">${escapeHtml(label)}</div>
          </div>
          <div class="generated-caption">
            <strong>image2生成済み</strong>
            <p>OpenAI APIで生成した投稿近似素材。</p>
            <p class="image-link">${escapeHtml(image.url)}</p>
          </div>
        </article>
      `;
    })
    .join("");
}

function generatedImageDataUrl({ row, index, name, label, toneA, toneB, left }) {
  const seed = Number(row.index || 1) * 17 + index * 31;
  const faceX = 210 + ((seed % 7) - 3) * 9;
  const faceY = 122 + ((seed % 5) - 2) * 6;
  const bodyX = Number(left) * 5.12;
  const title = escapeSvg(label);
  const creator = escapeSvg(compact(row.creator || "myfans", 20));
  const duration = escapeSvg(row.duration || "--:--");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="${toneA}"/>
          <stop offset="1" stop-color="${toneB}"/>
        </linearGradient>
        <radialGradient id="glow" cx=".46" cy=".24" r=".62">
          <stop offset="0" stop-color="#ffe3d1" stop-opacity=".9"/>
          <stop offset=".42" stop-color="#ffffff" stop-opacity=".15"/>
          <stop offset="1" stop-color="#000000" stop-opacity=".28"/>
        </radialGradient>
        <filter id="soft">
          <feGaussianBlur stdDeviation="18"/>
        </filter>
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="3" stitchTiles="stitch"/>
          <feColorMatrix type="saturate" values="0"/>
          <feComponentTransfer>
            <feFuncA type="table" tableValues="0 .12"/>
          </feComponentTransfer>
        </filter>
      </defs>
      <rect width="1024" height="1024" fill="url(#bg)"/>
      <rect width="1024" height="1024" fill="url(#glow)"/>
      <circle cx="${160 + seed % 160}" cy="${160 + seed % 90}" r="230" fill="#fff1e8" opacity=".16" filter="url(#soft)"/>
      <circle cx="${790 - seed % 110}" cy="${680 + seed % 80}" r="260" fill="#111827" opacity=".24" filter="url(#soft)"/>
      <ellipse cx="${bodyX}" cy="660" rx="174" ry="318" fill="#2a2426" opacity=".42"/>
      <ellipse cx="${bodyX}" cy="592" rx="150" ry="278" fill="#d7b5a3" opacity=".72"/>
      <ellipse cx="${bodyX - 82}" cy="690" rx="58" ry="164" fill="#cab0a2" opacity=".58"/>
      <ellipse cx="${bodyX + 82}" cy="690" rx="58" ry="164" fill="#cab0a2" opacity=".58"/>
      <circle cx="${faceX}" cy="${faceY}" r="78" fill="#e9c5ad" opacity=".96"/>
      <path d="M${faceX - 78} ${faceY + 6} C${faceX - 64} ${faceY - 98}, ${faceX + 84} ${faceY - 100}, ${faceX + 78} ${faceY + 10} C${faceX + 42} ${faceY - 22}, ${faceX - 36} ${faceY - 20}, ${faceX - 78} ${faceY + 6}Z" fill="#3b2927" opacity=".85"/>
      <rect x="0" y="0" width="1024" height="1024" fill="url(#grain)"/>
      <rect x="0" y="690" width="1024" height="334" fill="#000" opacity=".38"/>
      <text x="44" y="760" fill="#fff" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="34" font-weight="800">${title}</text>
      <text x="44" y="818" fill="#fff" opacity=".9" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="25" font-weight="700">${creator}</text>
      <rect x="804" y="44" width="156" height="58" rx="29" fill="#fff" opacity=".92"/>
      <text x="832" y="82" fill="#171717" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="24" font-weight="900">image2 ${index + 1}</text>
      <rect x="44" y="884" width="136" height="54" rx="14" fill="#111827" opacity=".86"/>
      <text x="70" y="920" fill="#fff" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="25" font-weight="900">${duration}</text>
      <text x="44" y="972" fill="#fff" opacity=".72" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif" font-size="19" font-weight="700">generated preview / non-explicit</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function escapeSvg(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.left = "-9999px";
    document.body.appendChild(helper);
    helper.select();
    document.execCommand("copy");
    helper.remove();
  }
  showToast("コピーしました");
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 1300);
}

function bindEvents() {
  els.genreSearch.addEventListener("input", (event) => {
    state.query = event.target.value;
    document.querySelectorAll(".chip").forEach((chip) => chip.classList.toggle("active", chip.dataset.chip === state.query));
    applyFilters();
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.query = chip.dataset.chip;
      els.genreSearch.value = state.query;
      document.querySelectorAll(".chip").forEach((item) => item.classList.toggle("active", item === chip));
      applyFilters();
    });
  });

  els.creatorFilter.addEventListener("change", (event) => {
    state.creator = event.target.value;
    applyFilters();
  });

  els.durationFilter.addEventListener("change", (event) => {
    state.duration = event.target.value;
    applyFilters();
  });

  els.rateFilter.addEventListener("change", (event) => {
    state.rate = event.target.value;
    applyFilters();
  });

  els.resultList.addEventListener("click", (event) => {
    const card = event.target.closest(".work-card");
    if (!card) return;
    state.selected = state.rows.find((row) => String(row.index) === card.dataset.index) || null;
    render();
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.activeTab = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
      document.querySelectorAll(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${state.activeTab}`));
    });
  });

  document.querySelectorAll("[data-image-count]").forEach((button) => {
    button.addEventListener("click", () => {
      state.imageCount = Number(button.dataset.imageCount);
      document.querySelectorAll("[data-image-count]").forEach((item) => item.classList.toggle("active", item === button));
      renderGeneratedImages();
    });
  });

  els.generateImages.addEventListener("click", async () => {
    if (!state.selected) return;
    els.generateImages.disabled = true;
    els.generateImages.innerHTML = '<i data-lucide="loader-circle"></i> 生成中';
    lucide.createIcons();
    try {
      const apiUrl = window.AFFILIATE_COPY_DESK_IMAGE_API_URL;
      if (!apiUrl) throw new Error("画像生成APIが設定されていません");
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          count: state.imageCount,
          work_index: state.selected.index,
          prompts: imagePrompts(state.selected).slice(0, state.imageCount),
        }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail));
      }
      const data = await response.json();
      renderGeneratedApiImages(data.images || []);
      showToast(`${(data.images || []).length}枚生成しました`);
    } catch (error) {
      renderGeneratedImages();
      showToast(`API未使用: ${error.message}`);
    } finally {
      els.generateImages.disabled = false;
      els.generateImages.innerHTML = '<i data-lucide="sparkles"></i> image2生成';
      lucide.createIcons();
    }
  });

  els.copyImageList.addEventListener("click", () => {
    const urls = state.generatedImageUrls.length
      ? state.generatedImageUrls
      : [...els.generatedGrid.querySelectorAll(".generated-photo img")].map((img) => img.src);
    copyText(urls.join("\n"));
  });

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.querySelector(`#${button.dataset.copyTarget}`);
      copyText(target.value);
    });
  });

  els.copyAll.addEventListener("click", () => {
    if (state.selected) copyText(allText(state.selected));
  });

  els.resetFilters.addEventListener("click", () => {
    state.query = "巨乳";
    state.creator = "all";
    state.duration = "all";
    state.rate = "all";
    els.genreSearch.value = state.query;
    els.creatorFilter.value = "all";
    els.durationFilter.value = "all";
    els.rateFilter.value = "all";
    document.querySelectorAll(".chip").forEach((chip) => chip.classList.toggle("active", chip.dataset.chip === "巨乳"));
    applyFilters();
  });
}

async function boot() {
  const response = await fetch(window.AFFILIATE_COPY_DESK_DATA_URL || "./myfans_affiliate_content_200.json");
  state.rows = await response.json();
  state.rows.sort((a, b) => Number(a.index) - Number(b.index));
  els.genreSearch.value = state.query;
  fillFilters();
  bindEvents();
  applyFilters();
}

boot().catch((error) => {
  els.resultSummary.textContent = "読み込み失敗";
  els.resultList.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
});
