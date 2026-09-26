import { clearSession, getSession } from './session.js'

export class ApiError extends Error {
  constructor(status, body) {
    super(`API answered ${status}`)
    this.status = status
    this.body = body
  }
}

/** Calls the backend with the session token. A 401 ends the session and sends the user to the login page. */
export const api = async (method, path, { query, body } = {}) => {
  const url = new URL(`/api${path}`, location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== '') url.searchParams.set(key, value)
  }
  const headers = { accept: 'application/json' }
  const token = getSession()?.token
  if (token) headers.authorization = `Token ${token}`
  if (body !== undefined) headers['content-type'] = 'application/json'
  const response = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (response.status === 401 && path !== '/auth/login/') {
    clearSession()
    location.assign(`/login?next=${encodeURIComponent(location.pathname)}`)
  }
  if (!response.ok) throw new ApiError(response.status, data)
  return data
}
