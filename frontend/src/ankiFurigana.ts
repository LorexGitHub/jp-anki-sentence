/** Convert Anki-style 漢字[かんじ] into HTML ruby for preview. */
export function ankiToRubyHtml(text: string): string {
  const parts: string[] = [];
  const re = /([^\[\]]+?)\[([^\]]+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      parts.push(escapeHtml(text.slice(last, m.index)));
    }
    parts.push(
      `<ruby>${escapeHtml(m[1])}<rt>${escapeHtml(m[2])}</rt></ruby>`
    );
    last = m.index + m[0].length;
  }

  if (last < text.length) {
    parts.push(escapeHtml(text.slice(last)));
  }

  return parts.join("") || escapeHtml(text);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
