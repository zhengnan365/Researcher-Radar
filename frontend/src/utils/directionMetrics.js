export const relevanceLevels = {
  1: '低相关',
  2: '较低相关',
  3: '一般相关',
  4: '重要相关',
  5: '核心研究方向',
}

export const priorityLevels = {
  1: '普通关注',
  2: '较低关注',
  3: '常规关注',
  4: '重点关注',
  5: '优先关注',
}

export const relevanceLevelText = (value) => relevanceLevels[value] || '-'
export const priorityLevelText = (value) => priorityLevels[value] || '-'
