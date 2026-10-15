import request from './request'

export const syncZoteroLibrary = (data) => request.post('/zotero/sync/', data)
export const readZoteroLibrary = (data) => request.post('/zotero/library/', data, { timeout: 30000 })
export const getZoteroLibraryItems = (params) => request.get('/zotero/library/items/', { params, timeout: 30000 })
export const getZoteroItem = (key) => request.get(`/zotero/items/${encodeURIComponent(key)}/`)
export const getZoteroSyncStatus = () => request.get('/zotero/sync-status/', { timeout: 15000 })
export const createZoteroCollection = (data) => request.post('/zotero/create-collection/', data)
export const importPaperToZotero = (data) => request.post('/zotero/import-paper/', data)
export const suggestZoteroCollection = (data) => request.post('/zotero/suggest-collection/', data)
export const getZoteroConfig = () => request.get('/zotero/config/')
export const saveZoteroConfig = (data) => request.post('/zotero/config/', data)
