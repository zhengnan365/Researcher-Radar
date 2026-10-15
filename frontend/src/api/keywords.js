import request from './request'

export const getKeywords = (params = {}) => request.get('/keywords/', { params })
export const createKeyword = (data) => request.post('/keywords/', data)
export const bulkCreateKeywords = (data) => request.post('/keywords/bulk-create/', data)
export const bulkDeleteKeywords = (ids) => request.post('/keywords/bulk-delete/', { ids })
export const updateKeyword = (id, data) => request.put(`/keywords/${id}/`, data)
export const deleteKeyword = (id) => request.delete(`/keywords/${id}/`)
