import { getSession } from './session.js'
import { escape } from './ui.js'

const routes = [
  [/^\/login$/, () => import('./pages/login.js'), { public: true }],
  [/^\/bookings$/, () => import('./pages/bookings.js')],
]

export const navigate = (path) => {
  history.pushState(null, '', path)
  render()
}

const render = async () => {
  const main = document.getElementById('app')
  const session = getSession()
  document.getElementById('user').textContent = session ? `${session.user.name} (${session.user.role})` : ''
  if (location.pathname === '/') return navigate(session ? '/bookings' : '/login')
  const match = routes.find(([pattern]) => pattern.test(location.pathname))
  if (!match) {
    main.innerHTML = '<h1>Page not found</h1>'
    return
  }
  const [pattern, load, options = {}] = match
  if (!options.public && !session) {
    return navigate(`/login?next=${encodeURIComponent(location.pathname)}`)
  }
  const page = await load()
  main.innerHTML = ''
  try {
    await page.mount(main, { params: location.pathname.match(pattern).slice(1), session, navigate })
  } catch (error) {
    main.innerHTML = `<p role="alert">Something went wrong: ${escape(error.message)}</p>`
  }
}

addEventListener('popstate', render)
render()
