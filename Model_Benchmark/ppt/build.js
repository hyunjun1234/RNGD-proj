/* Furiosa RNGD 코드 생성 모델 벤치마크 — 방법·과정·결과 덱 (16:9)
 * Design.md (Brandlogy) 준수. 테스트 번호 체계 일관화: 테스트 1~5.
 * 로고 미제공 → 우측 상단 비움. */
const pptx = new (require("pptxgenjs"))();
pptx.defineLayout({ name: "W", width: 13.333, height: 7.5 });
pptx.layout = "W";
pptx.author = "RNGD Benchmark";
const TOTAL = 16;

const F = {
  black: "Paperlogy 9 Black", xbold: "Paperlogy 8 ExtraBold",
  bold: "Paperlogy 7 Bold", semi: "Paperlogy 6 SemiBold",
  med: "Paperlogy 5 Medium", reg: "Paperlogy 4 Regular",
};
const C = {
  ink: "222222", ink2: "45515e", mut: "8e8e93",
  blue: "1456f0", blue2: "3b82f6", blue3: "60a5fa", blueLt: "bfdbfe",
  pink: "ea5ec1", white: "ffffff", border: "f2f3f5", border2: "e5e7eb",
  bg2: "f0f0f0", dark: "181e25", okBg: "e8ffea", ok: "16a34a",
  codeTx: "e5e9ef", codeMut: "8ea0b5", codeAc: "5fc6ff",
};
const shStd = () => ({ type: "outer", color: "000000", opacity: 0.08, blur: 6, offset: 2, angle: 90 });
const shGlow = () => ({ type: "outer", color: "2c1e74", opacity: 0.16, blur: 15, offset: 0, angle: 90 });
const M = 0.5, CW = 13.333 - 2 * M;
const ACS = [C.blue, C.blue2, C.blue3, C.pink];

function frame(s, chapter, page, source) {
  s.background = { color: C.white };
  s.addText(chapter.toUpperCase(), {
    x: M, y: 0.4, w: 9, h: 0.3, margin: 0, fontFace: F.semi, fontSize: 12, color: C.mut, charSpacing: 0.8,
  });
  s.addText(`${page} / ${TOTAL}`, {
    x: M, y: 7.05, w: 3, h: 0.25, margin: 0, fontFace: F.med, fontSize: 10, color: C.mut,
  });
  s.addText(source, {
    x: 13.333 - M - 8, y: 7.05, w: 8, h: 0.25, margin: 0,
    fontFace: F.reg, fontSize: 9.5, color: C.mut, align: "right",
  });
}
function title(s, head, sub) {
  s.addText(head, {
    x: M, y: 1.0, w: CW, h: 0.7, margin: 0,
    fontFace: F.bold, fontSize: 31, color: C.ink, charSpacing: -0.6, lineSpacingMultiple: 1.18,
  });
  s.addText(sub, {
    x: M, y: 1.73, w: CW, h: 0.4, margin: 0,
    fontFace: F.med, fontSize: 15, color: C.ink2, lineSpacingMultiple: 1.4,
  });
}
function card(s, x, y, w, h, opt = {}) {
  s.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: opt.r || 0.13,
    fill: { color: opt.fill || C.white },
    line: opt.line === null ? { type: "none" } : { color: opt.line || C.border, width: 1 },
    shadow: opt.shadow,
  });
}
function tag(s, x, y, text, fill, txtColor, fs) {
  const w = 0.26 + text.length * 0.092;
  s.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.28, rectRadius: 0.14, fill: { color: fill }, line: { type: "none" },
  });
  s.addText(text, {
    x, y, w, h: 0.28, margin: 0, align: "center", valign: "middle",
    fontFace: F.semi, fontSize: fs || 9.5, color: txtColor || C.white,
  });
  return w;
}
function accent(s, x, y, h, color) {
  s.addShape(pptx.ShapeType.roundRect, { x, y, w: 0.07, h, rectRadius: 0.03, fill: { color }, line: { type: "none" } });
}
function codeCard(s, x, y, w, h, label, lines, fs) {
  s.addShape(pptx.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.1, fill: { color: C.dark }, line: { type: "none" }, shadow: shStd() });
  let ty = y + 0.16;
  if (label) {
    s.addText(label, { x: x + 0.24, y: ty, w: w - 0.48, h: 0.24, margin: 0, fontFace: F.semi, fontSize: 10, color: C.codeMut });
    ty += 0.32;
  }
  s.addText(lines.map((ln) => ({
    text: ln.t, options: { fontFace: F.reg, fontSize: fs || 10, color: ln.c || C.codeTx, breakLine: true },
  })), { x: x + 0.24, y: ty, w: w - 0.48, h: y + h - ty - 0.14, margin: 0, lineSpacingMultiple: 1.3, valign: "top" });
}
// 방법 스트립: 무엇을 / 입력 / 출력·분석 3카드
function methodStrip(s, y, items) {
  const h = 1.2, w = (CW - 2 * 0.2) / 3;
  items.forEach(([lab, txt, ac], i) => {
    const x = M + i * (w + 0.2);
    card(s, x, y, w, h, { shadow: shStd() });
    tag(s, x + 0.2, y + 0.16, lab, ac);
    s.addText(txt, {
      x: x + 0.2, y: y + 0.5, w: w - 0.4, h: h - 0.62, margin: 0,
      fontFace: F.reg, fontSize: 9.8, color: C.ink2, lineSpacingMultiple: 1.34,
    });
  });
}
function resultLabel(s, y) {
  s.addText("결과", { x: M, y, w: 2, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 13, color: C.blue });
}

/* ===================== 1 — Cover ===================== */
(() => {
  const s = pptx.addSlide();
  s.background = { color: C.white };
  s.addText("FURIOSA RNGD · 2026.05", {
    x: M, y: 0.55, w: 8, h: 0.3, margin: 0, fontFace: F.semi, fontSize: 12, color: C.mut, charSpacing: 1,
  });
  s.addText("Furiosa RNGD\n코드 생성 모델 벤치마크", {
    x: M, y: 1.3, w: 12, h: 1.7, margin: 0, fontFace: F.bold, fontSize: 44, color: C.ink,
    charSpacing: -0.8, lineSpacingMultiple: 1.12,
  });
  s.addText("측정 기준 · 5개 테스트 방법 · 과정 · 결과 — RNGD 2-카드 환경에서 서빙 가능한 4개 모델 검증", {
    x: M, y: 3.0, w: 12, h: 0.4, margin: 0, fontFace: F.med, fontSize: 15, color: C.ink2,
  });
  const hx = M, hy = 3.7, hw = 12.333, hh = 1.75;
  s.addShape(pptx.ShapeType.roundRect, { x: hx, y: hy, w: hw, h: hh, rectRadius: 0.22, fill: { color: C.blue }, line: { type: "none" }, shadow: shGlow() });
  s.addShape(pptx.ShapeType.roundRect, { x: hx + 0.4, y: hy + 0.3, w: 1.16, h: 0.32, rectRadius: 0.16, fill: { color: C.white }, line: { type: "none" } });
  s.addText("핵심 결론", { x: hx + 0.4, y: hy + 0.3, w: 1.16, h: 0.32, margin: 0, align: "center", valign: "middle", fontFace: F.semi, fontSize: 10, color: C.blue });
  s.addText([
    { text: "코드 생성 후보 = ", options: { fontFace: F.med, color: "dbe6ff" } },
    { text: "Llama-3.1-8B-Instruct", options: { fontFace: F.bold, color: C.white } },
  ], { x: hx + 0.4, y: hy + 0.64, w: hw - 0.8, h: 0.6, margin: 0, fontSize: 26 });
  s.addText("단일 55 tok/s · 동시성 c128까지 요청 실패 0 · RNGD 1카드 — 단, 강력 후보 32B·70B는 4카드 필요로 제외돼 모델 간 비교는 불성립", {
    x: hx + 0.4, y: hy + 1.22, w: hw - 0.8, h: 0.36, margin: 0, fontFace: F.med, fontSize: 11, color: "dbe6ff",
  });
  const chips = [["측정 테스트", "5종", "속도·동시성·serve옵션·SWE-bench·임베딩"], ["측정 모델", "4 / 7종", "2카드 서빙 가능 모델만"], ["자동화", "1 YAML", "모델 추가 시 전 과정 자동"]];
  const cw = (12.333 - 2 * 0.2) / 3;
  chips.forEach(([l, n, d], i) => {
    const x = M + i * (cw + 0.2);
    card(s, x, 5.68, cw, 1.12, { shadow: shStd() });
    s.addText(l, { x: x + 0.22, y: 5.82, w: cw - 0.44, h: 0.24, margin: 0, fontFace: F.semi, fontSize: 11, color: C.mut });
    s.addText(n, { x: x + 0.22, y: 6.02, w: cw - 0.44, h: 0.42, margin: 0, fontFace: F.bold, fontSize: 22, color: C.blue });
    s.addText(d, { x: x + 0.22, y: 6.47, w: cw - 0.44, h: 0.24, margin: 0, fontFace: F.reg, fontSize: 9, color: C.ink2 });
  });
  s.addText("furiosa-llm 2026.2.0 · RNGD npu0/npu1 (firmware 2026.2.0)", {
    x: 13.333 - M - 8, y: 7.05, w: 8, h: 0.25, margin: 0, fontFace: F.reg, fontSize: 9.5, color: C.mut, align: "right",
  });
})();

/* ===================== 2 — 검증 목표 & 평가 기준 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Objective", 2, "");
  title(s, "무엇을, 어떤 기준으로 검증했나",
    "RNGD prebuilt 모델 중 코드 생성에 가장 적합한 모델을 4개 축으로 평가");
  const gy = 2.39, gh = 1.05;
  card(s, M, gy, 12.333, gh, { fill: C.blue, line: null, r: 0.16, shadow: shGlow() });
  s.addText("검증 목표", { x: M + 0.35, y: gy + 0.16, w: 3, h: 0.26, margin: 0, fontFace: F.semi, fontSize: 11, color: "dbe6ff" });
  s.addText("Furiosa RNGD에서 제공되는 prebuilt 모델을 대상으로 코드 생성 작업에 가장 적합한 모델을 가려내고, 그 판단 근거를 정량 측정으로 확보한다.", {
    x: M + 0.35, y: gy + 0.42, w: 11.6, h: 0.5, margin: 0, fontFace: F.med, fontSize: 13.5, color: C.white, lineSpacingMultiple: 1.35,
  });
  const crit = [
    ["속도", "토큰 생성 속도", "단일 요청에서 첫 토큰 지연(TTFT)과 초당 생성 토큰 수(tok/s)를 측정", "테스트 1", C.blue],
    ["동시성·배치", "동시 접속 확장성", "동시 요청을 늘리며 합산 처리량·요청당 지연·실패율의 변화를 측정", "테스트 2 · 3", C.blue2],
    ["정확도", "SWE-bench", "실제 GitHub 이슈를 코드 패치로 해결하는 정확도를 테스트 통과로 채점", "테스트 4", C.blue3],
    ["환경", "서빙·자동화", "furiosa-llm 서빙 구성과 신규 모델 자동 분석 파이프라인 구축", "테스트 5 · 전반", C.pink],
  ];
  const cy = gy + gh + 0.2, ch = 6.85 - cy, cw = (12.333 - 3 * 0.2) / 4;
  crit.forEach(([tg, ti, d, task, ac], i) => {
    const x = M + i * (cw + 0.2);
    card(s, x, cy, cw, ch, { shadow: shStd() });
    accent(s, x, cy + 0.24, 0.42, ac);
    s.addText(`0${i + 1}`, { x: x + 0.24, y: cy + 0.22, w: cw - 0.4, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 15, color: ac });
    s.addText(ti, { x: x + 0.24, y: cy + 0.62, w: cw - 0.44, h: 0.34, margin: 0, fontFace: F.bold, fontSize: 15, color: C.ink });
    s.addText(tg, { x: x + 0.24, y: cy + 0.96, w: cw - 0.44, h: 0.26, margin: 0, fontFace: F.semi, fontSize: 10.5, color: ac });
    s.addText(d, { x: x + 0.24, y: cy + 1.34, w: cw - 0.46, h: ch - 2.05, margin: 0, fontFace: F.reg, fontSize: 11, color: C.ink2, lineSpacingMultiple: 1.5 });
    s.addShape(pptx.ShapeType.line, { x: x + 0.24, y: cy + ch - 0.66, w: cw - 0.48, h: 0, line: { color: C.border, width: 1 } });
    s.addText(`해당 테스트 · ${task}`, { x: x + 0.24, y: cy + ch - 0.54, w: cw - 0.46, h: 0.42, margin: 0, fontFace: F.semi, fontSize: 9.5, color: ac });
  });
})();

/* ===================== 3 — 측정 환경 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Environment", 3, "");
  title(s, "측정 환경 — furiosa-llm OpenAI 호환 서버",
    "vLLM은 RNGD에 직접 붙지 않음 → furiosa-llm이 vLLM 호환 OpenAI API를 제공");
  const fy = 2.55, fh = 1.7;
  const boxes = [
    ["측정 클라이언트", "httpx 비동기\n/v1/chat/completions 호출", C.blue],
    ["furiosa-llm serve", "OpenAI 호환 API 서버\n(vLLM과 동일 스펙)", C.blue2],
    ["RNGD NPU", "prebuilt 아티팩트 실행\nnpu0 / npu1", C.blue3],
  ];
  const bw = 3.5, gap = (12.333 - 3 * bw) / 2;
  boxes.forEach(([t, d, ac], i) => {
    const x = M + i * (bw + gap);
    card(s, x, fy, bw, fh, { shadow: shStd() });
    accent(s, x, fy + 0.26, fh - 0.52, ac);
    s.addText(t, { x: x + 0.3, y: fy + 0.26, w: bw - 0.5, h: 0.36, margin: 0, fontFace: F.bold, fontSize: 15, color: C.ink });
    s.addText(d, { x: x + 0.3, y: fy + 0.66, w: bw - 0.5, h: fh - 0.9, margin: 0, fontFace: F.reg, fontSize: 11, color: C.ink2, lineSpacingMultiple: 1.4 });
    if (i < 2) s.addText("→", { x: x + bw, y: fy, w: gap, h: fh, margin: 0, align: "center", valign: "middle", fontFace: F.bold, fontSize: 24, color: C.mut });
  });
  const dy = fy + fh + 0.22, dh = 6.85 - dy;
  const items = [
    ["서빙", "furiosa-llm serve", "각 모델을 OpenAI 호환 서버로 기동. 측정 도구는 vLLM과 동일한 /v1 endpoint를 그대로 사용."],
    ["측정", "스트리밍 클라이언트", "응답을 토큰 단위 스트림으로 받아 TTFT·토큰 간 지연을 실측. 동시 요청은 비동기로 발생."],
    ["채점", "Docker harness", "SWE-bench 채점에만 Docker 사용 — 인스턴스별 격리 컨테이너에서 테스트 실행."],
  ];
  const iw = (12.333 - 2 * 0.2) / 3;
  items.forEach(([tg, ti, d], i) => {
    const x = M + i * (iw + 0.2);
    card(s, x, dy, iw, dh, { shadow: shStd() });
    tag(s, x + 0.24, dy + 0.22, tg, [C.blue, C.blue2, C.pink][i]);
    s.addText(ti, { x: x + 0.24, y: dy + 0.58, w: iw - 0.46, h: 0.32, margin: 0, fontFace: F.bold, fontSize: 13.5, color: C.ink });
    s.addText(d, { x: x + 0.24, y: dy + 0.92, w: iw - 0.46, h: dh - 1.1, margin: 0, fontFace: F.reg, fontSize: 10.5, color: C.ink2, lineSpacingMultiple: 1.45 });
  });
})();

/* ===================== 4 — 측정 대상 & 하드웨어 제약 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Targets", 4, "출처: 각 모델 artifact.json · model.parallel_config");
  title(s, "7종 중 4종만 2-카드에서 측정 가능",
    "prebuilt 아티팩트의 tensor-parallel 크기가 필요 NPU 수를 고정한다");
  const cx = M, cy = 2.39, cw = 7.5, ch = 4.46;
  card(s, cx, cy, cw, ch, { shadow: shStd() });
  s.addText("모델별 필요 PE (RNGD 1카드 = 8 PE)", { x: cx + 0.25, y: cy + 0.18, w: cw - 0.5, h: 0.3, margin: 0, fontFace: F.semi, fontSize: 14, color: C.ink });
  const labels = ["Qwen2.5-0.5B", "Llama-3.1-8B", "Qwen3-Embed-8B", "Qwen3-Rerank-8B", "Qwen3-32B-FP8", "EXAONE-4.0-32B", "Llama-3.3-70B"];
  s.addChart(pptx.ChartType.bar, [{ name: "필요 PE", labels, values: [4, 8, 8, 8, 32, 32, 32] }], {
    x: cx + 0.1, y: cy + 0.55, w: cw - 0.3, h: ch - 1.0, barDir: "bar",
    chartColors: [C.blue, C.blue, C.blue, C.blue, C.pink, C.pink, C.pink],
    valAxisMinVal: 0, valAxisMaxVal: 40,
    showValue: true, dataLabelFontSize: 9.5, dataLabelColor: C.ink, dataLabelFontFace: F.semi, dataLabelPosition: "outEnd",
    catAxisLabelFontFace: F.med, catAxisLabelFontSize: 9.5, catAxisLabelColor: C.ink2,
    valAxisLabelFontFace: F.reg, valAxisLabelFontSize: 9, valAxisLabelColor: C.mut,
    valAxisLineColor: C.border2, catAxisLineColor: C.border2,
    valGridLine: { style: "solid", color: C.border2, size: 0.5 }, showLegend: false,
    chartArea: { fill: { color: C.white } },
  });
  s.addText("파랑 = 2카드(16 PE)로 측정 가능 · 분홍 = 4카드 필요 → 측정 불가", { x: cx + 0.25, y: cy + ch - 0.36, w: cw - 0.5, h: 0.26, margin: 0, fontFace: F.reg, fontSize: 9, color: C.mut });
  const rx = M + cw + 0.24, rw = 12.333 - cw - 0.24;
  const rows = [
    ["측정 대상 4종", "Qwen2.5-0.5B · Llama-3.1-8B · Qwen3-Embedding-8B · Qwen3-Reranker-8B — 모두 1카드(≤8 PE)", C.blue],
    ["측정 제외 3종", "Qwen3-32B-FP8 · EXAONE-4.0-32B-FP8 · Llama-3.3-70B — 아티팩트가 tp=32(4카드)로 컴파일", C.pink],
    ["코드 생성 후보", "측정 가능 생성 모델은 Llama-3.1-8B 단독 (0.5B는 검증용) → 모델 간 비교 불성립", C.blue3],
  ];
  const rh = (4.46 - 2 * 0.18) / 3;
  rows.forEach(([t, d, ac], i) => {
    const y = cy + i * (rh + 0.18);
    card(s, rx, y, rw, rh, { shadow: shStd() });
    accent(s, rx, y + 0.22, rh - 0.44, ac);
    s.addText(t, { x: rx + 0.28, y: y + 0.2, w: rw - 0.5, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 14, color: C.ink });
    s.addText(d, { x: rx + 0.28, y: y + 0.54, w: rw - 0.5, h: rh - 0.72, margin: 0, fontFace: F.reg, fontSize: 10.5, color: C.ink2, lineSpacingMultiple: 1.35 });
  });
})();

/* ===================== 5 — 자동화 파이프라인 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Pipeline", 5, "");
  title(s, "측정 파이프라인 — 모델 추가만으로 자동화",
    "configs/models.yaml에 모델을 등록하면 서버 기동부터 리포트까지 자동 실행");
  const steps = [
    ["01", "모델 정의", "models.yaml에 모델 id·역할·serve 옵션 등록"],
    ["02", "서버 기동", "furiosa-llm serve 실행, 헬스체크 통과까지 대기"],
    ["03", "테스트 실행", "테스트 1~5를 순차 측정"],
    ["04", "결과 저장", "results/<모델>/<테스트>/*.json 자동 기록"],
    ["05", "집계·리포트", "analyze · report로 비교표·종합 리포트 생성"],
  ];
  const sy = 2.55, sh = 1.95, sw = (12.333 - 4 * 0.22) / 5;
  steps.forEach(([n, t, d], i) => {
    const x = M + i * (sw + 0.22);
    const feat = i >= 1 && i <= 3;
    card(s, x, sy, sw, sh, { shadow: shStd() });
    s.addShape(pptx.ShapeType.ellipse, { x: x + 0.24, y: sy + 0.24, w: 0.5, h: 0.5, fill: { color: feat ? C.blue : C.blue3 }, line: { type: "none" } });
    s.addText(n, { x: x + 0.24, y: sy + 0.24, w: 0.5, h: 0.5, margin: 0, align: "center", valign: "middle", fontFace: F.bold, fontSize: 13, color: C.white });
    s.addText(t, { x: x + 0.22, y: sy + 0.86, w: sw - 0.4, h: 0.32, margin: 0, fontFace: F.bold, fontSize: 13.5, color: C.ink });
    s.addText(d, { x: x + 0.22, y: sy + 1.2, w: sw - 0.42, h: sh - 1.36, margin: 0, fontFace: F.reg, fontSize: 9.8, color: C.ink2, lineSpacingMultiple: 1.4 });
    if (i < 4) s.addText("›", { x: x + sw - 0.04, y: sy, w: 0.3, h: sh, margin: 0, align: "center", valign: "middle", fontFace: F.bold, fontSize: 20, color: C.mut });
  });
  const by = sy + sh + 0.22, bh = 6.85 - by;
  card(s, M, by, 12.333, bh, { fill: C.bg2, line: null, shadow: shStd() });
  accent(s, M + 0.02, by + 0.24, bh - 0.48, C.blue);
  s.addText("02–04 단계는 모델마다 반복", { x: M + 0.32, y: by + 0.22, w: 11.6, h: 0.32, margin: 0, fontFace: F.bold, fontSize: 14, color: C.ink });
  s.addText("한 모델의 서버를 띄워 테스트 1·2·4를 측정하고, 테스트 3(memsweep)은 serve 옵션을 바꿔 서버를 재기동하며 측정한다. 측정이 끝나면 서버를 내리고 다음 모델로 — 7종이든 새 모델이든 동일 흐름. 측정 도구 코드는 수정 불필요, models.yaml만 바꾸면 된다.", {
    x: M + 0.32, y: by + 0.6, w: 11.7, h: bh - 0.8, margin: 0, fontFace: F.reg, fontSize: 11, color: C.ink2, lineSpacingMultiple: 1.5,
  });
})();

/* ===================== 6 — 측정 테스트 5종 한눈에 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test Overview", 6, "");
  title(s, "측정 테스트 5종 한눈에",
    "각 모델에 대해 아래 5개 테스트를 순차 수행 — 이후 슬라이드는 테스트 번호 순");
  const tests = [
    ["1", "토큰 생성 속도", "단일 요청 스트리밍으로 첫 토큰 지연·생성 속도 측정", "지표 TTFT · tok/s", C.blue],
    ["2", "동시성 스케일링", "동시 요청을 1→128로 늘리며 처리량·지연 변화 측정", "지표 합산 TPS · 실패율", C.blue2],
    ["3", "serve 옵션", "serve 인자를 바꿔가며 처리량 영향 측정 (memsweep)", "지표 조합별 합산 TPS", C.blue3],
    ["4", "SWE-bench", "실제 GitHub 이슈를 코드 패치로 해결, 테스트 통과 채점", "지표 resolved %", C.pink],
    ["5", "임베딩·리랭커", "검색 보조 모델의 배치별 처리량 측정", "지표 inputs/s", C.mut],
  ];
  const cy = 2.39, ch = 4.46, cw = (12.333 - 4 * 0.18) / 5;
  tests.forEach(([n, name, d, metric, ac], i) => {
    const x = M + i * (cw + 0.18);
    card(s, x, cy, cw, ch, { shadow: shStd() });
    s.addShape(pptx.ShapeType.roundRect, { x, y: cy, w: cw, h: 0.62, rectRadius: 0.13, fill: { color: ac }, line: { type: "none" } });
    s.addShape(pptx.ShapeType.rect, { x, y: cy + 0.32, w: cw, h: 0.3, fill: { color: ac }, line: { type: "none" } });
    s.addText(`테스트 ${n}`, { x: x + 0.2, y: cy, w: cw - 0.4, h: 0.62, margin: 0, valign: "middle", fontFace: F.bold, fontSize: 14, color: C.white });
    s.addText(name, { x: x + 0.2, y: cy + 0.8, w: cw - 0.4, h: 0.6, margin: 0, fontFace: F.bold, fontSize: 14, color: C.ink, lineSpacingMultiple: 1.15 });
    s.addText(d, { x: x + 0.2, y: cy + 1.5, w: cw - 0.4, h: 1.7, margin: 0, fontFace: F.reg, fontSize: 10, color: C.ink2, lineSpacingMultiple: 1.45 });
    s.addShape(pptx.ShapeType.line, { x: x + 0.2, y: cy + ch - 0.62, w: cw - 0.4, h: 0, line: { color: C.border, width: 1 } });
    s.addText(metric, { x: x + 0.2, y: cy + ch - 0.5, w: cw - 0.4, h: 0.4, margin: 0, fontFace: F.semi, fontSize: 9.3, color: ac, lineSpacingMultiple: 1.25 });
  });
})();

/* ===================== 7 — 테스트 1: 토큰 생성 속도 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 1 · Speed", 7, "출처: bench/results · tps task (concurrency=1, 50 req)");
  title(s, "테스트 1 — 토큰 생성 속도",
    "단일 요청 스트리밍으로 첫 토큰 지연(TTFT)·생성 속도(tok/s) 측정");
  methodStrip(s, 2.39, [
    ["무엇을", "동시 사용자 1명일 때 체감 속도 — 코드 자동완성·대화형 보조의 핵심 지표.", C.blue],
    ["입력", "고정 프롬프트를 /v1/chat/completions에 스트리밍 요청. max_tokens 256, 워밍업 5 + 측정 50회.", C.blue],
    ["출력·분석", "요청별 TTFT·ITL(토큰 간 간격)·출력 tok/s를 p50/p95로 집계.", C.blue],
  ]);
  resultLabel(s, 3.78);
  const ry = 4.12, rh = 6.85 - ry;
  const kpis = [
    ["Llama-3.1-8B-Instruct", "55.2", "tok/s", "TTFT 32 ms", "ITL 18.2 ms", "코드 생성 후보 · context 128K", true],
    ["Qwen2.5-0.5B-Instruct", "85.3", "tok/s", "TTFT 31 ms", "ITL 11.8 ms", "파이프라인 검증용 (smoke)", false],
  ];
  const kw = (12.333 - 0.24) / 2;
  kpis.forEach(([name, num, unit, m1, m2, note, feat], i) => {
    const x = M + i * (kw + 0.24);
    card(s, x, ry, kw, rh, { fill: feat ? C.blue : C.white, line: feat ? null : C.border, shadow: feat ? shGlow() : shStd(), r: feat ? 0.18 : 0.13 });
    const fg = feat ? C.white : C.ink, fg2 = feat ? "dbe6ff" : C.ink2;
    s.addText(name, { x: x + 0.32, y: ry + 0.24, w: kw - 0.64, h: 0.32, margin: 0, fontFace: F.semi, fontSize: 14, color: feat ? "dbe6ff" : C.mut });
    s.addText([
      { text: num, options: { fontFace: F.bold, fontSize: 44, color: feat ? C.white : C.blue } },
      { text: "  " + unit, options: { fontFace: F.semi, fontSize: 16, color: fg2 } },
    ], { x: x + 0.32, y: ry + 0.62, w: kw - 0.64, h: 0.78, margin: 0 });
    s.addText("출력 토큰 처리량 (단일 요청)", { x: x + 0.32, y: ry + 1.46, w: kw - 0.64, h: 0.26, margin: 0, fontFace: F.med, fontSize: 11, color: fg2 });
    s.addShape(pptx.ShapeType.line, { x: x + 0.32, y: ry + 1.8, w: kw - 0.64, h: 0, line: { color: feat ? "3b6fe0" : C.border, width: 1 } });
    s.addText([
      { text: m1 + "      ", options: { fontFace: F.bold, fontSize: 14, color: fg } },
      { text: m2, options: { fontFace: F.bold, fontSize: 14, color: fg } },
    ], { x: x + 0.32, y: ry + 1.94, w: kw - 0.64, h: 0.34, margin: 0 });
    s.addText(note, { x: x + 0.32, y: ry + 2.32, w: kw - 0.64, h: 0.3, margin: 0, fontFace: F.reg, fontSize: 10, color: fg2 });
  });
})();

/* ===================== 8 — 테스트 2: 동시성 스케일링 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 2 · Concurrency", 8, "출처: bench/results · sweep task (Llama-3.1-8B, prompt 1024)");
  title(s, "테스트 2 — 동시성 스케일링",
    "동시 요청을 1→128로 늘리며 합산 처리량·지연 변화 측정");
  methodStrip(s, 2.39, [
    ["무엇을", "동시 접속자 수에 따른 처리량·지연 — 서버 운영 조건 산정의 근거.", C.blue2],
    ["입력", "동시성 {1·2·4·8·16·32·64·128} × 프롬프트 길이 {256·1024·4096} 매트릭스.", C.blue2],
    ["출력·분석", "셀별 합산 처리량·요청당 속도·TTFT·실패 수 → 효율 배치점 도출.", C.blue2],
  ]);
  resultLabel(s, 3.78);
  const ry = 4.12, rh = 6.85 - ry, chw = 7.4;
  card(s, M, ry, chw, rh, { shadow: shStd() });
  s.addText("동시성별 합산 처리량 (tok/s) — Llama-3.1-8B", { x: M + 0.25, y: ry + 0.14, w: chw - 0.5, h: 0.28, margin: 0, fontFace: F.semi, fontSize: 13, color: C.ink });
  s.addChart(pptx.ChartType.line, [
    { name: "합산 TPS", labels: ["1", "2", "4", "8", "16", "32", "64", "128"], values: [52, 101, 191, 344, 649, 1090, 1636, 2197] },
  ], {
    x: M + 0.1, y: ry + 0.46, w: chw - 0.3, h: rh - 0.86,
    chartColors: [C.blue], lineSize: 2.5, lineSmooth: true,
    showValue: true, dataLabelFontSize: 8, dataLabelFontFace: F.semi, dataLabelColor: C.ink, dataLabelPosition: "t",
    valAxisMinVal: 0, valAxisMaxVal: 2600,
    catAxisLabelFontFace: F.med, catAxisLabelFontSize: 9, catAxisLabelColor: C.ink2,
    valAxisLabelFontFace: F.reg, valAxisLabelFontSize: 8.5, valAxisLabelColor: C.mut,
    valGridLine: { style: "solid", color: C.border2, size: 0.5 },
    valAxisLineColor: C.border2, catAxisLineColor: C.border2, showLegend: false,
  });
  const rx = M + chw + 0.24, rw = 12.333 - chw - 0.24;
  const cards = [
    ["스케일링", "처리량 약 20배", "c1 52 → c128 2,197 tok/s. 동시성을 올릴수록 합산 처리량 비례 이상 증가.", C.blue],
    ["지연", "TTFT 1.8s @c128", "첫 토큰 지연 0.04→1.85s, 요청당 속도 54→18 tok/s. 전 구간 실패 0건.", C.blue3],
    ["판단", "효율 배치점 c32", "체감 속도(35 tok/s↑) 유지하는 1카드 권장 상한은 동시 32명.", C.pink],
  ];
  const ih = (rh - 2 * 0.16) / 3;
  cards.forEach(([tg, ti, d, ac], i) => {
    const y = ry + i * (ih + 0.16);
    card(s, rx, y, rw, ih, { shadow: shStd() });
    tag(s, rx + 0.2, y + 0.16, tg, ac);
    s.addText(ti, { x: rx + 0.2, y: y + 0.48, w: rw - 0.4, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 13, color: C.ink });
    s.addText(d, { x: rx + 0.2, y: y + 0.78, w: rw - 0.4, h: ih - 0.9, margin: 0, fontFace: F.reg, fontSize: 9.8, color: C.ink2, lineSpacingMultiple: 1.32 });
  });
})();

/* ===================== 9 — 테스트 3: serve 옵션 (memsweep) ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 3 · Serve Options", 9, "출처: bench/results · memsweep task (Llama-3.1-8B)");
  title(s, "테스트 3 — serve 옵션 튜닝 (memsweep)",
    "서버 기동 옵션을 한 번에 하나씩 바꿔(OFAT) 처리량 영향 측정");
  methodStrip(s, 2.39, [
    ["무엇을", "KV cache·배치 관련 serve 옵션이 처리량에 주는 영향.", C.blue3],
    ["입력", "baseline + max-model-len·max-batch-size·max-num-batched-tokens 한 축씩 변경, 조합마다 서버 재기동.", C.blue3],
    ["출력·분석", "조합별 합산 처리량 비교 → 어떤 옵션이 유의미한지 판단.", C.blue3],
  ]);
  resultLabel(s, 3.78);
  const ry = 4.12, rh = 6.85 - ry, chw = 7.4;
  card(s, M, ry, chw, rh, { shadow: shStd() });
  s.addText("serve 옵션 조합별 합산 처리량 (tok/s)", { x: M + 0.25, y: ry + 0.14, w: chw - 0.5, h: 0.28, margin: 0, fontFace: F.semi, fontSize: 13, color: C.ink });
  s.addChart(pptx.ChartType.bar, [{
    name: "tok/s",
    labels: ["baseline", "max-model-len 4096", "max-model-len 16384", "max-batch-size 32", "max-num-batched 16384"],
    values: [2276, 2294, 2133, 2265, 2266],
  }], {
    x: M + 0.1, y: ry + 0.46, w: chw - 0.3, h: rh - 0.86, barDir: "bar",
    chartColors: [C.blue2], valAxisMinVal: 1800, valAxisMaxVal: 2450,
    showValue: true, dataLabelFontSize: 9, dataLabelFontFace: F.semi, dataLabelPosition: "outEnd", dataLabelColor: C.ink,
    catAxisLabelFontFace: F.med, catAxisLabelFontSize: 8.8, catAxisLabelColor: C.ink2,
    valAxisLabelFontFace: F.reg, valAxisLabelFontSize: 8.5, valAxisLabelColor: C.mut,
    valGridLine: { style: "solid", color: C.border2, size: 0.5 },
    valAxisLineColor: C.border2, catAxisLineColor: C.border2, showLegend: false,
  });
  const rx = M + chw + 0.24, rw = 12.333 - chw - 0.24;
  card(s, rx, ry, rw, rh, { shadow: shStd() });
  accent(s, rx, ry + 0.26, rh - 0.52, C.pink);
  s.addText("튜닝 효과 미미", { x: rx + 0.3, y: ry + 0.24, w: rw - 0.55, h: 0.34, margin: 0, fontFace: F.bold, fontSize: 16, color: C.ink });
  s.addText("Llama-3.1-8B는 어떤 serve 옵션을 바꿔도 합산 처리량이 2,200 tok/s대(전체 범위 2,133~2,294, 편차 ~7%)에서 거의 변하지 않는다. KV cache·배치 한도 옵션을 손댈 실익이 없으며 기본값 그대로 서빙하면 된다 — 운영 시 튜닝 부담이 없다는 점은 장점.", {
    x: rx + 0.3, y: ry + 0.66, w: rw - 0.6, h: rh - 0.9, margin: 0, fontFace: F.reg, fontSize: 11, color: C.ink2, lineSpacingMultiple: 1.5,
  });
})();

/* ===================== 10 — 테스트 4 SWE-bench ①: 정의 & 종류 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 4 · SWE-bench ①", 10, "출처: SWE-bench (Princeton NLP)");
  title(s, "테스트 4 — SWE-bench ①: 정의 & 종류",
    "GitHub 이슈를 패치로 해결하고 실제 repo 테스트 통과 여부로 채점하는 벤치마크");
  const lw = 5.4, ly = 2.39, lh = 4.46;
  card(s, M, ly, lw, lh, { shadow: shStd() });
  s.addText("채점 방식", { x: M + 0.26, y: ly + 0.2, w: lw - 0.5, h: 0.3, margin: 0, fontFace: F.semi, fontSize: 13.5, color: C.ink });
  const flow = [
    ["입력", "GitHub 이슈 본문 + 해당 시점 repo 코드", C.blue],
    ["모델 출력", "이슈를 해결하는 unified diff (패치)", C.blue2],
    ["적용", "Docker 컨테이너에서 repo에 패치 적용", C.blue3],
    ["채점", "테스트 실행 — FAIL→PASS 통과 시 resolved", C.pink],
  ];
  const fh = (lh - 0.6) / 4;
  flow.forEach(([t, d, ac], i) => {
    const y = ly + 0.6 + i * fh;
    s.addShape(pptx.ShapeType.ellipse, { x: M + 0.28, y: y + 0.16, w: 0.36, h: 0.36, fill: { color: ac }, line: { type: "none" } });
    s.addText(`${i + 1}`, { x: M + 0.28, y: y + 0.16, w: 0.36, h: 0.36, margin: 0, align: "center", valign: "middle", fontFace: F.bold, fontSize: 11, color: C.white });
    s.addText(t, { x: M + 0.8, y: y + 0.12, w: lw - 1.0, h: 0.26, margin: 0, fontFace: F.bold, fontSize: 12.5, color: C.ink });
    s.addText(d, { x: M + 0.8, y: y + 0.37, w: lw - 1.05, h: fh - 0.42, margin: 0, fontFace: F.reg, fontSize: 10, color: C.ink2, lineSpacingMultiple: 1.3 });
    if (i < 3) s.addText("↓", { x: M + 0.36, y: y + 0.5, w: 0.2, h: fh - 0.34, margin: 0, align: "center", fontFace: F.bold, fontSize: 11, color: C.border2 });
  });
  const rx = M + lw + 0.24, rw = 12.333 - lw - 0.24;
  card(s, rx, ly, rw, 2.66, { shadow: shStd() });
  s.addText("데이터셋 종류", { x: rx + 0.26, y: ly + 0.18, w: rw - 0.5, h: 0.28, margin: 0, fontFace: F.semi, fontSize: 13, color: C.ink });
  const ds = [
    ["SWE-bench (full)", "2,294건 · 원본"],
    ["SWE-bench Lite", "300건 · 저비용 평가용 subset"],
    ["SWE-bench Verified", "500건 · 사람 검증, 신뢰도 최상"],
    ["SWE-bench Multimodal", "517건 · 시각 요소 포함"],
  ];
  ds.forEach(([a, b], i) => {
    const y = ly + 0.52 + i * 0.5;
    if (i % 2 === 1) s.addShape(pptx.ShapeType.rect, { x: rx + 0.2, y, w: rw - 0.4, h: 0.5, fill: { color: "fafafa" }, line: { type: "none" } });
    s.addText(a, { x: rx + 0.32, y, w: 2.7, h: 0.5, margin: 0, valign: "middle", fontFace: F.semi, fontSize: 11, color: C.ink });
    s.addText(b, { x: rx + 3.05, y, w: rw - 3.25, h: 0.5, margin: 0, valign: "middle", fontFace: F.reg, fontSize: 10.5, color: C.ink2 });
  });
  const sy = ly + 2.66 + 0.16, sh = 6.85 - sy;
  card(s, rx, sy, rw, sh, { fill: C.blue, line: null, r: 0.16, shadow: shGlow() });
  s.addShape(pptx.ShapeType.roundRect, { x: rx + 0.28, y: sy + 0.22, w: 1.0, h: 0.3, rectRadius: 0.15, fill: { color: C.white }, line: { type: "none" } });
  s.addText("본 측정", { x: rx + 0.28, y: sy + 0.22, w: 1.0, h: 0.3, margin: 0, align: "center", valign: "middle", fontFace: F.semi, fontSize: 9.5, color: C.blue });
  s.addText("SWE-bench Lite · oracle · single-shot", { x: rx + 0.28, y: sy + 0.56, w: rw - 0.56, h: 0.32, margin: 0, fontFace: F.bold, fontSize: 14.5, color: C.white });
  s.addText("Lite 300건 중 12개 repo(astropy·django·matplotlib·sympy 등)에 고르게 50건 추출. context는 oracle(정답 파일 제공), 호출은 single-shot(1회 생성) — 에이전트 반복 없이 순수 코드 편집 능력을 본다.", {
    x: rx + 0.28, y: sy + 0.92, w: rw - 0.56, h: sh - 1.1, margin: 0, fontFace: F.med, fontSize: 10.3, color: "dbe6ff", lineSpacingMultiple: 1.42,
  });
})();

/* ===================== 11 — 테스트 4 SWE-bench ②: 환경 구축 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 4 · SWE-bench ②", 11, "docs/SWEBENCH_SETUP.md 참조");
  title(s, "테스트 4 — SWE-bench ②: 환경 구축",
    "Docker 기반 채점 — 인스턴스별 격리 컨테이너에서 repo 테스트 실행");
  const lw = 7.0, ly = 2.39;
  codeCard(s, M, ly, lw, 1.66, "① 설치", [
    { t: "$ git clone https://github.com/SWE-bench/SWE-bench.git", c: C.codeAc },
    { t: "$ cd SWE-bench && pip install -e .", c: C.codeAc },
    { t: "$ docker --version    # Docker 동작 확인", c: C.codeMut },
  ], 10.5);
  codeCard(s, M, ly + 1.82, lw, 2.64, "② 채점 실행", [
    { t: "$ python -m swebench.harness.run_evaluation \\", c: C.codeAc },
    { t: "    --dataset_name princeton-nlp/SWE-bench_Lite \\", c: C.codeTx },
    { t: "    --predictions_path predictions.jsonl \\", c: C.codeTx },
    { t: "    --max_workers 8 \\", c: C.codeTx },
    { t: "    --namespace swebench \\", c: C.codeTx },
    { t: "    --run_id my_run", c: C.codeTx },
    { t: "# --namespace swebench → prebuilt 이미지 pull", c: C.codeMut },
    { t: "# 결과: <model>.<run_id>.json (resolved 카운트)", c: C.codeMut },
  ], 10.5);
  const rx = M + lw + 0.24, rw = 12.333 - lw - 0.24;
  card(s, rx, ly, rw, 2.0, { shadow: shStd() });
  s.addText("요구사항", { x: rx + 0.26, y: ly + 0.18, w: rw - 0.5, h: 0.28, margin: 0, fontFace: F.semi, fontSize: 13, color: C.ink });
  const req = ["x86_64 Linux · Docker", "디스크 수십~120GB (인스턴스 이미지)", "Python 3.10+ · swebench 패키지"];
  req.forEach((r, i) => {
    s.addShape(pptx.ShapeType.ellipse, { x: rx + 0.3, y: ly + 0.58 + i * 0.42, w: 0.1, h: 0.1, fill: { color: C.blue }, line: { type: "none" } });
    s.addText(r, { x: rx + 0.52, y: ly + 0.46 + i * 0.42, w: rw - 0.8, h: 0.34, margin: 0, valign: "middle", fontFace: F.reg, fontSize: 10.8, color: C.ink2 });
  });
  card(s, rx, ly + 2.16, rw, 2.3, { shadow: shStd() });
  s.addText("예측 파일 (predictions.jsonl)", { x: rx + 0.26, y: ly + 2.32, w: rw - 0.5, h: 0.28, margin: 0, fontFace: F.semi, fontSize: 13, color: C.ink });
  s.addText("한 줄 = 한 인스턴스. 모델이 만든 패치를 model_patch에 담는다:", {
    x: rx + 0.26, y: ly + 2.6, w: rw - 0.5, h: 0.5, margin: 0, fontFace: F.reg, fontSize: 10, color: C.ink2, lineSpacingMultiple: 1.4,
  });
  codeCard(s, rx + 0.26, ly + 3.06, rw - 0.52, 1.2, null, [
    { t: '{"instance_id": "astropy__..."', c: C.codeTx },
    { t: ' "model_name_or_path": "8B",', c: C.codeTx },
    { t: ' "model_patch": "diff --git ..."}', c: C.codeAc },
  ], 9.5);
})();

/* ===================== 12 — 테스트 4 SWE-bench ③: 측정 방법 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 4 · SWE-bench ③", 12, "예시: astropy__astropy-12907");
  title(s, "테스트 4 — SWE-bench ③: 측정 방법",
    "oracle 프롬프트를 로컬 furiosa-llm 서버에 보내 diff를 받고 harness로 채점");
  const y = 2.39, h = 4.46, w = (12.333 - 2 * 0.22) / 3;
  card(s, M, y, w, h, { shadow: shStd() });
  tag(s, M + 0.22, y + 0.2, "입력", C.blue);
  s.addText("oracle 프롬프트", { x: M + 0.22, y: y + 0.54, w: w - 0.44, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 13, color: C.ink });
  s.addText("이슈 설명 + 수정 대상 파일 코드", { x: M + 0.22, y: y + 0.84, w: w - 0.44, h: 0.3, margin: 0, fontFace: F.reg, fontSize: 9.8, color: C.ink2 });
  codeCard(s, M + 0.22, y + 1.18, w - 0.44, h - 1.4, null, [
    { t: "<issue>", c: C.codeMut },
    { t: "separability_matrix 가", c: C.codeTx },
    { t: "nested CompoundModel 에서", c: C.codeTx },
    { t: "분리성을 잘못 계산함", c: C.codeTx },
    { t: "</issue>", c: C.codeMut },
    { t: "", c: C.codeTx },
    { t: "[start of separable.py]", c: C.codeMut },
    { t: "def _separable(transform):", c: C.codeAc },
    { t: "    ...", c: C.codeTx },
  ], 9.5);
  card(s, M + w + 0.22, y, w, h, { shadow: shStd() });
  tag(s, M + w + 0.44, y + 0.2, "출력", C.blue2);
  s.addText("모델 생성 diff", { x: M + w + 0.44, y: y + 0.54, w: w - 0.44, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 13, color: C.ink });
  s.addText("Llama-3.1-8B single-shot 응답", { x: M + w + 0.44, y: y + 0.84, w: w - 0.44, h: 0.3, margin: 0, fontFace: F.reg, fontSize: 9.8, color: C.ink2 });
  codeCard(s, M + w + 0.44, y + 1.18, w - 0.44, h - 1.4, null, [
    { t: "--- a/.../separable.py", c: C.codeMut },
    { t: "+++ b/.../separable.py", c: C.codeMut },
    { t: "@@ -304,6 +304,10 @@", c: C.codeAc },
    { t: "  elif isinstance(", c: C.codeTx },
    { t: "      transform, Compound):", c: C.codeTx },
    { t: "+   if isinstance(", c: "7ee787" },
    { t: "+       transform.left,...):", c: "7ee787" },
    { t: "+     sepleft =", c: "7ee787" },
    { t: "+       _separable(...)", c: "7ee787" },
  ], 9.5);
  card(s, M + 2 * (w + 0.22), y, w, h, { shadow: shStd() });
  tag(s, M + 2 * (w + 0.22) + 0.22, y + 0.2, "채점", C.pink);
  s.addText("Docker harness", { x: M + 2 * (w + 0.22) + 0.22, y: y + 0.54, w: w - 0.44, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 13, color: C.ink });
  s.addText("패치 적용 후 테스트 실행", { x: M + 2 * (w + 0.22) + 0.22, y: y + 0.84, w: w - 0.44, h: 0.3, margin: 0, fontFace: F.reg, fontSize: 9.8, color: C.ink2 });
  const gx = M + 2 * (w + 0.22) + 0.22, gw = w - 0.44;
  const judge = [
    ["resolved", "패치 적용 + 테스트 통과", C.ok],
    ["unresolved", "적용됐으나 테스트 미통과", C.mut],
    ["적용실패", "malformed diff — 적용 불가", C.pink],
  ];
  judge.forEach(([t, d, ac], i) => {
    const jy = y + 1.2 + i * 1.04;
    card(s, gx, jy, gw, 0.9, { fill: "fafafa", line: C.border });
    accent(s, gx, jy + 0.16, 0.58, ac);
    s.addText(t, { x: gx + 0.22, y: jy + 0.12, w: gw - 0.4, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 12, color: C.ink });
    s.addText(d, { x: gx + 0.22, y: jy + 0.42, w: gw - 0.4, h: 0.4, margin: 0, fontFace: F.reg, fontSize: 9.5, color: C.ink2, lineSpacingMultiple: 1.3 });
  });
})();

/* ===================== 13 — 테스트 4 SWE-bench ④: 결과 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 4 · SWE-bench ④", 13, "출처: SWE-bench Lite oracle 50건 · Docker harness 채점");
  title(s, "테스트 4 — SWE-bench ④: 결과",
    "Llama-3.1-8B single-shot · oracle 컨텍스트 50건 채점 결과");
  const chw = 6.4, cy = 2.39, ch = 4.46;
  card(s, M, cy, chw, ch, { shadow: shStd() });
  s.addText("채점 결과 분포 (50건)", { x: M + 0.25, y: cy + 0.16, w: chw - 0.5, h: 0.28, margin: 0, fontFace: F.semi, fontSize: 14, color: C.ink });
  s.addChart(pptx.ChartType.doughnut, [
    { name: "결과", labels: ["resolved 0", "unresolved 23", "적용실패 27"], values: [0.001, 23, 27] },
  ], {
    x: M + 0.5, y: cy + 0.55, w: chw - 1.0, h: ch - 1.3,
    chartColors: [C.ok, C.mut, C.pink], holeSize: 58,
    showValue: false, showLegend: true, legendPos: "b",
    legendFontFace: F.med, legendFontSize: 10, legendColor: C.ink2,
  });
  s.addText("repo 분포: astropy·django·matplotlib 각 5 · 기타 9개 repo — Lite 12개 repo stratified", {
    x: M + 0.25, y: cy + ch - 0.36, w: chw - 0.5, h: 0.26, margin: 0, fontFace: F.reg, fontSize: 9, color: C.mut,
  });
  const rx = M + chw + 0.24, rw = 12.333 - chw - 0.24;
  card(s, rx, cy, rw, 1.5, { shadow: shStd() });
  s.addText("resolved (테스트 통과)", { x: rx + 0.3, y: cy + 0.2, w: rw - 0.6, h: 0.26, margin: 0, fontFace: F.semi, fontSize: 12, color: C.mut });
  s.addText([
    { text: "0", options: { fontFace: F.bold, fontSize: 38, color: C.ink } },
    { text: " / 50", options: { fontFace: F.semi, fontSize: 18, color: C.mut } },
  ], { x: rx + 0.3, y: cy + 0.5, w: rw - 0.6, h: 0.7, margin: 0 });
  s.addText("8B 단발 생성으로는 SWE-bench 버그를 해결하지 못함 — 원인은 다음 슬라이드", { x: rx + 0.3, y: cy + 1.14, w: rw - 0.6, h: 0.3, margin: 0, fontFace: F.reg, fontSize: 10, color: C.ink2 });
  const inf = [
    ["27건 — 적용실패", "모델이 정확한 unified diff를 만들지 못함. diff 포맷이 무너진 비율 54%."],
    ["23건 — 미해결", "패치는 적용됐으나 테스트 미통과. 단발 8B 코드 수정 역량의 한계."],
  ];
  const ih = (4.46 - 1.5 - 0.18 - 0.16) / 2;
  inf.forEach(([t, d], i) => {
    const y = cy + 1.5 + 0.18 + i * (ih + 0.16);
    card(s, rx, y, rw, ih, { shadow: shStd() });
    accent(s, rx, y + 0.2, ih - 0.4, [C.pink, C.mut][i]);
    s.addText(t, { x: rx + 0.28, y: y + 0.2, w: rw - 0.5, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 13.5, color: C.ink });
    s.addText(d, { x: rx + 0.28, y: y + 0.52, w: rw - 0.5, h: ih - 0.7, margin: 0, fontFace: F.reg, fontSize: 10.5, color: C.ink2, lineSpacingMultiple: 1.4 });
  });
})();

/* ===================== 14 — 테스트 4 SWE-bench ⑤: 심층 분석 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 4 · SWE-bench ⑤", 14, "출처: 예측 jsonl + harness 로그 분석");
  title(s, "테스트 4 — SWE-bench ⑤: 결과 심층 분석",
    "27 적용실패·23 미해결 — 모델 한계인가, NPU 한계인가?");
  // verdict 배너
  const vy = 2.39, vh = 0.84;
  card(s, M, vy, 12.333, vh, { fill: C.blue, line: null, r: 0.16, shadow: shGlow() });
  s.addShape(pptx.ShapeType.roundRect, { x: M + 0.32, y: vy + 0.26, w: 0.92, h: 0.32, rectRadius: 0.16, fill: { color: C.white }, line: { type: "none" } });
  s.addText("결론", { x: M + 0.32, y: vy + 0.26, w: 0.92, h: 0.32, margin: 0, align: "center", valign: "middle", fontFace: F.semi, fontSize: 10, color: C.blue });
  s.addText("원인은 single-shot 8B 모델의 한계 — NPU·서빙 제약이 아니다", {
    x: M + 1.4, y: vy, w: 11.2, h: vh, margin: 0, valign: "middle", fontFace: F.bold, fontSize: 16, color: C.white,
  });
  const by = vy + vh + 0.18;            // 3.41
  const colTop = by + 0.42, colBot = 6.18;
  const lw = 5.7, rw = 12.333 - lw - 0.22, rx = M + lw + 0.22;
  // 좌: 왜 NPU 한계가 아닌가
  s.addText("왜 NPU·서빙 한계가 아닌가", { x: M + 0.04, y: by, w: lw, h: 0.32, margin: 0, fontFace: F.semi, fontSize: 13, color: C.blue });
  const ev = [
    ["8B 아티팩트 = bf16", "양자화 없음 → NPU 정밀도 손실 0"],
    ["평균 출력 698토큰", "max_tokens 4096 한도 — 절단은 27건 중 2건뿐"],
    ["context 128K", "프롬프트(5~18K 토큰) 충분히 수용 — 길이 제약 없음"],
  ];
  const eh = (colBot - colTop - 2 * 0.14) / 3;
  ev.forEach(([t, d], i) => {
    const y = colTop + i * (eh + 0.14);
    card(s, M, y, lw, eh, { shadow: shStd() });
    accent(s, M, y + 0.16, eh - 0.32, C.blue);
    s.addText(t, { x: M + 0.26, y: y + 0.13, w: lw - 0.5, h: 0.28, margin: 0, fontFace: F.bold, fontSize: 12.5, color: C.ink });
    s.addText(d, { x: M + 0.26, y: y + 0.4, w: lw - 0.5, h: eh - 0.5, margin: 0, fontFace: F.reg, fontSize: 10, color: C.ink2, lineSpacingMultiple: 1.3 });
  });
  // 우: 두 실패 유형
  s.addText("두 실패 유형 — 모두 모델 역량 문제", { x: rx + 0.04, y: by, w: rw, h: 0.32, margin: 0, fontFace: F.semi, fontSize: 13, color: C.ink });
  const types = [
    ["27 적용실패", "모델이 diff의 @@ hunk 헤더 줄 수를 잘못 계산 → patch 도구가 거부 (헤더는 +1줄 표기, 실제 본문은 2줄 추가 → 불일치).", C.pink],
    ["23 미해결", "문법이 맞는 패치가 적용됐으나 테스트 미통과 — 수정 위치·내용이 틀림. 단발 8B의 코드 추론 능력 한계.", C.mut],
  ];
  const th = (colBot - colTop - 0.16) / 2;
  types.forEach(([t, d, ac], i) => {
    const y = colTop + i * (th + 0.16);
    card(s, rx, y, rw, th, { shadow: shStd() });
    accent(s, rx, y + 0.18, th - 0.36, ac);
    s.addText(t, { x: rx + 0.3, y: y + 0.16, w: rw - 0.55, h: 0.3, margin: 0, fontFace: F.bold, fontSize: 14, color: C.ink });
    s.addText(d, { x: rx + 0.3, y: y + 0.5, w: rw - 0.58, h: th - 0.62, margin: 0, fontFace: F.reg, fontSize: 10.3, color: C.ink2, lineSpacingMultiple: 1.4 });
  });
  // 하단 결론 strip
  card(s, M, 6.32, 12.333, 0.5, { fill: C.bg2, line: null });
  s.addText([
    { text: "시사점  ", options: { fontFace: F.bold, fontSize: 10.5, color: C.blue } },
    { text: "정확도는 모델이 결정, 속도는 하드웨어가 결정 — 같은 모델이면 GPU에서도 SWE-bench 결과는 비슷할 것. NPU↔GPU 비교의 핵심은 속도·처리량.", options: { fontFace: F.med, fontSize: 10.5, color: C.ink2 } },
  ], { x: M + 0.3, y: 6.32, w: 11.7, h: 0.5, margin: 0, valign: "middle" });
})();

/* ===================== 15 — 테스트 5: 임베딩 / 리랭커 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Test 5 · Embedding", 15, "출처: bench/results · embed / rerank task");
  title(s, "테스트 5 — 임베딩 · 리랭커",
    "검색 보조 모델(Qwen3-Embedding-8B · Qwen3-Reranker-8B)의 처리량 측정");
  methodStrip(s, 2.39, [
    ["무엇을", "임베딩/리랭킹 처리량 — SWE-bench 검색 보조에 쓰이는 모델.", C.mut],
    ["입력", "/v1/embeddings·/v1/rerank에 batch {1·4·16·64}개 입력.", C.mut],
    ["출력·분석", "초당 처리 건수(inputs/s), 배치 크기별 효율.", C.mut],
  ]);
  resultLabel(s, 3.78);
  const ry = 4.12, rh = 6.85 - ry;
  const kp = [["Qwen3-Embedding-8B", "1.17", "inputs/s", "batch 1·16·64 모두 동일 — 배치 이득 없음"],
    ["Qwen3-Reranker-8B", "1.17", "pairs/s", "쿼리당 100문서 ≈ 85초 — 항목당 약 0.85초"]];
  const kw = 3.9;
  kp.forEach(([n, v, u, note], i) => {
    const x = M + i * (kw + 0.2);
    card(s, x, ry, kw, rh, { shadow: shStd() });
    s.addText(n, { x: x + 0.28, y: ry + 0.24, w: kw - 0.56, h: 0.3, margin: 0, fontFace: F.semi, fontSize: 12.5, color: C.mut });
    s.addText([
      { text: v, options: { fontFace: F.bold, fontSize: 40, color: C.blue } },
      { text: "  " + u, options: { fontFace: F.semi, fontSize: 13, color: C.ink2 } },
    ], { x: x + 0.28, y: ry + 0.58, w: kw - 0.56, h: 0.7, margin: 0 });
    s.addText(note, { x: x + 0.28, y: ry + 1.36, w: kw - 0.56, h: 0.5, margin: 0, fontFace: F.reg, fontSize: 9.8, color: C.ink2, lineSpacingMultiple: 1.35 });
  });
  const dx = M + 2 * (kw + 0.2), dw = 12.333 - 2 * (kw + 0.2);
  card(s, dx, ry, dw, rh, { shadow: shStd() });
  accent(s, dx, ry + 0.26, rh - 0.52, C.pink);
  s.addText("처리량 이상 — 별도 점검 필요", { x: dx + 0.3, y: ry + 0.24, w: dw - 0.55, h: 0.34, margin: 0, fontFace: F.bold, fontSize: 14, color: C.ink });
  s.addText("두 모델 모두 항목당 약 0.85초 — 8B 생성 모델의 단일 prefill(수십 ms) 대비 수십 배 느리다. batch size를 키워도 처리량이 1.17/s로 고정돼 배칭이 동작하지 않는다. 아티팩트의 고정 버킷 패딩 또는 배칭 경로 미최적화 가능성 → 현재 설정으로는 대량 검색에 부적합하며 후속 점검이 필요하다.", {
    x: dx + 0.3, y: ry + 0.64, w: dw - 0.6, h: rh - 0.9, margin: 0, fontFace: F.reg, fontSize: 10.5, color: C.ink2, lineSpacingMultiple: 1.5,
  });
})();

/* ===================== 16 — 결론 & 권장 ===================== */
(() => {
  const s = pptx.addSlide();
  frame(s, "Conclusion", 16, "출처: bench/REPORT.md · 동시성은 prompt 1024 기준");
  title(s, "결론 — 2-카드에서는 Llama-3.1-8B 단독",
    "강력 후보 32B·70B는 RNGD 4카드 필요 → 정확도 우선이면 4카드 환경 권장");
  const tw = 7.0, ty = 2.39;
  card(s, M, ty, tw, 4.46, { shadow: shStd() });
  s.addText("동시 접속자별 권장 (Llama-3.1-8B · 1카드)", { x: M + 0.25, y: ty + 0.18, w: tw - 0.5, h: 0.3, margin: 0, fontFace: F.semi, fontSize: 14, color: C.ink });
  const rowsT = [
    ["동시 사용자", "요청당 속도", "TTFT p95", "판단"],
    ["1 – 8", "48 – 54 tok/s", "< 0.2 s", "쾌적"],
    ["16", "42 tok/s", "0.38 s", "양호"],
    ["32", "35 tok/s", "0.51 s", "양호 · 1카드 권장 상한"],
    ["64", "27 tok/s", "0.96 s", "처리량 우선"],
    ["128", "18 tok/s", "1.85 s", "집계 peak · 체감 느림"],
  ];
  const colX = [0, 1.7, 3.4, 4.4], colW = [1.7, 1.7, 1.0, 2.1];
  const tx = M + 0.25, th0 = ty + 0.56, rh = 0.55;
  rowsT.forEach((r, ri) => {
    const y = th0 + ri * rh;
    if (ri === 0) s.addShape(pptx.ShapeType.rect, { x: tx, y, w: tw - 0.5, h: rh, fill: { color: C.border }, line: { type: "none" } });
    else if (ri % 2 === 0) s.addShape(pptx.ShapeType.rect, { x: tx, y, w: tw - 0.5, h: rh, fill: { color: "fafafa" }, line: { type: "none" } });
    r.forEach((c, ci) => {
      s.addText(c, {
        x: tx + colX[ci] + 0.08, y, w: colW[ci], h: rh, margin: 0, valign: "middle",
        fontFace: ri === 0 || ci === 0 ? F.semi : F.reg, fontSize: 11,
        color: ri === 0 ? C.ink : (ci === 3 ? C.blue : C.ink),
      });
    });
  });
  s.addText("전 동시성 구간 요청 실패 0건 · KV cache 27GB 확보로 KV는 병목 아님", {
    x: tx, y: th0 + 6 * rh + 0.06, w: tw - 0.5, h: 0.3, margin: 0, fontFace: F.reg, fontSize: 9.5, color: C.mut,
  });
  const rx = M + tw + 0.24, rw = 12.333 - tw - 0.24;
  const acts = [
    ["채택", "Llama-3.1-8B / 1카드", "코드 자동완성·대화형 보조에 적합. ~32명까지 쾌적, serve 옵션은 기본값.", true],
    ["보강", "32B·70B는 4카드에서", "정확도(SWE-bench)는 8B가 약함. 강력 후보는 4카드 환경에서 측정·운영.", false],
    ["점검", "임베딩·리랭커 처리량", "1.17/s는 비정상 — 대량 검색 전 배칭/버킷 설정 점검 필요.", false],
  ];
  const ah = (4.46 - 2 * 0.18) / 3;
  acts.forEach(([tg, ti, d, feat], i) => {
    const y = ty + i * (ah + 0.18);
    card(s, rx, y, rw, ah, { fill: feat ? C.blue : C.white, line: feat ? null : C.border, shadow: feat ? shGlow() : shStd(), r: feat ? 0.16 : 0.13 });
    if (feat) {
      s.addShape(pptx.ShapeType.roundRect, { x: rx + 0.22, y: y + 0.2, w: 0.82, h: 0.3, rectRadius: 0.15, fill: { color: C.white }, line: { type: "none" } });
      s.addText(tg, { x: rx + 0.22, y: y + 0.2, w: 0.82, h: 0.3, margin: 0, align: "center", valign: "middle", fontFace: F.semi, fontSize: 10, color: C.blue });
    } else {
      tag(s, rx + 0.22, y + 0.2, tg, [C.blue, C.blue3, C.pink][i]);
    }
    s.addText(ti, { x: rx + 0.22, y: y + 0.55, w: rw - 0.44, h: 0.32, margin: 0, fontFace: F.bold, fontSize: 14, color: feat ? C.white : C.ink });
    s.addText(d, { x: rx + 0.22, y: y + 0.88, w: rw - 0.44, h: ah - 1.0, margin: 0, fontFace: F.reg, fontSize: 10, color: feat ? "dbe6ff" : C.ink2, lineSpacingMultiple: 1.38 });
  });
})();

pptx.writeFile({ fileName: "/home/jun/bench/ppt/RNGD_Benchmark.pptx" })
  .then(() => console.log("OK: 16 slides"))
  .catch((e) => { console.error(e); process.exit(1); });
