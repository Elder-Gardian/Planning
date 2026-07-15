import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const require = createRequire(import.meta.url);
const katex = require(resolve(root, "site/vendor/katex/katex.min.js"));
const documents = [
  { source: "content/planning.md", output: "site/planning.html", page: "planning", type: "Business plan", title: "WelfareMap AI 사업 기획서", subtitle: "AI 기반 노인 복지 사각지대 탐지 및 신규 복지시설 입지·규모 추천", status: "사업 구상 · 정책 의사결정 지원", audience: "지자체 · 공공 복지기관 · 도시계획 부서" },
  { source: "content/technical-blueprint.md", output: "site/technical-blueprint.html", page: "blueprint", type: "Technical blueprint", title: "WelfareMap AI 기술 청사진", subtitle: "노인 복지시설 계획을 위한 그래프 신경망 및 강화학습 아키텍처", status: "기술 설계 · MVP 기준", audience: "ML 엔지니어 · 데이터 엔지니어 · 공간 분석가" },
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
  const protectedValue = String(value).replace(/\$([^$\n]+)\$/g, (_, expression) => {
    expressions.push(expression);
    return `@@MATH_${expressions.length - 1}@@`;
  });

  return escapeHtml(protectedValue)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/@@MATH_(\d+)@@/g, (_, expressionIndex) => `<span class="math-inline">${renderMath(expressions[Number(expressionIndex)], false)}</span>`);
};
const isTableDivider = (line) => /^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(line);
const tableCells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

function renderMarkdown(markdown) {
  const allLines = markdown.replaceAll("\r\n", "\n").split("\n");
  const firstSection = allLines.findIndex((line) => /^##\s+1\./.test(line));
  const lines = firstSection >= 0 ? allLines.slice(firstSection) : allLines;
  const toc = [];
  const blocks = [];
  let index = 0;
  let sectionIndex = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim() || /^---+$/.test(line)) { index += 1; continue; }
    const heading = line.match(/^(#{2,4})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2].trim();
      if (level === 2) {
        if (sectionIndex > 0) blocks.push("</section>");
        sectionIndex += 1;
        const id = `section-${sectionIndex}`;
        toc.push({ id, text });
        blocks.push(`<section class="document-section" id="${id}"><div class="document-section-index">${String(sectionIndex).padStart(2, "0")}</div><h2>${renderInline(text)}</h2>`);
      } else blocks.push(`<h${level}>${renderInline(text)}</h${level}>`);
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
    if (/^\$\$\s*$/.test(line)) {
      const equation = [];
      index += 1;
      while (index < lines.length && !/^\$\$\s*$/.test(lines[index])) { equation.push(lines[index].trim()); index += 1; }
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
      if (!value.trim() || /^(#{2,4})\s+/.test(value) || /^```/.test(value) || /^\$\$\s*$/.test(value) || /^>\s?/.test(value) || /^[-*]\s+/.test(value) || /^\d+\.\s+/.test(value) || /^---+$/.test(value)) break;
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

const nav = (active) => `<nav class="document-nav" aria-label="문서 탐색"><a${active === "method" ? ' class="active" aria-current="page"' : ""} href="./index.html">방법론</a><a${active === "planning" ? ' class="active" aria-current="page"' : ""} href="./planning.html">사업 기획서</a><a${active === "blueprint" ? ' class="active" aria-current="page"' : ""} href="./technical-blueprint.html">기술 청사진</a></nav>`;

function pageTemplate(document, rendered) {
  return `<!doctype html><html lang="ko"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><meta name="description" content="${escapeHtml(document.subtitle)}" /><meta name="theme-color" content="#10233f" /><title>${escapeHtml(document.title)} | Elder Guardian</title><link rel="stylesheet" href="./vendor/katex/katex.min.css" /><link rel="stylesheet" href="./report.css" /><script defer src="./report.js"></script></head><body><a class="skip-link" href="#content">본문으로 건너뛰기</a>
<header class="topbar"><a class="brand" href="./index.html" aria-label="Elder Guardian 방법론 보고서로"><svg viewBox="0 0 36 36" aria-hidden="true"><path d="M29 6C17 6 9 12 9 21c0 3 1 5 3 7 2-7 7-12 13-15-5 4-9 9-11 16 3 1 6 1 9 0 8-3 9-13 6-23Z"/><path d="m13 27-7 5"/></svg><span>Elder Guardian</span></a>${nav(document.page)}<a class="github" href="https://github.com/Elder-Gardian/Planning" target="_blank" rel="noreferrer">GitHub <span aria-hidden="true">↗</span></a></header>
<div class="page-shell document-shell" id="top"><aside class="toc document-toc" aria-label="${escapeHtml(document.title)} 목차"><p>Contents</p><nav>${rendered.toc.map((item) => `<a href="#${item.id}">${renderInline(item.text)}</a>`).join("")}</nav><div class="toc-meta"><span>문서 유형</span><strong>${escapeHtml(document.type)}</strong><span>섹션</span><strong>${rendered.toc.length}개</strong><span>작성일</span><strong>2026. 07. 15.</strong></div></aside>
<main class="report document-report" id="content"><header class="report-header document-header"><div class="mobile-document-nav">${nav(document.page)}</div><div class="report-meta"><span>${escapeHtml(document.type)}</span><span>WelfareMap AI</span></div><h1>${escapeHtml(document.title)}</h1><p class="dek">${escapeHtml(document.subtitle)}</p><div class="report-status"><span class="status-dot"></span><p><strong>문서 상태</strong> ${escapeHtml(document.status)}</p><p><strong>주요 독자</strong> ${escapeHtml(document.audience)}</p></div></header><article class="document-content">${rendered.content}</article><footer class="report-footer"><div><strong>Elder Guardian · Planning</strong><span>${escapeHtml(document.title)}</span></div><a href="https://github.com/Elder-Gardian/Planning" target="_blank" rel="noreferrer">GitHub 저장소 ↗</a></footer></main></div></body></html>`;
}

for (const document of documents) {
  const markdown = await readFile(resolve(root, document.source), "utf8");
  const rendered = renderMarkdown(markdown);
  await writeFile(resolve(root, document.output), pageTemplate(document, rendered), "utf8");
  console.log(`${document.output}: ${rendered.toc.length} sections`);
}
