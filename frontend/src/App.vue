<script setup>
import { ref, computed } from 'vue'

const isRecording = ref(false)
const isLoading = ref(false)
const resultText = ref('')
const errorMsg = ref('')
const recordDuration = ref(0)

let mediaRecorder = null
let audioChunks = []
let durationTimer = null

const statusText = computed(() => {
  if (isLoading.value) return '正在识别闽南话...'
  if (isRecording.value) return `录音中 ${recordDuration.value}s`
  return '点击按钮开始录音'
})

async function startRecording() {
  errorMsg.value = ''
  resultText.value = ''

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder = new MediaRecorder(stream, { mimeType: getSupportedMimeType() })
    audioChunks = []

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data)
    }

    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop())
      clearInterval(durationTimer)
      sendAudio(new Blob(audioChunks, { type: mediaRecorder.mimeType }))
    }

    mediaRecorder.start()
    isRecording.value = true
    recordDuration.value = 0
    durationTimer = setInterval(() => recordDuration.value++, 1000)
  } catch (err) {
    errorMsg.value = '无法访问麦克风，请检查浏览器权限'
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
  } else {
    startRecording()
  }
}

function getSupportedMimeType() {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  for (const t of types) {
    if (MediaRecorder.isTypeSupported(t)) return t
  }
  return ''
}

async function sendAudio(blob) {
  isLoading.value = true
  errorMsg.value = ''

  const ext = blob.type.includes('ogg') ? 'ogg' : blob.type.includes('mp4') ? 'm4a' : 'webm'
  const formData = new FormData()
  formData.append('file', blob, `recording.${ext}`)
  formData.append('dialect', 'minnan')

  try {
    const res = await fetch('/api/transcribe', { method: 'POST', body: formData })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '识别失败')
    resultText.value = data.text
    console.log('识别结果:', data.text)
  } catch (err) {
    errorMsg.value = err.message || '请求失败，请确认后端服务已启动'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="container">
    <header class="header">
      <h1>闽南话语音识别</h1>
      <p class="subtitle">基于 FunASR · Fun-ASR-Nano 方言识别</p>
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
        <span>{{ isRecording ? '停止录音' : isLoading ? '识别中...' : '开始录音' }}</span>
      </button>

      <div v-if="errorMsg" class="error">{{ errorMsg }}</div>

      <section v-if="resultText" class="result">
        <h2>识别结果</h2>
        <p class="result-text">{{ resultText }}</p>
      </section>

      <section v-else-if="!isLoading && !isRecording" class="hint">
        <p>请用闽南话对着麦克风说话，录音结束后自动识别并显示文字。</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.container {
  max-width: 560px;
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

.result {
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid #eee;
}

.result h2 {
  font-size: 16px;
  color: #888;
  margin-bottom: 12px;
}

.result-text {
  font-size: 22px;
  line-height: 1.6;
  color: #1a1a1a;
  word-break: break-all;
}

.hint {
  margin-top: 24px;
  text-align: center;
  color: #999;
  font-size: 14px;
  line-height: 1.6;
}
</style>
