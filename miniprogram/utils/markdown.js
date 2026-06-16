/** 简易 Markdown → rich-text HTML（小程序 subset） */
function toRichHtml(md) {
  if (!md) return ''
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<p style="font-weight:bold;margin:8px 0 4px">$1</p>')
    .replace(/^## (.+)$/gm, '<p style="font-weight:bold;font-size:16px;margin:10px 0 4px">$1</p>')
    .replace(/^# (.+)$/gm, '<p style="font-weight:bold;font-size:17px;margin:10px 0 4px">$1</p>')
    .replace(/^\s*[-*+]\s+(.+)$/gm, '<p style="margin:4px 0;padding-left:12px">• $1</p>')
    .replace(/^\s*\d+\.\s+(.+)$/gm, '<p style="margin:4px 0;padding-left:12px">$1</p>')
    .replace(/\n/g, '<br/>')
  return html
}

function stripMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim()
}

module.exports = { toRichHtml, stripMarkdown }
