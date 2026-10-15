import request from './request'

export const getDirections = (params = {}) => request.get('/directions/', { params })
export const createDirection = (data) => request.post('/directions/', data)
export const bulkCreateDirections = (data) => request.post('/directions/bulk-create/', data)
export const bulkDeleteDirections = (ids) => request.post('/directions/bulk-delete/', { ids })
export const updateDirection = (id, data) => request.put(`/directions/${id}/`, data)
export const deleteDirection = (id) => request.delete(`/directions/${id}/`)
