import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const require = createRequire(import.meta.url);
const katex = require(resolve(root, "site/vendor/katex/katex.min.js"));
const documents = [
  { source: "content/proposal.md", output: "site/proposal.html", page: "proposal", type: "Pilot proposal", title: "WelfareMap AI P0 실증 제안서", subtitle: "고령인구 복지 불균형 완화를 위한 신규 경로당 1개 입지 의사결정 지원", status: "조건부 실증 제안 · 데이터 gate 적용", audience: "지자체 의사결정자 · 복지·도시계획 부서 · 실증 파트너", date: "2026. 07. 17." },
  { source: "content/planning.md", output: "site/planning.html", page: "planning", type: "Business plan", title: "WelfareMap AI 사업 기획서", subtitle: "고령인구 복지 불균형 완화를 위한 신규 경로당 1개 입지·사업규모 추천", status: "P0 확정 · 사업 입력 검증 단계", audience: "지자체 · 공공 복지기관 · 도시계획 부서", date: "2026. 07. 17." },
  { source: "content/technical-blueprint.md", output: "site/technical-blueprint.html", page: "blueprint", type: "Technical blueprint", title: "WelfareMap AI 기술 청사진", subtitle: "예상 동시수요·수도권 경로·필지 예산·형평성 배분 기반 구현 명세", status: "P0 exact-first · 구현 기준", audience: "ML 엔지니어 · 데이터 엔지니어 · 공간 분석가", date: "2026. 07. 17." },
  { source: "content/dual-graph-recommendation.md", output: "site/dual-graph-recommendation.html", page: "dual-graph", type: "Architecture specification", title: "P0 이중 그래프 구현 명세", subtitle: "100m 의사결정 그래프 + 상태 확장 경로 그래프", status: "P0 확정 · 라우팅·텐서 계약", audience: "ML 엔지니어 · 교통 모델러 · 공간 분석가", date: "2026. 07. 17.", sectionLevel: 3, summary: "100m 격자를 GNN의 입지 의사결정 단위로 유지하고, 환승 이력에 의존하는 고령자 일반화 이동비용은 별도의 상태 확장 경로 그래프에서 계산한다. 직접도보와 직전 노선을 보존해 억지 승차, 숨은 환승, 무비용 순환을 구조적으로 차단한다." },
  { source: "report/facility-data-capacity-resolution.md", output: "site/facility-data.html", page: "facility-data", type: "Data quality audit", title: "P0 시설 데이터·용량 감사", subtitle: "서울시 경로당 원천·좌표 coverage·운영상태·동시수용량의 현재 준비도", status: "잠정 · 최종 최적화 입력 미완료", audience: "정책 담당자 · 데이터 엔지니어 · 공간 분석가", date: "2026. 07. 17.", summary: "경로당 3,644건의 좌표값은 모두 존재하지만 엄격 검증 완료는 2건이고 실제 운영 동시수용량은 0건이다. 고정 8명은 공급량에서 제거했으며, 자치구 회신 전에는 STRICT_UNKNOWN과 LEGAL_NOMINAL 시나리오의 순위 안정성을 함께 본다." },
];

const escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const renderMath = (value, displayMode) => katex.renderToString(value, {
  displayMode,
  output: "htmlAndMathml",
  strict: "ignore",
  throwOnError: false,
  trust: false,
});
const renderInline = (value) => {
  const expressions = [];
  const links = [];
  const protectedLinks = String(value).replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, label, href) => {
    links.push({ label, href });
    return `@@LINK_${links.length - 1}@@`;
  });
  const protectedValue = protectedLinks.replace(/\$([^$\n]+)\$|\\\((.+?)\\\)/g, (_, dollarExpression, parenthesizedExpression) => {
    const expression = dollarExpression ?? parenthesizedExpression;
    expressions.push(expression);
    return `@@MATH_${expressions.length - 1}@@`;
  });

  return escapeHtml(protectedValue)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/@@MATH_(\d+)@@/g, (_, expressionIndex) => `<span class="math-inline">${renderMath(expressions[Number(expressionIndex)], false)}</span>`)
    .replace(/@@LINK_(\d+)@@/g, (_, linkIndex) => {
      const link = links[Number(linkIndex)];
      return `<a href="${escapeHtml(link.href)}" target="_blank" rel="noreferrer">${renderInline(link.label)}</a>`;
    });
};
const isTableDivider = (line) => /^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(line);
const tableCells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
const isMathBlockStart = (line) => /^\s*\$\$\s*$/.test(line) || /^\s*\\\[\s*$/.test(line);

function renderMarkdown(markdown, sectionLevel = 2) {
  const allLines = markdown.replaceAll("\r\n", "\n").split("\n");
  const firstSectionPattern = new RegExp(`^${"#".repeat(sectionLevel)}\\s+1\\.`);
  const firstSection = allLines.findIndex((line) => firstSectionPattern.test(line));
  const lines = firstSection >= 0 ? allLines.slice(firstSection) : allLines;
  const toc = [];
  const blocks = [];
  let index = 0;
  let sectionIndex = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim() || /^---+$/.test(line)) { index += 1; continue; }
    const heading = line.match(/^(#{2,5})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2].trim();
      if (level === sectionLevel) {
        if (sectionIndex > 0) blocks.push("</section>");
        sectionIndex += 1;
        const id = `section-${sectionIndex}`;
        toc.push({ id, text });
        blocks.push(`<section class="document-section" id="${id}"><div class="document-section-index">${String(sectionIndex).padStart(2, "0")}</div><h2>${renderInline(text)}</h2>`);
      } else {
        const outputLevel = Math.min(4, Math.max(3, level - sectionLevel + 2));
        blocks.push(`<h${outputLevel}>${renderInline(text)}</h${outputLevel}>`);
      }
      index += 1;
      continue;
    }
    if (/^```/.test(line)) {
      const language = line.slice(3).trim();
      const code = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index])) { code.push(lines[index]); index += 1; }
      index += 1;
      blocks.push(`<pre><code${language ? ` data-language="${escapeHtml(language)}"` : ""}>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    if (isMathBlockStart(line)) {
      const equation = [];
      const endPattern = /^\s*\$\$\s*$/.test(line) ? /^\s*\$\$\s*$/ : /^\s*\\\]\s*$/;
      index += 1;
      while (index < lines.length && !endPattern.test(lines[index])) { equation.push(lines[index].trim()); index += 1; }
      index += 1;
      blocks.push(`<div class="math-block">${renderMath(equation.join(" "), true)}</div>`);
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) { quote.push(lines[index].replace(/^>\s?/, "")); index += 1; }
      blocks.push(`<blockquote>${quote.map(renderInline).join(" ")}</blockquote>`);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) { items.push(lines[index].replace(/^[-*]\s+/, "")); index += 1; }
      blocks.push(`<ul>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ul>`);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) { items.push(lines[index].replace(/^\d+\.\s+/, "")); index += 1; }
      blocks.push(`<ol>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ol>`);
      continue;
    }
    if (line.includes("|") && isTableDivider(lines[index + 1] ?? "")) {
      const header = tableCells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) { rows.push(tableCells(lines[index])); index += 1; }
      blocks.push(`<div class="table-frame document-table" role="region" aria-label="${escapeHtml(header.join(", "))}" tabindex="0"><table><thead><tr>${header.map((cell) => `<th>${renderInline(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell, cellIndex) => cellIndex === 0 ? `<th>${renderInline(cell)}</th>` : `<td>${renderInline(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    const values = [];
    while (index < lines.length) {
      const value = lines[index];
      if (!value.trim() || /^(#{2,5})\s+/.test(value) || /^```/.test(value) || isMathBlockStart(value) || /^>\s?/.test(value) || /^[-*]\s+/.test(value) || /^\d+\.\s+/.test(value) || /^---+$/.test(value)) break;
      if (value.includes("|") && isTableDivider(lines[index + 1] ?? "")) break;
      values.push(value.trim());
      index += 1;
    }
    if (values.length) blocks.push(`<p>${renderInline(values.join(" "))}</p>`);
    else index += 1;
  }
  if (sectionIndex > 0) blocks.push("</section>");
  return { content: blocks.join("\n"), toc };
}

const nav = (active) => `<nav class="document-nav" aria-label="문서 탐색"><a${active === "method" ? ' class="active" aria-current="page"' : ""} href="./index.html">P0 방법론</a><a${active === "proposal" ? ' class="active" aria-current="page"' : ""} href="./proposal.html">실증 제안서</a><a${active === "planning" ? ' class="active" aria-current="page"' : ""} href="./planning.html">사업 기획서</a><a${active === "blueprint" ? ' class="active" aria-current="page"' : ""} href="./technical-blueprint.html">기술 청사진</a><a${active === "dual-graph" ? ' class="active" aria-current="page"' : ""} href="./dual-graph-recommendation.html">이중 그래프</a><a${active === "facility-data" ? ' class="active" aria-current="page"' : ""} href="./facility-data.html">시설 데이터</a></nav>`;

function pageTemplate(document, rendered) {
  const summary = document.summary ? `<section class="document-summary"><span>Technical summary</span><h2>핵심 권고</h2><p>${renderInline(document.summary)}</p></section>` : "";
  return `<!doctype html><html lang="ko"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><meta name="description" content="${escapeHtml(document.subtitle)}" /><meta name="theme-color" content="#10233f" /><title>${escapeHtml(document.title)} | Elder Guardian</title><link rel="icon" href="./favicon.svg" type="image/svg+xml" /><link rel="stylesheet" href="./vendor/katex/katex.min.css" /><link rel="stylesheet" href="./report.css" /><script defer src="./report.js"></script></head><body><a class="skip-link" href="#content">본문으로 건너뛰기</a>
<header class="topbar"><a class="brand" href="./index.html" aria-label="Elder Guardian 방법론 보고서로"><svg viewBox="0 0 36 36" aria-hidden="true"><path d="M29 6C17 6 9 12 9 21c0 3 1 5 3 7 2-7 7-12 13-15-5 4-9 9-11 16 3 1 6 1 9 0 8-3 9-13 6-23Z"/><path d="m13 27-7 5"/></svg><span>Elder Guardian</span></a>${nav(document.page)}<a class="github" href="https://github.com/Elder-Gardian/Planning" target="_blank" rel="noreferrer">GitHub <span aria-hidden="true">↗</span></a></header>
<div class="page-shell document-shell" id="top"><aside class="toc document-toc" aria-label="${escapeHtml(document.title)} 목차"><p>Contents</p><nav>${rendered.toc.map((item) => `<a href="#${item.id}">${renderInline(item.text)}</a>`).join("")}</nav><div class="toc-meta"><span>문서 유형</span><strong>${escapeHtml(document.type)}</strong><span>섹션</span><strong>${rendered.toc.length}개</strong><span>작성일</span><strong>${escapeHtml(document.date ?? "2026. 07. 15.")}</strong></div></aside>
<main class="report document-report" id="content"><header class="report-header document-header"><div class="mobile-document-nav">${nav(document.page)}</div><div class="report-meta"><span>${escapeHtml(document.type)}</span><span>WelfareMap AI</span></div><h1>${escapeHtml(document.title)}</h1><p class="dek">${escapeHtml(document.subtitle)}</p><div class="report-status"><span class="status-dot"></span><p><strong>문서 상태</strong> ${escapeHtml(document.status)}</p><p><strong>주요 독자</strong> ${escapeHtml(document.audience)}</p></div></header><article class="document-content">${summary}${rendered.content}</article><footer class="report-footer"><div><strong>Elder Guardian · Planning</strong><span>${escapeHtml(document.title)}</span></div><a href="https://github.com/Elder-Gardian/Planning" target="_blank" rel="noreferrer">GitHub 저장소 ↗</a></footer></main></div></body></html>`;
}

for (const document of documents) {
  const markdown = await readFile(resolve(root, document.source), "utf8");
  const rendered = renderMarkdown(markdown, document.sectionLevel);
  await writeFile(resolve(root, document.output), pageTemplate(document, rendered), "utf8");
  console.log(`${document.output}: ${rendered.toc.length} sections`);
}
