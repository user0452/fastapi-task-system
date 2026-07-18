import { nextTick, onBeforeUnmount, ref, unref, watch } from 'vue'
import {
  archiveAgentSession,
  createAgentSession,
  decideAgentAction,
  getAgentSessions,
  getCourseAgentWorkspace,
  sendAgentMessageStream
} from '../../../api/agent'
import { showToast } from '../../../components/common/toast'


export function sessionDraftKey(courseId, sessionId) {
  return `a3:chat-draft:${courseId || 'general'}:${sessionId || 'new'}`
}

function successful(response) {
  return response?.code >= 200 && response.code < 300
}

export function useCourseAgentChat({
  courseId,
  route,
  router,
  scrollBottom = async () => {},
  focusInput = () => {},
  onDataChanged = () => {},
  onSessionSelected = () => {}
}) {
  const sessions = ref([])
  const activeId = ref(null)
  const session = ref(null)
  const agent = ref(null)
  const messages = ref([])
  const input = ref('')
  const loadingSessions = ref(false)
  const loadingMessages = ref(false)
  const sending = ref(false)
  const actionBusy = ref(false)
  const statusText = ref('')
  const loadError = ref('')
  let loadVersion = 0
  let streamVersion = 0
  let streamController = null
  let draftSyncPaused = false
  let routeSyncPaused = false
  let routeNavigationVersion = 0

  const currentCourseId = () => Number(unref(courseId)) || null

  function saveDraft() {
    if (draftSyncPaused) return
    const key = sessionDraftKey(currentCourseId(), activeId.value)
    if (input.value) localStorage.setItem(key, input.value)
    else localStorage.removeItem(key)
  }

  async function restoreDraft() {
    draftSyncPaused = true
    input.value = localStorage.getItem(
      sessionDraftKey(currentCourseId(), activeId.value)
    ) || ''
    await nextTick()
    draftSyncPaused = false
  }

  async function syncSessionQuery(sessionId) {
    if (!route || !router || routeSyncPaused) return
    const current = Number(route.query?.session) || null
    const next = Number(sessionId) || null
    if (current === next) return
    const query = { ...(route.query || {}) }
    if (next) query.session = String(next)
    else delete query.session
    routeSyncPaused = true
    try {
      await router.replace({ path: route.path, query })
    } finally {
      routeSyncPaused = false
    }
  }

  function cancelStream() {
    streamVersion += 1
    streamController?.abort()
    streamController = null
    sending.value = false
    statusText.value = ''
  }

  async function loadWorkspace(
    sessionId = null,
    { syncRoute = true, reportError = true } = {}
  ) {
    const requestedCourseId = currentCourseId()
    if (!requestedCourseId) return false
    const version = ++loadVersion
    loadingMessages.value = true
    loadError.value = ''
    try {
      const params = { message_limit: 100 }
      if (sessionId) params.session_id = Number(sessionId)
      const response = await getCourseAgentWorkspace(requestedCourseId, params)
      if (version !== loadVersion || requestedCourseId !== currentCourseId()) return false
      if (!successful(response)) throw new Error(response?.message || '课程会话加载失败')
      session.value = response.data.session
      activeId.value = Number(response.data.session.id)
      agent.value = response.data.agent
      messages.value = response.data.messages || []
      await restoreDraft()
      if (syncRoute) await syncSessionQuery(activeId.value)
      await scrollBottom()
      return true
    } catch (error) {
      if (version !== loadVersion) return false
      if (reportError) {
        loadError.value = error.message || '课程会话加载失败'
        showToast({ type: 'error', message: loadError.value })
      }
      return false
    } finally {
      if (version === loadVersion) loadingMessages.value = false
    }
  }

  async function loadLatestSession() {
    const fallback = sessions.value[0] || null
    if (fallback) {
      if (Number(fallback.id) === Number(activeId.value)) return true
      return selectSession(fallback, { syncRoute: false, notify: false })
    }
    const loaded = await loadWorkspace(null, { syncRoute: false })
    if (loaded) await loadSessions({ select: false })
    return loaded
  }

  async function loadSessions({ preferredId = null, select = true } = {}) {
    const requestedCourseId = currentCourseId()
    if (!requestedCourseId) return
    loadingSessions.value = true
    try {
      const response = await getAgentSessions({
        page: 1,
        size: 100,
        course_id: requestedCourseId
      })
      if (requestedCourseId !== currentCourseId()) return
      if (!successful(response)) throw new Error(response?.message || '历史会话加载失败')
      sessions.value = response.data?.items || []
      if (!select) return
      const requestedId = Number(preferredId) || null
      if (requestedId) {
        const preferred = sessions.value.find(item => Number(item.id) === requestedId)
        if (preferred) {
          await selectSession(preferred, { syncRoute: false, notify: false })
          return
        }
        const loaded = await loadWorkspace(requestedId, {
          syncRoute: false,
          reportError: false
        })
        if (loaded) {
          if (!sessions.value.some(item => Number(item.id) === requestedId)) {
            sessions.value = [session.value, ...sessions.value]
          }
          return
        }
        await syncSessionQuery(null)
      }
      if (await loadLatestSession()) {
        return
      }
    } catch (error) {
      loadError.value = error.message || '历史会话加载失败'
      showToast({ type: 'error', message: loadError.value })
    } finally {
      loadingSessions.value = false
    }
  }

  async function selectSession(nextSession, { syncRoute = true, notify = true } = {}) {
    const nextId = Number(nextSession?.id)
    if (!nextId) return false
    saveDraft()
    cancelStream()
    activeId.value = nextId
    session.value = nextSession
    messages.value = []
    await restoreDraft()
    const loaded = await loadWorkspace(nextId, { syncRoute })
    if (loaded && notify) onSessionSelected(nextSession)
    return loaded
  }

  async function newSession() {
    saveDraft()
    cancelStream()
    const response = await createAgentSession({
      course_id: currentCourseId(),
      title: '新对话'
    })
    if (!successful(response)) {
      showToast({ type: 'error', message: response?.message || '新建会话失败' })
      return null
    }
    session.value = response.data
    activeId.value = Number(response.data.id)
    messages.value = []
    await restoreDraft()
    await syncSessionQuery(activeId.value)
    await loadSessions({ select: false })
    onSessionSelected(response.data)
    focusInput()
    return response.data
  }

  async function archiveSession(target) {
    if (!target?.id) return false
    if (!window.confirm(`归档对话“${target.title}”？`)) return false
    const response = await archiveAgentSession(target.id)
    if (!successful(response)) {
      showToast({ type: 'error', message: response?.message || '归档会话失败' })
      return false
    }
    localStorage.removeItem(sessionDraftKey(currentCourseId(), target.id))
    if (Number(activeId.value) === Number(target.id)) {
      cancelStream()
      activeId.value = null
      session.value = null
      messages.value = []
      await syncSessionQuery(null)
      await loadSessions({ select: true })
    } else {
      await loadSessions({ select: false })
    }
    return true
  }

  async function send(textOverride = '') {
    const text = String(textOverride || input.value).trim()
    if (!text || sending.value || !currentCourseId()) return
    const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    const assistantId = `local-assistant-${requestId}`
    const requestCourseId = currentCourseId()
    const requestSessionId = Number(activeId.value) || null
    messages.value.push({
      id: `local-user-${requestId}`,
      role: 'user',
      content: text,
      sources: []
    })
    input.value = ''
    saveDraft()
    messages.value.push({
      id: assistantId,
      role: 'assistant',
      content: '',
      sources: [],
      tool_calls: {},
      streaming: true
    })
    sending.value = true
    statusText.value = '正在读取课程上下文'
    await scrollBottom('smooth')

    let received = null
    const controller = new AbortController()
    streamController?.abort()
    streamController = controller
    const requestVersion = ++streamVersion
    const isCurrentRequest = () => (
      requestVersion === streamVersion
      && requestCourseId === currentCourseId()
      && requestSessionId === Number(activeId.value)
      && !controller.signal.aborted
    )
    const currentAssistant = () => (
      isCurrentRequest()
        ? messages.value.find(message => message.id === assistantId)
        : null
    )
    try {
      await sendAgentMessageStream(
        {
          message: text,
          session_id: requestSessionId,
          course_id: requestCourseId,
          client_request_id: requestId
        },
        {
          onStatus(message) {
            if (isCurrentRequest()) statusText.value = message
          },
          onDelta(delta) {
            const assistant = currentAssistant()
            if (!assistant) return
            assistant.content += delta
            scrollBottom()
          },
          onResult(result) {
            const assistant = currentAssistant()
            if (!assistant) return
            received = result
            session.value = result.session
            agent.value = result.agent || agent.value
            const assistantIndex = messages.value.findIndex(
              message => message.id === assistantId
            )
            if (assistantIndex < 0) return
            messages.value[assistantIndex] = {
              ...result.message,
              content: result.reply || assistant.content,
              streaming: false
            }
          },
          onDone() {
            if (isCurrentRequest()) statusText.value = ''
          }
        },
        { signal: controller.signal }
      )
      if (!isCurrentRequest()) return
      await loadSessions({ select: false })
    } catch (error) {
      if (error.name === 'AbortError' || controller.signal.aborted) return
      const assistant = currentAssistant()
      if (!assistant) return
      const assistantIndex = messages.value.findIndex(message => message.id === assistantId)
      if (assistantIndex < 0) return
      messages.value[assistantIndex] = {
        ...assistant,
        content: `请求失败：${error.message}`,
        streaming: false
      }
    } finally {
      if (isCurrentRequest()) {
        if (streamController === controller) streamController = null
        const assistant = currentAssistant()
        if (!received && assistant) assistant.streaming = false
        sending.value = false
        statusText.value = ''
        onDataChanged(received?.intent || 'chat')
        await scrollBottom()
      }
    }
  }

  async function decide(confirmation, confirmed) {
    if (actionBusy.value) return
    actionBusy.value = true
    try {
      const response = await decideAgentAction(confirmation.id, confirmed)
      if (!successful(response)) throw new Error(response?.message || '操作处理失败')
      showToast({
        type: confirmed ? 'success' : 'info',
        message: confirmed ? '操作已执行' : '操作已取消'
      })
      await loadWorkspace(activeId.value)
      await loadSessions({ select: false })
      onDataChanged('action')
    } catch (error) {
      showToast({ type: 'error', message: error.message || '操作处理失败' })
    } finally {
      actionBusy.value = false
    }
  }

  async function initialize({ useRouteSession = true } = {}) {
    const preferredId = useRouteSession ? Number(route?.query?.session) || null : null
    await loadSessions({ preferredId, select: true })
  }

  async function switchCourse() {
    saveDraft()
    cancelStream()
    loadVersion += 1
    routeNavigationVersion += 1
    sessions.value = []
    activeId.value = null
    session.value = null
    agent.value = null
    messages.value = []
    statusText.value = ''
    await restoreDraft()
    await syncSessionQuery(null)
    await initialize({ useRouteSession: false })
  }

  async function reconcileRouteSession(value) {
    if (routeSyncPaused) return
    const navigationVersion = ++routeNavigationVersion
    const requestedId = Number(value) || null
    if (requestedId === Number(activeId.value)) return

    if (!requestedId) {
      await loadLatestSession()
      return
    }

    const target = sessions.value.find(item => Number(item.id) === requestedId)
    if (target) {
      await selectSession(target, { syncRoute: false })
      return
    }

    saveDraft()
    cancelStream()
    const loaded = await loadWorkspace(requestedId, {
      syncRoute: false,
      reportError: false
    })
    if (navigationVersion !== routeNavigationVersion) return
    if (loaded) {
      if (!sessions.value.some(item => Number(item.id) === requestedId)) {
        sessions.value = [session.value, ...sessions.value]
      }
      onSessionSelected(session.value)
      return
    }

    await syncSessionQuery(null)
    if (navigationVersion !== routeNavigationVersion) return
    await loadLatestSession()
  }

  watch(input, saveDraft)

  if (route) {
    watch(
      () => route.query?.session,
      reconcileRouteSession
    )
  }

  onBeforeUnmount(() => {
    saveDraft()
    loadVersion += 1
    routeNavigationVersion += 1
    cancelStream()
  })

  return {
    sessions,
    activeId,
    session,
    agent,
    messages,
    input,
    loadingSessions,
    loadingMessages,
    sending,
    actionBusy,
    statusText,
    loadError,
    initialize,
    switchCourse,
    selectSession,
    newSession,
    archiveSession,
    cancelStream,
    send,
    decide
  }
}
