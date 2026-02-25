import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'

const BASE = 'http://localhost:8000/api'

const api = axios.create({ baseURL: BASE })

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (err: unknown) => void
}> = []

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((p) => (token ? p.resolve(token) : p.reject(error)))
  failedQueue = []
}

api.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const original = err.config as InternalAxiosRequestConfig & { _retry?: boolean }

    if (err.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              if (original.headers) original.headers.Authorization = `Bearer ${token}`
              resolve(api(original))
            },
            reject,
          })
        })
      }
      original._retry = true
      isRefreshing = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (!refreshToken) {
        clearAuthAndRedirect()
        return Promise.reject(err)
      }

      try {
        const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
          `${BASE}/auth/refresh`,
          { refresh_token: refreshToken }
        )
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        processQueue(null, data.access_token)
        if (original.headers) original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch (refreshErr) {
        processQueue(refreshErr, null)
        clearAuthAndRedirect()
        return Promise.reject(refreshErr)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(err)
  }
)

function clearAuthAndRedirect() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  window.location.href = '/login'
}

// Types
export type PDFItem = {
  id: string
  name: string
  size_bytes: number
  page_count: number | null
  status: string
  version: number
  created_at: string
  updated_at: string | null
}

export type PDFListResponse = {
  items: PDFItem[]
  total: number
  page: number
  size: number
}

export type UploadFileItem = {
  pdf_id: string
  filename: string
  status: string
  task_id: string
}

export type TaskStatus = {
  task_id: string
  state: string
  result: unknown
  progress: number | null
}

export type UserProfile = {
  id: string
  email: string
  display_name: string
  created_at: string
  updated_at: string | null
}

export type TextBlock = {
  text: string
  x: number
  y: number
  width: number
  height: number
  font_family: string
  font_size: number
  bold: boolean
  italic: boolean
  raw_font: string
}

export type VersionItem = {
  id: string
  version: number
  saved_at: string
  saved_by: string
}

export type LogItem = {
  id: string
  timestamp: string
  level: string
  module: string
  event: string
  user_id: string | null
  metadata: Record<string, unknown>
  error: string | null
}

// Auth API
export const auth = {
  signup: (email: string, displayName: string, password: string) =>
    api.post<{ id: string; email: string; display_name: string }>('/auth/signup', {
      email,
      display_name: displayName,
      password,
    }),

  login: (email: string, password: string) =>
    api.post<{ access_token: string; refresh_token: string }>('/auth/login', { email, password }),

  logout: (refreshToken: string) =>
    api.post('/auth/logout', { refresh_token: refreshToken }),

  refreshToken: (refreshToken: string) =>
    api.post<{ access_token: string; refresh_token: string }>('/auth/refresh', {
      refresh_token: refreshToken,
    }),
}

// PDFs API
export const pdfs = {
  listPdfs: (page = 1, size = 20) =>
    api.get<PDFListResponse>('/pdfs', { params: { page, size } }),

  getPdf: (id: string) => api.get<PDFItem>(`/pdfs/${id}`),

  uploadPdfs: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return api.post<{ files: UploadFileItem[]; total: number }>('/pdfs/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  streamUrl: (id: string) => `${BASE.replace('/api', '')}/api/pdfs/${id}/stream`,

  rename: (id: string, name: string) =>
    api.patch<PDFItem>(`/pdfs/${id}`, { name }),

  deletePdf: (id: string) => api.delete(`/pdfs/${id}`),

  getDimensions: (id: string) =>
    api.get<{ pages: { page: number; width_pts: number; height_pts: number }[] }>(`/pdfs/${id}/dimensions`),

  getTextContent: (id: string, page: number) =>
    api.get<{ page: number; blocks: TextBlock[] }>(`/pdfs/${id}/text-content`, { params: { page } }),

  editPdf: (
    id: string,
    operations: Array<
      | { type: 'text'; page: number; x: number; y: number; text: string; font_family?: string; font_size?: number; bold?: boolean; italic?: boolean; color_hex?: string; rotation?: number }
      | { type: 'highlight'; page: number; x: number; y: number; width: number; height: number; color_hex?: string; opacity?: number }
      | { type: 'erase'; page: number; x: number; y: number; width: number; height: number; fill_color?: string }
      | { type: 'shape'; shape_type: 'rectangle' | 'line'; page: number; x: number; y: number; width: number; height: number; stroke_color?: string; fill_color?: string | null; stroke_width?: number }
      | { type: 'draw'; page: number; path: string; color_hex?: string; stroke_width?: number }
      | { type: 'page'; action: 'delete' | 'rotate' | 'reorder'; page: number; rotate_degrees?: number; new_order?: number[] }
    >,
    comment?: string
  ) =>
    api.post<{ pdf_id: string; version: number; task_id: string }>(`/pdfs/${id}/edit`, {
      operations,
      comment,
    }),

  getVersions: (id: string) =>
    api.get<VersionItem[]>(`/pdfs/${id}/versions`),

  getTaskStatus: (taskId: string) =>
    api.get<TaskStatus>(`/pdfs/tasks/${taskId}`),
}

// Users API
export const users = {
  getMe: () => api.get<UserProfile>('/users/me'),

  updateProfile: (data: {
    display_name?: string
    email?: string
    current_password?: string
    new_password?: string
  }) => api.patch<UserProfile>('/users/me', data),
}

// Logs API
export const logs = {
  getLogs: (filters: { level?: string; module?: string } = {}, page = 1, size = 50) =>
    api.get<{ items: LogItem[]; total: number; page: number; size: number }>('/logs/', {
      params: { ...filters, page, size },
    }),
}

export { api }
