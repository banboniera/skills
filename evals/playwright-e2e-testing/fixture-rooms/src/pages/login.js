/**
 * Login page (/login). Email and password are required; submitting sends POST /api/auth/login/ with {email, password}.
 * On 200 ({token, user}) the session is stored and the user goes to the `next` path, or /bookings.
 * On 400 the page shows "Wrong email or password" and stays.
 */
import { api, ApiError } from '../api.js'
import { setSession } from '../session.js'

export const mount = (root, { navigate }) => {
  root.innerHTML = `
    <h1>Sign in</h1>
    <form novalidate>
      <label>Email <input name="email" type="email" required /></label>
      <label>Password <input name="password" type="password" required /></label>
      <p class="field-error" role="alert" hidden></p>
      <button type="submit">Sign in</button>
    </form>`
  const form = root.querySelector('form')
  const error = form.querySelector('[role=alert]')
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const email = form.email.value.trim()
    const password = form.password.value
    if (!email || !password) {
      error.textContent = 'Enter your email and password'
      error.hidden = false
      return
    }
    try {
      const session = await api('POST', '/auth/login/', { body: { email, password } })
      setSession(session)
      navigate(new URLSearchParams(location.search).get('next') ?? '/bookings')
    } catch (failure) {
      error.textContent = failure instanceof ApiError && failure.status === 400 ? 'Wrong email or password' : 'Could not sign in, try again'
      error.hidden = false
    }
  })
}
