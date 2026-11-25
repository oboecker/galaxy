/* The search box of every 3D map: at the top in the middle, its results under it — names that begin
 * with what is typed first ("Io" before "Dione"); Enter or a click takes a
 * result. Each map gives its items and what taking one does. Styles:
 * space.css.
 *
 *   const search = createSearch(bar, { placeholder, items, title, detail, choose })
 */

const LIMIT = 10

export function createSearch(bar, { placeholder = 'Search…', items, title, detail = () => '', choose, limit = LIMIT }) {
  const wrap = document.createElement('div')
  wrap.className = 'space-search-wrap'
  wrap.innerHTML = `<input type="text" class="space-search-box" autocomplete="off" spellcheck="false">
    <div class="space-search-results" hidden></div>`
  bar.prepend(wrap)
  const box = wrap.querySelector('.space-search-box')
  const results = wrap.querySelector('.space-search-results')
  box.placeholder = placeholder
  box.setAttribute('aria-label', placeholder.replace(/[.…]+$/, ''))

  function found(query) {
    const q = query.trim().toLowerCase()
    if (!q) return []
    const starts = item => title(item).toLowerCase().startsWith(q)
    return items().filter(item => title(item).toLowerCase().includes(q))
      .sort((a, b) => starts(b) - starts(a)).slice(0, limit)
  }
  function take(item) {
    box.value = title(item)
    results.hidden = true
    choose(item)
  }
  function list() {
    const hits = found(box.value)
    results.replaceChildren(...hits.map(item => {
      const row = document.createElement('div')
      row.className = 'space-search-item'
      const name = document.createElement('div')
      name.className = 'space-search-name'
      name.textContent = title(item)
      const more = document.createElement('div')
      more.className = 'space-search-details'
      more.textContent = detail(item)
      row.append(name, more)
      row.addEventListener('click', () => take(item))
      return row
    }))
    results.hidden = !hits.length
  }
  box.addEventListener('input', list)
  box.addEventListener('focus', () => { if (box.value) list() })
  box.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      const first = found(box.value)[0]
      if (first) take(first)
    } else if (event.key === 'Escape') {
      results.hidden = true
      box.blur()
    }
  })
  const outside = event => { if (!wrap.contains(event.target)) results.hidden = true }
  document.addEventListener('click', outside)

  return {
    box,
    // Set from outside (a star picked on the map), without searching.
    show(text) { box.value = text; results.hidden = true },
    dispose() { document.removeEventListener('click', outside); wrap.remove() },
  }
}
