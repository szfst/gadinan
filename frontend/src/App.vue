<script setup>
import { ref, computed, onUnmounted } from 'vue'

const isRecording = ref(false)
const isLoading = ref(false)
const loadingStep = ref('')
const errorMsg = ref('')
const recordDuration = ref(0)
const dialectText = ref('')
const mandarinText = ref('')
const answerText = ref('')
const isSpeaking = ref(false)

let mediaRecorder = null
let audioChunks = []
let durationTimer = null

const isSecure = window.isSecureContext

const statusText = computed(() => {
  if (!isSecure) return '需要 HTTPS 才能使用麦克风'
  if (loadingStep.value) return loadingStep.value
  if (isRecording.value) return `录音中 ${recordDuration.value}s`
  return '点击按钮，用闽南语提问'
})

function getRecorderOptions() {
  const types = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/aac',
    'audio/ogg;codecs=opus',
  ]
  for (const mimeType of types) {
    if (MediaRecorder.isTypeSupported(mimeType)) {
      return { mimeType }
    }
  }
  return undefined
}

function createMediaRecorder(stream) {
  const options = getRecorderOptions()
  try {
    return options ? new MediaRecorder(stream, options) : new MediaRecorder(stream)
  } catch {
    return new MediaRecorder(stream)
  }
}

function describeMicError(err) {
  const name = err?.name || ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return '麦克风被拒绝，请在浏览器设置中允许此网站使用麦克风'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return '未检测到麦克风设备'
  }
  if (name === 'NotSupportedError') {
    return '当前浏览器不支持录音，请用 Chrome / Safari 最新版，且需 HTTPS 访问'
  }
  if (name === 'SecurityError' || !isSecure) {
    return '请使用 HTTPS 访问（http://IP 在手机浏览器上无法录音）'
  }
  return `录音失败：${err?.message || '未知错误'}`
}

async function startRecording() {
  errorMsg.value = ''
  dialectText.value = ''
  mandarinText.value = ''
  answerText.value = ''
  stopSpeaking()

  if (!isSecure) {
    errorMsg.value = '请使用 HTTPS 访问（如 https://gardinan.xyz），手机浏览器在 HTTP 下无法录音'
    return
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    errorMsg.value = '当前浏览器不支持录音，请用 Chrome / Safari 最新版访问'
    return
  }
  if (typeof MediaRecorder === 'undefined') {
    errorMsg.value = '当前浏览器不支持 MediaRecorder，请升级浏览器'
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
      },
    })
    mediaRecorder = createMediaRecorder(stream)
    audioChunks = []

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }

    mediaRecorder.onerror = (e) => {
      errorMsg.value = describeMicError(e.error || new Error('MediaRecorder error'))
      isRecording.value = false
      clearInterval(durationTimer)
      stream.getTracks().forEach((t) => t.stop())
    }

    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop())
      clearInterval(durationTimer)
      if (audioChunks.length === 0) {
        errorMsg.value = '未录到音频，请重新录音'
        return
      }
      const mimeType = mediaRecorder.mimeType || audioChunks[0]?.type || 'audio/webm'
      sendVoiceChat(new Blob(audioChunks, { type: mimeType }))
    }

    // iOS 需要 timeslice 才能稳定产生数据
    mediaRecorder.start(1000)
    isRecording.value = true
    recordDuration.value = 0
    durationTimer = setInterval(() => recordDuration.value++, 1000)
  } catch (err) {
    errorMsg.value = describeMicError(err)
    console.error(err)
  }
}

function stopRecording() {
  if (mediaRecorder && isRecording.value) {
    mediaRecorder.stop()
    isRecording.value = false
  }
}

function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else if (!isLoading.value) {
    startRecording()
  }
}

async function sendVoiceChat(blob) {
  isLoading.value = true
  loadingStep.value = '正在识别闽南语...'
  errorMsg.value = ''

  const ext = blob.type.includes('mp4') || blob.type.includes('aac')
    ? 'm4a'
    : blob.type.includes('ogg')
      ? 'ogg'
      : 'webm'
  const formData = new FormData()
  formData.append('file', blob, `recording.${ext}`)

  try {
    const res = await fetch('/api/voice-chat', { method: 'POST', body: formData })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '处理失败')

    dialectText.value = data.dialect_text
    mandarinText.value = data.mandarin_text
    answerText.value = data.answer
    console.log('闽南语:', data.dialect_text)
    console.log('普通话:', data.mandarin_text)
    console.log('回答:', data.answer)
  } catch (err) {
    errorMsg.value = err.message || '请求失败，请确认服务已启动且已配置 DeepSeek Key'
  } finally {
    isLoading.value = false
    loadingStep.value = ''
  }
}

function speak(text) {
  if (!text || !window.speechSynthesis) return

  stopSpeaking()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 1
  utterance.onstart = () => { isSpeaking.value = true }
  utterance.onend = () => { isSpeaking.value = false }
  utterance.onerror = () => { isSpeaking.value = false }
  window.speechSynthesis.speak(utterance)
}

function stopSpeaking() {
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel()
    isSpeaking.value = false
  }
}

function toggleSpeak() {
  if (isSpeaking.value) {
    stopSpeaking()
  } else {
    speak(answerText.value)
  }
}

onUnmounted(() => {
  stopSpeaking()
  clearInterval(durationTimer)
})
</script>

<template>
  <div class="container">
    <header class="header">
      <h1>闽南话语音助手</h1>
      <p class="subtitle">闽南语说话 → 普通话翻译 → DeepSeek 智能回答</p>
    </header>

    <main class="card">
      <div class="status">{{ statusText }}</div>

      <button
        class="record-btn"
        :class="{ recording: isRecording, loading: isLoading }"
        :disabled="isLoading"
        @click="toggleRecording"
      >
        <span class="icon">{{ isRecording ? '⏹' : '🎤' }}</span>
        <span>{{ isRecording ? '停止并发送' : isLoading ? '处理中...' : '开始录音提问' }}</span>
      </button>

      <div v-if="errorMsg" class="error">{{ errorMsg }}</div>

      <section v-if="dialectText" class="block">
        <h2>闽南语转写</h2>
        <p class="text dialect">{{ dialectText }}</p>
      </section>

      <section v-if="mandarinText" class="block">
        <h2>普通话翻译</h2>
        <p class="text mandarin">{{ mandarinText }}</p>
      </section>

      <section v-if="answerText" class="block answer-block">
        <div class="answer-header">
          <h2>AI 回答</h2>
          <button class="speak-btn" :class="{ active: isSpeaking }" @click="toggleSpeak">
            {{ isSpeaking ? '🔇 停止' : '🔊 朗读' }}
          </button>
        </div>
        <p class="text answer" @click="toggleSpeak">{{ answerText }}</p>
        <p class="speak-hint">点击回答文字也可朗读</p>
      </section>

      <section v-if="!dialectText && !isLoading && !isRecording" class="hint">
        <p v-if="!isSecure" class="warn">⚠️ 当前为 HTTP 访问，手机无法录音。请配置 HTTPS 后访问。</p>
        <p>用闽南话提问，例如：「今天天气怎么样？」</p>
        <p>系统会自动翻译为普通话，并调用 DeepSeek 回答。</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.container {
  max-width: 640px;
  margin: 0 auto;
  padding: 40px 20px;
}

.header {
  text-align: center;
  color: #fff;
  margin-bottom: 32px;
}

.header h1 {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 8px;
}

.subtitle {
  font-size: 14px;
  opacity: 0.85;
}

.card {
  background: #fff;
  border-radius: 16px;
  padding: 32px 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.status {
  text-align: center;
  color: #666;
  font-size: 15px;
  margin-bottom: 24px;
}

.record-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 16px;
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #667eea, #764ba2);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: transform 0.15s, opacity 0.15s;
}

.record-btn:hover:not(:disabled) {
  transform: scale(1.02);
}

.record-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.record-btn.recording {
  background: linear-gradient(135deg, #e74c3c, #c0392b);
  animation: pulse 1.5s infinite;
}

.icon {
  font-size: 24px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.error {
  margin-top: 16px;
  padding: 12px;
  background: #fef2f2;
  color: #dc2626;
  border-radius: 8px;
  font-size: 14px;
  text-align: center;
}

.block {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.block h2 {
  font-size: 14px;
  color: #888;
  margin-bottom: 10px;
  font-weight: 600;
}

.text {
  line-height: 1.7;
  word-break: break-word;
}

.dialect {
  font-size: 16px;
  color: #666;
}

.mandarin {
  font-size: 20px;
  color: #1a1a1a;
  font-weight: 500;
}

.answer-block {
  background: #f8f9ff;
  margin-left: -24px;
  margin-right: -24px;
  padding: 20px 24px 24px;
  border-top: none;
  border-radius: 0 0 16px 16px;
}

.answer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.answer-header h2 {
  margin-bottom: 0;
}

.speak-btn {
  padding: 6px 14px;
  font-size: 13px;
  border: 1px solid #667eea;
  background: #fff;
  color: #667eea;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.15s;
}

.speak-btn:hover,
.speak-btn.active {
  background: #667eea;
  color: #fff;
}

.answer {
  font-size: 18px;
  color: #222;
  cursor: pointer;
}

.speak-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #aaa;
  text-align: center;
}

.hint {
  margin-top: 24px;
  text-align: center;
  color: #999;
  font-size: 14px;
  line-height: 1.8;
}

.warn {
  color: #dc2626;
  font-weight: 500;
  margin-bottom: 8px;
}
</style>
