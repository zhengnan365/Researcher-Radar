import request from './request'

export const getScoringSettings = () => request.get('/settings/scoring/')
export const saveScoringSettings = (data) => request.post('/settings/scoring/', data, { timeout: 300000 })
export const resetScoringSettings = () => request.post('/settings/scoring/reset/')
export const getScoringDistribution = (params = {}) => request.get('/settings/scoring/distribution/', { params })
export const startScoringRescore = (scope = 'all') => request.post('/settings/scoring/rescore/', { scope })
export const getActiveScoringRescore = () => request.get('/settings/scoring/rescore/active/')
export const getScoringRescoreStatus = (taskId) => request.get(`/settings/scoring/rescore/${taskId}/`)
