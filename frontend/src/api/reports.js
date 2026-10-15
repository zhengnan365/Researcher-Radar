import request from './request'

export const getReports = (params = {}) => request.get('/reports/', { params })
export const getReport = (id) => request.get(`/reports/${id}/`)
export const regenerateReport = (report_date) => request.post('/reports/regenerate/', { report_date })
export const startFetchDailyTask = () => request.post('/tasks/fetch-daily/', {}, { timeout: 60000 })
export const getActiveFetchDailyTask = () => request.get('/tasks/fetch-daily/active/')
export const getFetchDailyTask = (taskId) => request.get(`/tasks/fetch-daily/${taskId}/`)
export const fetchDailyNow = startFetchDailyTask
