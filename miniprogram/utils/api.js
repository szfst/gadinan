const { API_BASE } = require('./config')

function parseResponse(data, statusCode) {
  if (typeof data === 'string') {
    if (data.trim().startsWith('<')) {
      const hint = statusCode === 504
        ? '处理超时，请稍后重试'
        : statusCode === 502
          ? '后端未启动'
          : `服务器异常 (${statusCode})`
      throw new Error(hint)
    }
    try {
      return JSON.parse(data)
    } catch (e) {
      throw new Error('服务器返回格式错误')
    }
  }
  return data
}

function voiceChat(filePath, history) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${API_BASE}/api/voice-chat`,
      filePath,
      name: 'file',
      formData: {
        history: JSON.stringify(history || []),
      },
      timeout: 600000,
      success(res) {
        try {
          const data = parseResponse(res.data, res.statusCode)
          if (res.statusCode >= 400) {
            reject(new Error(data.detail || '请求失败'))
            return
          }
          resolve(data)
        } catch (e) {
          reject(e)
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '网络请求失败，请检查域名是否已在小程序后台配置'))
      },
    })
  })
}

function checkHealth() {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE}/api/health`,
      timeout: 15000,
      success(res) {
        if (res.statusCode === 200) resolve(res.data)
        else reject(new Error('服务不可用'))
      },
      fail: reject,
    })
  })
}

module.exports = { voiceChat, checkHealth, API_BASE }
