// The signed-in user lives in localStorage under "session": {"token": "...", "user": {"name": "...", "role": "manager" | "viewer"}}.
export const getSession = () => {
  try {
    return JSON.parse(localStorage.getItem('session') ?? 'null')
  } catch {
    return null
  }
}

export const setSession = (session) => localStorage.setItem('session', JSON.stringify(session))

export const clearSession = () => localStorage.removeItem('session')
