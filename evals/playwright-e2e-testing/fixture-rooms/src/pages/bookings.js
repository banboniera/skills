/**
 * Bookings page (/bookings).
 *
 * - Shows one day's bookings: GET /api/bookings/?date=YYYY-MM-DD, answered with
 *   [{id, room: {id, name}, title, owner: {id, name}, starts_at, ends_at, status: "booked" | "cancelled"}], where the
 *   times are ISO 8601 instants in UTC. The page opens on today (the user's local date) and the heading reads
 *   "Bookings for YYYY-MM-DD"; "Previous day" and "Next day" move one day. Each booking shows its room, title, owner,
 *   and time as "HH:MM–HH:MM" in the user's local time, sorted by start time. A day without bookings shows
 *   "No bookings on this day"; a failed load shows the alert "Could not load bookings".
 * - "Only mine" adds `owner=me` to the request and stays on while moving between days.
 * - Members and admins see "Book a room", a dialog with Room (the rooms from GET /api/rooms/, [{id, name}]), Title,
 *   Start, and End (times of day on the shown day, in local time). The title is required and the end must be after
 *   the start; otherwise the error shows under the field and nothing is sent. "Book" sends POST /api/bookings/ with
 *   {room: <room id>, title (trimmed), starts_at, ends_at}, the times as UTC ISO instants. On 201 the dialog closes,
 *   "Room booked" is announced, and the day reloads. On 409 the dialog stays open and shows
 *   "That room is already booked then".
 * - A booking's owner, and any admin, sees "Cancel <title>" on a booking that is not cancelled. It asks
 *   "Cancel <title>?"; "Cancel booking" sends POST /api/bookings/<id>/cancel/, after which the booking shows
 *   "Cancelled" and has no cancel button. "Keep" sends nothing.
 * - Guests only see the bookings: no "Book a room" and no cancel buttons.
 */
import { api, ApiError } from '../api.js'
import { confirmDialog, escape, toast } from '../ui.js'

const pad = (n) => String(n).padStart(2, '0')
const formatDay = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
const shiftDay = (day, days) => {
  const [y, m, d] = day.split('-').map(Number)
  return formatDay(new Date(y, m - 1, d + days))
}
const clock = (iso) => {
  const date = new Date(iso)
  return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`
}

export const mount = async (root, { session }) => {
  const isAdmin = session.user.role === 'admin'
  const canBook = session.user.role !== 'guest'
  const canCancel = (booking) => isAdmin || session.user.role === 'member'
  const state = { day: formatDay(new Date()), mine: false }

  root.innerHTML = `
    <h1></h1>
    <div class="toolbar">
      <button type="button" id="prev-day">Previous day</button>
      <button type="button" id="next-day">Next day</button>
      <label><input type="checkbox" name="mine" /> Only mine</label>
      ${canBook ? '<button type="button" id="book">Book a room</button>' : ''}
    </div>
    <div id="list"></div>`

  const list = root.querySelector('#list')

  const row = (booking) => `
    <li data-id="${booking.id}">
      <strong>${escape(booking.title)}</strong> · ${escape(booking.room.name)} · ${escape(booking.owner.name)}
      · <time>${clock(booking.starts_at)}–${clock(booking.ends_at)}</time>
      ${booking.status === 'cancelled' ? ' · Cancelled' : ''}
      ${booking.status !== 'cancelled' && canCancel(booking) ? `<button type="button" data-cancel="${booking.id}">Cancel ${escape(booking.title)}</button>` : ''}
    </li>`

  const render = (bookings) => {
    if (bookings.length === 0) {
      list.innerHTML = '<p>No bookings on this day</p>'
      return
    }
    const sorted = [...bookings].sort((a, b) => a.starts_at.localeCompare(b.starts_at))
    list.innerHTML = `<ul aria-label="Bookings">${sorted.map(row).join('')}</ul>`
    list.bookings = sorted
  }

  const load = async () => {
    root.querySelector('h1').textContent = `Bookings for ${state.day}`
    try {
      render(await api('GET', '/bookings/', { query: { date: state.day, owner: state.mine ? 'me' : undefined } }))
    } catch {
      list.innerHTML = '<p role="alert">Could not load bookings</p>'
    }
  }

  root.querySelector('#prev-day').addEventListener('click', () => {
    state.day = shiftDay(state.day, -1)
    load()
  })
  root.querySelector('#next-day').addEventListener('click', () => {
    state.day = shiftDay(state.day, 1)
    load()
  })
  root.querySelector('input[name=mine]').addEventListener('change', (event) => {
    state.mine = event.target.checked
    load()
  })

  list.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-cancel]')
    if (!button) return
    const booking = list.bookings.find((b) => String(b.id) === button.dataset.cancel)
    if (!(await confirmDialog(`Cancel ${booking.title}?`, 'Cancel booking', 'Keep'))) return
    try {
      await api('POST', `/bookings/${booking.id}/cancel/`)
      booking.status = 'cancelled'
      button.closest('li').outerHTML = row(booking)
    } catch {
      toast('Could not cancel the booking')
    }
  })

  if (canBook) root.querySelector('#book').addEventListener('click', () => openBooking(state.day, load))
  await load()
}

const openBooking = async (day, reload) => {
  const rooms = await api('GET', '/rooms/')
  const dialog = document.createElement('dialog')
  dialog.setAttribute('aria-labelledby', 'book-title')
  dialog.innerHTML = `
    <h2 id="book-title">Book a room</h2>
    <form novalidate>
      <p><label>Room <select name="room">${rooms.map((r) => `<option value="${r.id}">${escape(r.name)}</option>`).join('')}</select></label></p>
      <p><label>Title <input name="title" /></label><span class="field-error" data-error="title"></span></p>
      <p><label>Start <input name="start" type="time" value="09:00" /></label></p>
      <p><label>End <input name="end" type="time" value="10:00" /></label><span class="field-error" data-error="end"></span></p>
      <p class="field-error" data-error="form"></p>
      <button type="button" data-close>Close</button>
      <button type="submit">Book</button>
    </form>`
  document.body.append(dialog)
  const form = dialog.querySelector('form')
  const close = () => {
    dialog.close()
    dialog.remove()
  }
  const showErrors = (errors) => {
    for (const slot of form.querySelectorAll('[data-error]')) slot.textContent = errors[slot.dataset.error] ?? ''
  }
  form.querySelector('[data-close]').addEventListener('click', close)
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const body = {
      room: Number(form.room.value),
      title: form.title.value.trim(),
      starts_at: new Date(`${day}T${form.start.value}`).toISOString(),
      ends_at: new Date(`${day}T${form.end.value}`).toISOString(),
    }
    const errors = {}
    if (!body.title) errors.title = 'Enter a title'
    if (body.ends_at < body.starts_at) errors.end = 'End after the start'
    showErrors(errors)
    if (Object.keys(errors).length) return
    try {
      await api('POST', '/bookings/', { body })
      close()
      toast('Room booked')
      reload()
    } catch (failure) {
      showErrors({ form: failure instanceof ApiError && failure.status === 409 ? 'That room is already booked then' : 'Could not book the room, try again' })
    }
  })
  dialog.showModal()
}
