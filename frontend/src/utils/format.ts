import dayjs from 'dayjs'

/** YYYY-MM-DD */
export function fmtDate(v?: string | null): string {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD') : String(v)
}

/** YYYY-MM-DD HH:mm */
export function fmtDateTime(v?: string | null): string {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : String(v)
}

/** YYYY-MM-DD HH:mm:ss */
export function fmtDateTimeFull(v?: string | null): string {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

/** 文件大小人性化显示 */
export function fmtSize(bytes?: number | null): string {
  if (bytes === null || bytes === undefined || isNaN(bytes)) return '-'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = bytes / 1024
  let i = 0
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(size >= 100 ? 0 : 1)} ${units[i]}`
}

/** 毫秒时长人性化显示 */
export function fmtDuration(ms?: number | null): string {
  if (ms === null || ms === undefined || isNaN(ms)) return '-'
  if (ms < 1000) return `${ms}ms`
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ${sec % 60}s`
  const hour = Math.floor(min / 60)
  return `${hour}h ${min % 60}m`
}
