/* A calendar's dates for the maps, as galaxy.calendar reads and writes them:
 * eras on one axis of years (the Gregorian year), dates written
 * `ERA YEAR[-MM[-DD]]`, with a fraction ("AD 523.5") or a day of the year
 * ("AD 523, day 120"). The definition is the system record's `calendar`
 * (galaxy.systemmap):
 *
 *   {eras: {BC: {zero: 0, direction: -1}, AD: {zero: 0, direction: 1}},
 *    written: [{era: 'AD', from: 1}, {era: 'BC'}]}
 *
 *   const cal = createCalendar(system.calendar)
 *   cal.read('AD 523, day 120')   // { absolute } or { error }
 *   cal.text(523.33)              // 'AD 523, day 121'
 */

const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
const YEAR_DAYS = 365.25

export const GREGORIAN = {
  eras: { BC: { zero: 0, direction: -1 }, AD: { zero: 0, direction: 1 } },
  written: [{ era: 'AD', from: 1 }, { era: 'BC' }],
}

const escapeRegExp = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export function createCalendar(definition = GREGORIAN) {
  const eras = definition.eras
  const names = Object.keys(eras)
  const example = (definition.written[0] || {}).era || names[0]
  const forms = `${example} 523.5, ${example} 523-04-12 or ${example} 523, day 120`
  const pattern = new RegExp(`^\\s*(${names.map(escapeRegExp).join('|')})\\s+(\\d+(?:\\.\\d+)?)`
    + '(?:-(\\d{1,2}))?(?:-(\\d{1,2}))?\\s*(?:,\\s*day\\s+(\\d+))?\\s*$', 'i')

  /* A date as the planner reads one (galaxy.calendar.Calendar.years): "AD
   * 523.5", as a timeline writes it ("AD 523-04-12", the start of the day)
   * or as a field shows it ("AD 523, day 120", its noon). { absolute } or
   * { error }, the reason in words. */
  function read(text) {
    const m = pattern.exec(text || '')
    if (!m) return { error: `Not a date: write it like ${forms}` }
    const [, eraText, yearText, month, dayOfMonth, dayOfYear] = m
    if ((month || dayOfYear) && yearText.includes('.')) return { error: 'A year with a fraction has no month or day' }
    if (month && dayOfYear) return { error: 'Either a month and day or a day of the year, not both' }
    const year = parseFloat(yearText)
    let within = 0
    if (month) {
      const mo = +month, d = dayOfMonth ? +dayOfMonth : 1
      if (mo < 1 || mo > 12) return { error: 'The month is 1–12' }
      if (d < 1 || d > MONTH_DAYS[mo - 1]) return { error: `Day ${d} is not in month ${mo} (1–${MONTH_DAYS[mo - 1]})` }
      within = (MONTH_DAYS.slice(0, mo - 1).reduce((a, b) => a + b, 0) + d - 1) / YEAR_DAYS
    } else if (dayOfYear) {
      const d = +dayOfYear
      if (d < 1 || d > 366) return { error: 'The day of the year is 1–366' }
      within = (d - 0.5) / YEAR_DAYS          // its noon, so that it shows again as the same day
    }
    // The era counts the years; a year's months and days run forward in every era.
    const era = names.find(name => name.toUpperCase() === eraText.toUpperCase())
    return { absolute: eras[era].zero + eras[era].direction * year + within }
  }

  /* A date on the axis as the maps show it (galaxy.calendar.Calendar.text). */
  function text(absolute) {
    // A day's start is that day, not a hair before.
    const whole = Math.floor(absolute), day = Math.floor((absolute - whole) * YEAR_DAYS + 1e-6) + 1
    const written = definition.written.find(w => w.from === undefined || w.from === null || whole >= w.from)
    const { zero, direction } = eras[written.era]
    return `${written.era} ${(whole - zero) * direction}, day ${day}`
  }

  /* A date on the axis as the planner reads it: an era and a decimal year
   * (galaxy.calendar.Calendar.years reads it back). */
  function param(absolute) {
    for (const w of definition.written) {
      const { zero, direction } = eras[w.era]
      const year = (absolute - zero) * direction
      if (year >= 0 && (w.from === undefined || w.from === null || absolute > w.from - 1)) {
        return `${w.era} ${year.toFixed(6)}`
      }
    }
    return `${definition.written[0].era} ${absolute.toFixed(6)}`
  }

  return { read, text, param, forms }
}
