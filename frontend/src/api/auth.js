import request from './request'

export const loginApi = (data) => request.post('/auth/login/', data)
export const logoutApi = () => request.post('/auth/logout/')
export const meApi = () => request.get('/auth/me/')
