export const escape = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

let toastTimer
/** Announces a short message in the page's status region. */
export const toast = (message) => {
  const region = document.getElementById('toast')
  region.textContent = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { region.textContent = '' }, 5000)
}

/** Opens a modal confirmation and resolves to true when the user confirms. */
export const confirmDialog = (question, confirmLabel) =>
  new Promise((resolve) => {
    const dialog = document.createElement('dialog')
    dialog.setAttribute('role', 'alertdialog')
    dialog.setAttribute('aria-labelledby', 'confirm-question')
    dialog.innerHTML = `<p id="confirm-question">${escape(question)}</p>
      <button type="button" data-answer="no">Cancel</button>
      <button type="button" data-answer="yes">${escape(confirmLabel)}</button>`
    document.body.append(dialog)
    dialog.addEventListener('click', (event) => {
      const answer = event.target.closest('button')?.dataset.answer
      if (!answer) return
      dialog.close()
      dialog.remove()
      resolve(answer === 'yes')
    })
    dialog.addEventListener('cancel', () => { dialog.remove(); resolve(false) })
    dialog.showModal()
  })
