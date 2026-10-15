import request from './request'

export const getFetchLogs = (params = {}) => request.get('/fetch_logs/', { params })
