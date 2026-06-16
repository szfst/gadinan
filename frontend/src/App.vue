<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { renderMarkdown, stripMarkdown } from './utils/text.js'

const isRecording = ref(false)
const isLoading = ref(false)
const loadingStep = ref('')
const errorMsg = ref('')
const recordDuration = ref(0)
const turns = ref([])
const chatHistory = ref([])
const speakingKey = ref(null)
const speakError = ref('')
const chatListRef = ref(null)

let mediaRecorder = null
let audioChunks = []
let durationTimer = null
let voicesReady = false

const synth = typeof window !== 'undefined' ? window.speechSynthesis : null
const isSecure = window.isSecureContext

const statusText = computed(() => {
  if (!isSecure) return '需要 HTTPS 才能使用麦克风'
  if (loadingStep.value) return loadingStep.value
  if (isRecording.value) return `录音中 ${recordDuration.value}s`
  if (turns.value.length) return '继续说话，AI 会记住上下文'
  return '点击按钮，用闽南语开始对话'
})

function getRecorderOptions() {
  const types = [
    'audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac', 'audio/ogg;codecs=opus',
  ]
  for (const mimeType of types) {
    if (MediaRecorder.isTypeSupported(mimeType)) return { mimeType }
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

async function scrollToBottom() {
  await nextTick()
  if (chatListRef.value) {
    chatListRef.value.scrollTop = chatListRef.value.scrollHeight
  }
}

async function startRecording() {
  errorMsg.value = ''
  speakError.value = ''
  stopSpeaking()

  if (!isSecure) {
    errorMsg.value = '请使用 HTTPS 访问，手机浏览器在 HTTP 下无法录音'
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
      audio: { echoCancellation: true, noiseSuppression: true },
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
  if (isRecording.value) stopRecording()
  else if (!isLoading.value) startRecording()
}

function newConversation() {
  stopSpeaking()
  turns.value = []
  chatHistory.value = []
  errorMsg.value = ''
  speakError.value = ''
}

async function sendVoiceChat(blob) {
  isLoading.value = true
  loadingStep.value = '正在识别并思考...'
  errorMsg.value = ''

  const ext = blob.type.includes('mp4') || blob.type.includes('aac')
    ? 'm4a'
    : blob.type.includes('ogg') ? 'ogg' : 'webm'
  const formData = new FormData()
  formData.append('file', blob, `recording.${ext}`)
  formData.append('history', JSON.stringify(chatHistory.value))

  try {
    const res = await fetch('/api/voice-chat', { method: 'POST', body: formData })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '处理失败')

    const turn = {
      id: Date.now(),
      dialect: data.dialect_text,
      mandarin: data.mandarin_text,
      answer: data.answer,
      answerMinnan: data.answer_minnan || data.answer,
    }
    turns.value.push(turn)

    chatHistory.value.push({ role: 'user', content: data.mandarin_text })
    chatHistory.value.push({ role: 'assistant', content: data.answer })

    await scrollToBottom()
  } catch (err) {
    errorMsg.value = err.message || '请求失败，请确认服务已启动且已配置 DeepSeek Key'
  } finally {
    isLoading.value = false
    loadingStep.value = ''
  }
}

function loadVoices() {
  if (!synth) return []
  return synth.getVoices()
}

function pickVoice(lang) {
  const voices = loadVoices()
  if (lang === 'minnan') {
    const rules = [
      (v) => v.lang === 'nan-TW' || v.lang === 'nan-CN' || v.lang === 'nan',
      (v) => /minnan|闽南|潮州|台语|台湾/i.test(v.name),
      (v) => v.lang.startsWith('zh-TW'),
    ]
    for (const rule of rules) {
      const voice = voices.find(rule)
      if (voice) return { voice, lang: voice.lang }
    }
    return { voice: null, lang: 'zh-TW' }
  }
  const rules = [
    (v) => v.lang === 'zh-CN',
    (v) => v.lang.startsWith('zh') && !v.lang.startsWith('zh-TW'),
    (v) => v.lang.startsWith('zh'),
  ]
  for (const rule of rules) {
    const voice = voices.find(rule)
    if (voice) return { voice, lang: voice.lang }
  }
  return { voice: voices[0] || null, lang: 'zh-CN' }
}

function speak(rawText, turnId, lang) {
  speakError.value = ''
  const text = stripMarkdown(rawText)
  if (!text) {
    speakError.value = '没有可朗读的内容'
    return
  }
  if (!synth) {
    speakError.value = '当前浏览器不支持语音朗读'
    return
  }

  const key = `${turnId}-${lang}`
  if (speakingKey.value === key) {
    stopSpeaking()
    return
  }

  stopSpeaking()

  const start = () => {
    const utterance = new SpeechSynthesisUtterance(text)
    const { voice, lang: utterLang } = pickVoice(lang)
    utterance.lang = utterLang
    if (voice) utterance.voice = voice
    utterance.rate = lang === 'minnan' ? 0.9 : 1

    utterance.onstart = () => { speakingKey.value = key }
    utterance.onend = () => { speakingKey.value = null }
    utterance.onerror = (e) => {
      speakingKey.value = null
      speakError.value = `朗读失败（${e.error || 'unknown'}）`
    }

    synth.resume()
    synth.speak(utterance)
  }

  if (loadVoices().length > 0 || voicesReady) start()
  else {
    synth.onvoiceschanged = () => {
      voicesReady = true
      synth.onvoiceschanged = null
      start()
    }
    loadVoices()
    setTimeout(start, 300)
  }
}

function stopSpeaking() {
  if (synth) {
    synth.cancel()
    speakingKey.value = null
  }
}

function isSpeaking(turnId, lang) {
  return speakingKey.value === `${turnId}-${lang}`
}

onMounted(() => {
  if (synth) {
    loadVoices()
    synth.onvoiceschanged = () => { voicesReady = true }
  }
})

onUnmounted(() => {
  stopSpeaking()
  clearInterval(durationTimer)
})
</script>

<template>
  <div class="container">
    <header class="header">
      <h1>闽南话语音助手</h1>
      <p class="subtitle">连续对话 · Markdown 展示 · 普通话 / 闽南语朗读</p>
    </header>

    <main class="card">
      <div class="toolbar">
        <span class="status">{{ statusText }}</span>
        <button v-if="turns.length" class="new-chat-btn" @click="newConversation">新对话</button>
      </div>

      <div v-if="turns.length" ref="chatListRef" class="chat-list">
        <div v-for="(turn, i) in turns" :key="turn.id" class="turn">
          <div class="turn-label">第 {{ i + 1 }} 轮</div>
          <div class="bubble user-bubble">
            <p v-if="turn.dialect" class="dialect-line"><span>闽南语</span>{{ turn.dialect }}</p>
            <p class="mandarin-line"><span>普通话</span>{{ turn.mandarin }}</p>
          </div>
          <div class="bubble ai-bubble">
            <div class="ai-header">
              <span>AI 回答</span>
              <div class="speak-group">
                <button
                  class="speak-btn mandarin"
                  :class="{ active: isSpeaking(turn.id, 'mandarin') }"
                  @click="speak(turn.answer, turn.id, 'mandarin')"
                >
                  {{ isSpeaking(turn.id, 'mandarin') ? '🔇' : '🔊' }} 普通话
                </button>
                <button
                  class="speak-btn minnan"
                  :class="{ active: isSpeaking(turn.id, 'minnan') }"
                  @click="speak(turn.answerMinnan, turn.id, 'minnan')"
                >
                  {{ isSpeaking(turn.id, 'minnan') ? '🔇' : '🔊' }} 闽南语
                </button>
              </div>
            </div>
            <div class="markdown-body" v-html="renderMarkdown(turn.answer)" />
            <p v-if="turn.answerMinnan" class="answer-minnan">
              <span>闽南语版</span>{{ turn.answerMinnan }}
            </p>
          </div>
        </div>
      </div>

      <section v-else-if="!isLoading && !isRecording" class="hint">
        <p v-if="!isSecure" class="warn">⚠️ 请使用 HTTPS 访问，手机才能录音。</p>
        <p>用闽南话提问，可多轮连续对话。</p>
      </section>

      <div v-if="errorMsg" class="error">{{ errorMsg }}</div>
      <div v-if="speakError" class="speak-error">{{ speakError }}</div>

      <button
        class="record-btn"
        :class="{ recording: isRecording, loading: isLoading }"
        :disabled="isLoading"
        @click="toggleRecording"
      >
        <span class="icon">{{ isRecording ? '⏹' : '🎤' }}</span>
        <span>{{ isRecording ? '停止并发送' : isLoading ? '处理中...' : turns.length ? '继续说话' : '开始录音' }}</span>
      </button>
    </main>
  </div>
</template>

<style scoped>
.container {
  max-width: 640px;
  margin: 0 auto;
  padding: 24px 16px 40px;
}

.header {
  text-align: center;
  color: #fff;
  margin-bottom: 20px;
}

.header h1 {
  font-size: 26px;
  font-weight: 700;
  margin-bottom: 6px;
}

.subtitle {
  font-size: 13px;
  opacity: 0.85;
}

.card {
  background: #fff;
  border-radius: 16px;
  padding: 20px 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 140px);
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.status {
  flex: 1;
  color: #666;
  font-size: 14px;
}

.new-chat-btn {
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 16px;
  cursor: pointer;
  color: #666;
  white-space: nowrap;
}

.chat-list {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 16px;
  max-height: 55vh;
  padding-right: 4px;
}

.turn { margin-bottom: 20px; }

.turn-label {
  font-size: 12px;
  color: #aaa;
  margin-bottom: 8px;
  text-align: center;
}

.bubble {
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 8px;
}

.user-bubble { background: #f0f4ff; }
.ai-bubble { background: #f8f9ff; border: 1px solid #e8ebff; }

.dialect-line,
.mandarin-line {
  line-height: 1.6;
  word-break: break-word;
}

.dialect-line {
  font-size: 14px;
  color: #666;
  margin-bottom: 6px;
}

.mandarin-line {
  font-size: 16px;
  color: #1a1a1a;
  font-weight: 500;
}

.dialect-line span,
.mandarin-line span {
  display: inline-block;
  font-size: 11px;
  color: #999;
  margin-right: 6px;
  min-width: 42px;
}

.ai-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12px;
  color: #888;
}

.speak-group {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.speak-btn {
  padding: 4px 8px;
  font-size: 11px;
  border-radius: 14px;
  cursor: pointer;
  white-space: nowrap;
}

.speak-btn.mandarin {
  border: 1px solid #667eea;
  background: #fff;
  color: #667eea;
}

.speak-btn.minnan {
  border: 1px solid #e67e22;
  background: #fff;
  color: #e67e22;
}

.speak-btn.mandarin.active {
  background: #667eea;
  color: #fff;
}

.speak-btn.minnan.active {
  background: #e67e22;
  color: #fff;
}

.markdown-body {
  font-size: 15px;
  line-height: 1.7;
  color: #222;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  font-size: 16px;
  font-weight: 700;
  margin: 12px 0 6px;
}

.markdown-body :deep(p) {
  margin: 6px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(strong) {
  font-weight: 700;
  color: #111;
}

.markdown-body :deep(code) {
  background: #eef1ff;
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 13px;
}

.markdown-body :deep(pre) {
  background: #f4f4f5;
  padding: 10px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
}

.answer-minnan {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #dde1ff;
  font-size: 14px;
  color: #e67e22;
  line-height: 1.6;
}

.answer-minnan span {
  display: block;
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
}

.record-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 16px;
  font-size: 17px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #667eea, #764ba2);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  flex-shrink: 0;
}

.record-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.record-btn.recording {
  background: linear-gradient(135deg, #e74c3c, #c0392b);
  animation: pulse 1.5s infinite;
}

.icon { font-size: 22px; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.error,
.speak-error {
  margin-bottom: 12px;
  padding: 10px;
  background: #fef2f2;
  color: #dc2626;
  border-radius: 8px;
  font-size: 13px;
  text-align: center;
}

.hint {
  text-align: center;
  color: #999;
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 16px;
}

.warn {
  color: #dc2626;
  font-weight: 500;
}
</style>
