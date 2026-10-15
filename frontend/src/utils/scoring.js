export const levelMap = {
  key: '重点推荐',
  normal: '一般推荐',
  weak: '弱相关',
  low: '低相关',
}

export const fieldMap = {
  title: '标题',
  abstract: '摘要',
  raw_keywords: 'RSS 关键词',
}

export function levelText(level) {
  return levelMap[level] || level || '未评分'
}

export function levelType(level) {
  return { key: 'primary', normal: 'success', weak: 'warning', low: 'info' }[level] || 'info'
}

export function scoreTitle(paper) {
  return `${paper?.recommend_score ?? 0} 分｜${levelText(paper?.recommend_level)}`
}

export function fieldText(field) {
  return fieldMap[field] || field
}

export function matchedKeywordNames(paper, limit = 5) {
  const names = paper?.matched_keywords?.length
    ? paper.matched_keywords
    : paper?.keywords?.map((item) => item.keyword) || []
  const clean = [...new Set(names.filter(Boolean))]
  const head = clean.slice(0, limit)
  const extra = clean.length - head.length
  return extra > 0 ? `${head.join('、')} 等 ${extra} 个` : head.join('、')
}

export function matchedDirectionNames(paper, limit = 4) {
  const names = paper?.matched_directions?.length
    ? paper.matched_directions
    : paper?.directions?.map((item) => item.name) || []
  const clean = [...new Set(names.filter(Boolean))]
  const head = clean.slice(0, limit)
  const extra = clean.length - head.length
  return extra > 0 ? `${head.join('、')} 等 ${extra} 个` : head.join('、')
}

export function matchedFieldSummary(paper, limit = 4) {
  const matched = paper?.matched_fields || {}
  const fields = []
  Object.values(matched).forEach((items) => {
    ;(items || []).forEach((item) => fields.push(fieldText(item)))
  })
  const clean = [...new Set(fields)]
  const head = clean.slice(0, limit)
  const extra = clean.length - head.length
  return extra > 0 ? `${head.join('、')} 等 ${extra} 个字段` : head.join('、')
}

export function hitSummary(paper, limit = 3) {
  const matched = paper?.matched_fields || {}
  const entries = Object.entries(matched).slice(0, limit)
  if (!entries.length) return '暂无命中内容'
  const text = entries
    .map(([keyword, fields]) => `${(fields || []).map(fieldText).join('/')}：${keyword}`)
    .join('；')
  const extra = Object.keys(matched).length - entries.length
  return extra > 0 ? `${text}；等 ${extra} 个` : text
}

export function recommendationReason(paper) {
  const keywords = matchedKeywordNames(paper, 3)
  const fields = matchedFieldSummary(paper, 3)
  const directions = matchedDirectionNames(paper, 2)
  const parts = []
  if (keywords) parts.push(`命中关键词：${keywords}`)
  if (fields) parts.push(`命中字段：${fields}`)
  if (directions) parts.push(`匹配方向：${directions}`)
  return parts.join('；') || '暂无明确命中内容'
}
