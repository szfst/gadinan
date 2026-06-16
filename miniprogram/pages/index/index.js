const { voiceChat, checkHealth } = require('../../utils/api')
const { toRichHtml, stripMarkdown } = require('../../utils/markdown')

let recorder = null
let innerAudio = null
let plugin = null

Page({
  data: {
    turns: [],
    chatHistory: [],
    isRecording: false,
    isLoading: false,
    statusText: '按住说话，用闽南语提问',
    errorMsg: '',
    recordSec: 0,
    speakingKey: '',
    serviceOk: false,
  },

  onLoad() {
    recorder = wx.getRecorderManager()
    innerAudio = wx.createInnerAudioContext()
    innerAudio.obeyMuteSwitch = false

    try {
      plugin = requirePlugin('WechatSI')
    } catch (e) {
      console.warn('WechatSI 插件未启用', e)
    }

    recorder.onStop((res) => {
      this.setData({ isRecording: false, recordSec: 0 })
      if (res.duration < 500) {
        this.setData({ errorMsg: '录音太短，请按住多说一会' })
        return
      }
      this.sendVoice(res.tempFilePath)
    })

    recorder.onError((err) => {
      this.setData({
        isRecording: false,
        errorMsg: '录音失败：' + (err.errMsg || '未知错误'),
      })
    })

    innerAudio.onEnded(() => {
      this.setData({ speakingKey: '' })
    })

    innerAudio.onError(() => {
      this.setData({ speakingKey: '', errorMsg: '播放失败' })
    })

    this.checkService()
  },

  onUnload() {
    if (innerAudio) innerAudio.destroy()
  },

  async checkService() {
    try {
      await checkHealth()
      this.setData({ serviceOk: true })
    } catch (e) {
      this.setData({
        serviceOk: false,
        errorMsg: '无法连接服务器，请确认 gardinan.xyz 已配置到小程序合法域名',
      })
    }
  },

  onRecordStart() {
    if (this.data.isLoading) return
    wx.authorize({
      scope: 'scope.record',
      success: () => this.startRecord(),
      fail: () => {
        wx.showModal({
          title: '需要麦克风权限',
          content: '请在设置中允许录音',
          confirmText: '去设置',
          success(r) {
            if (r.confirm) wx.openSetting()
          },
        })
      },
    })
  },

  startRecord() {
    this.setData({
      errorMsg: '',
      isRecording: true,
      statusText: '录音中…松开发送',
      recordSec: 0,
    })
    this.stopSpeak()
    recorder.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3',
    })
    this._recordTimer = setInterval(() => {
      this.setData({ recordSec: this.data.recordSec + 1 })
    }, 1000)
  },

  onRecordEnd() {
    if (!this.data.isRecording) return
    clearInterval(this._recordTimer)
    recorder.stop()
    this.setData({ statusText: '正在识别并思考…' })
  },

  onRecordCancel() {
    if (!this.data.isRecording) return
    clearInterval(this._recordTimer)
    recorder.stop()
    this.setData({ isRecording: false, statusText: '已取消' })
  },

  async sendVoice(filePath) {
    this.setData({ isLoading: true, errorMsg: '' })
    try {
      const data = await voiceChat(filePath, this.data.chatHistory)
      const turn = {
        id: Date.now(),
        dialect: data.dialect_text,
        mandarin: data.mandarin_text,
        answer: data.answer,
        answerHtml: toRichHtml(data.answer),
        answerMinnan: data.answer_minnan || data.answer,
      }
      const turns = this.data.turns.concat(turn)
      const chatHistory = this.data.chatHistory.concat(
        { role: 'user', content: data.mandarin_text },
        { role: 'assistant', content: data.answer }
      )
      this.setData({
        turns,
        chatHistory,
        statusText: '继续按住说话，AI 会记住上下文',
      })
    } catch (e) {
      this.setData({
        errorMsg: e.message || '请求失败',
        statusText: '点击重试',
      })
    } finally {
      this.setData({ isLoading: false })
    }
  },

  newConversation() {
    this.stopSpeak()
    this.setData({
      turns: [],
      chatHistory: [],
      errorMsg: '',
      statusText: '按住说话，用闽南语提问',
    })
  },

  speak(e) {
    const { text, key, lang } = e.currentTarget.dataset
    const plain = stripMarkdown(text)
    if (!plain) return

    if (this.data.speakingKey === key) {
      this.stopSpeak()
      return
    }

    this.stopSpeak()
    this.setData({ speakingKey: key })

    if (!plugin) {
      wx.showToast({ title: '请在 app.json 启用 WechatSI 插件', icon: 'none' })
      this.setData({ speakingKey: '' })
      return
    }

    plugin.textToSpeech({
      lang: lang === 'minnan' ? 'zh_CN' : 'zh_CN',
      tts: true,
      content: plain,
      success: (res) => {
        innerAudio.src = res.filename
        innerAudio.play()
      },
      fail: () => {
        this.setData({ speakingKey: '', errorMsg: '语音合成失败' })
      },
    })
  },

  stopSpeak() {
    if (innerAudio) innerAudio.stop()
    this.setData({ speakingKey: '' })
  },
})
