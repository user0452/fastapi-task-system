import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const authApi = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn()
}))
const courseApi = vi.hoisted(() => ({
  createCourse: vi.fn(),
  getCourses: vi.fn(),
  getCurrentCourse: vi.fn(),
  selectCourse: vi.fn()
}))

vi.mock('../api/auth', () => authApi)
vi.mock('../api/courses', () => courseApi)

import { useAuthStore } from './auth'
import { useCourseStore } from './course'


function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

describe('user session isolation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('clears the previous account and reloads courses after a new login', async () => {
    const auth = useAuthStore()
    const courses = useCourseStore()
    courses.courses = [{ id: 1, name: '旧账户课程' }]
    courses.current = courses.courses[0]
    courses.loaded = true
    localStorage.setItem('a3:course-draft:1', '旧账户草稿')
    authApi.login.mockResolvedValue({
      code: 200,
      data: { username: 'new-user' }
    })
    courseApi.getCourses.mockResolvedValue({
      code: 200,
      data: { items: [{ id: 2, name: '新账户课程' }] }
    })
    courseApi.getCurrentCourse.mockResolvedValue({
      code: 200,
      data: { id: 2, name: '新账户课程' }
    })

    await auth.login('new-user', 'password')

    expect(courses.courses).toEqual([])
    expect(courses.current).toBeNull()
    expect(courses.loaded).toBe(false)
    expect(localStorage.getItem('a3:course-draft:1')).toBeNull()

    await courses.ensureLoaded()
    expect(courses.courses.map(course => course.id)).toEqual([2])
    expect(courses.current.id).toBe(2)
  })

  it('invalidates an in-flight course load when authentication expires', async () => {
    const auth = useAuthStore()
    const courses = useCourseStore()
    const coursesRequest = deferred()
    const currentRequest = deferred()
    courseApi.getCourses.mockReturnValue(coursesRequest.promise)
    courseApi.getCurrentCourse.mockReturnValue(currentRequest.promise)

    const loading = courses.load()
    window.dispatchEvent(new CustomEvent('auth:expired'))
    coursesRequest.resolve({ code: 200, data: { items: [{ id: 9, name: '过期课程' }] } })
    currentRequest.resolve({ code: 200, data: { id: 9, name: '过期课程' } })
    await loading

    expect(auth.isLoggedIn).toBe(false)
    expect(courses.courses).toEqual([])
    expect(courses.current).toBeNull()
    expect(courses.loaded).toBe(false)
    expect(courses.loading).toBe(false)
  })

  it('coalesces concurrent course initialization after a page reload', async () => {
    const courses = useCourseStore()
    const coursesRequest = deferred()
    const currentRequest = deferred()
    courseApi.getCourses.mockReturnValue(coursesRequest.promise)
    courseApi.getCurrentCourse.mockReturnValue(currentRequest.promise)

    const shellLoad = courses.ensureLoaded()
    const workspaceLoad = courses.ensureLoaded()
    expect(courseApi.getCourses).toHaveBeenCalledTimes(1)
    expect(courseApi.getCurrentCourse).toHaveBeenCalledTimes(1)

    coursesRequest.resolve({ code: 200, data: { items: [{ id: 4, name: '刷新课程' }] } })
    currentRequest.resolve({ code: 200, data: { id: 4, name: '刷新课程' } })

    await expect(shellLoad).resolves.toMatchObject({ id: 4 })
    await expect(workspaceLoad).resolves.toMatchObject({ id: 4 })
    expect(courses.courses).toHaveLength(1)
    expect(courses.loaded).toBe(true)
  })
})
