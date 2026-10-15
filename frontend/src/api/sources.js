import request from './request'

export const getSources = (params = {}) => request.get('/sources/', { params })
export const createSource = (data) => request.post('/sources/', data)
export const bulkCreateSources = (data) => request.post('/sources/bulk-create/', data)
export const bulkDeleteSources = (ids) => request.post('/sources/bulk-delete/', { ids })
export const updateSource = (id, data) => request.put(`/sources/${id}/`, data)
export const deleteSource = (id) => request.delete(`/sources/${id}/`)
export const testSource = (id) => request.post(`/sources/${id}/test/`)
