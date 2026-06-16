/** 安全解析 API 响应，避免 HTML 错误页导致 JSON 解析失败 */
export async function parseApiResponse(res) {
  const contentType = res.headers.get('content-type') || ''
  const text = await res.text()

  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(text)
    } catch {
      throw new Error('服务器返回了无效的 JSON')
    }
  }

  if (text.trimStart().startsWith('<')) {
    const statusHint = res.status === 502
      ? '后端服务未启动或已崩溃'
      : res.status === 504
        ? '处理超时（语音识别+AI 较慢，请增大 Nginx 超时时间）'
        : res.status === 413
          ? '上传文件过大'
          : `HTTP ${res.status}`
    throw new Error(`服务器返回异常页面：${statusHint}`)
  }

  throw new Error(text.slice(0, 120) || `请求失败 (${res.status})`)
}
