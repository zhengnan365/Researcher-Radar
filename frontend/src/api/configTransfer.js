import request from './request'

export const exportSystemConfig = () => request.get('/settings/config/export/', {
  responseType: 'blob',
  timeout: 60000,
})

export const importSystemConfig = (data) => request.post('/settings/config/import/', data, {
  timeout: 120000,
})
