import request from './request'

export const getAiSettings = () => request.get('/settings/ai/')
export const saveAiSettings = (data) => request.post('/settings/ai/', data)
