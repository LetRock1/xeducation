import axios from 'axios'
const client = axios.create({ baseURL: '/api' })
client.interceptors.request.use(cfg => {
  cfg.headers.Authorization = `Bearer ${localStorage.getItem('mkt_token') || ''}`
  return cfg
})
// Session expired (tokens last 12 h) -> back to login instead of silently empty pages
client.interceptors.response.use(r => r, err => {
  if (err.response?.status === 401) {
    localStorage.removeItem('mkt_token')
    if (!window.location.pathname.startsWith('/login')) window.location.href = '/login'
  }
  return Promise.reject(err)
})
const a = () => client

export const mktLogin        = d  => axios.post('/api/mkt/login', d)
export const getStats        = () => a().get('/mkt/stats')
export const getModelHealth  = () => a().get('/mkt/model/health')
export const rescoreLead     = id => a().post(`/mkt/leads/${id}/rescore`)
export const getLeads        = (tier, search, sort) => {
  let q = []
  if (tier)   q.push(`tier=${encodeURIComponent(tier)}`)
  if (search) q.push(`search=${encodeURIComponent(search)}`)
  if (sort)   q.push(`sort=${encodeURIComponent(sort)}`)
  return a().get(`/mkt/leads${q.length?'?'+q.join('&'):''}`)
}
export const getLead         = id => a().get(`/mkt/leads/${id}`)
export const sendEmail       = d  => a().post('/mkt/send-email', d)
export const aiImprove       = d  => a().post('/mkt/ai-improve', d)
export const whatsappLink    = d  => a().post('/mkt/whatsapp', d)
export const getSmsQueue     = () => a().get('/mkt/sms-queue')
export const generateCoupon  = d  => a().post('/mkt/coupons/generate', d)
export const getAllCoupons    = () => a().get('/mkt/coupons')
export const scheduleCampaign= d  => a().post('/mkt/campaigns', d)
export const getCampaigns    = () => a().get('/mkt/campaigns')
export const getUnansweredQnA= () => a().get('/mkt/qna')
export const answerQnA       = d  => a().post('/mkt/qna/answer', d)
export const exportCsv       = () => a().get('/mkt/export-csv', { responseType:'blob' })
export const deleteCoupon   = id => a().delete(`/mkt/coupons/${id}`)
export const deleteCampaign = id => a().delete(`/mkt/campaigns/${id}`)

export const getLeadExplain     = id => a().get(`/mkt/leads/${id}/explain`)
export const getLeadAttribution = id => a().get(`/mkt/leads/${id}/attribution`)
export const getCampaignInfluence = () => a().get('/mkt/campaign-influence')
export const getPriorityQueue   = (limit) => a().get(`/mkt/priority-queue${limit ? `?limit=${limit}` : ''}`)

export const createAbTest   = d  => a().post('/mkt/ab-tests', d)
export const getAbTests     = () => a().get('/mkt/ab-tests')
export const sendAbTest     = id => a().post(`/mkt/ab-tests/${id}/send`)
export const getAbTestResults = id => a().get(`/mkt/ab-tests/${id}/results`)
export const planAbTest     = p  => a().get(`/mkt/ab-tests/plan?${new URLSearchParams(p).toString()}`)
export const applyAbWinner  = (id, d) => a().post(`/mkt/ab-tests/${id}/apply`, d)
export const deleteAbTest   = id => a().delete(`/mkt/ab-tests/${id}`)
export const getLearning    = () => a().get('/mkt/learning/overview')
export const runLearning    = (dryRun = false) => a().post(`/mkt/learning/run?dry_run=${dryRun}`)
export const getJourneys    = (days = 180, tier = '') => a().get(`/mkt/journeys?days=${days}${tier ? `&tier=${encodeURIComponent(tier)}` : ''}`)
export const getLeadPaths   = (id, depth = 2) => a().get(`/mkt/leads/${id}/paths?depth=${depth}`)
export const sendCampaignNow  = id => a().post(`/mkt/campaigns/${id}/send-now`)
export const getCallbacks     = (status = 'open') => a().get(`/mkt/callbacks?status=${status}`)
export const closeCallback    = id => a().post(`/mkt/callbacks/${id}/done`)
export const getActions       = (status = 'open') => a().get(`/mkt/actions?status=${status}`)
export const completeAction   = (id, outcome) => a().post(`/mkt/actions/${id}/done`, { outcome })
export const getNbaPerformance= () => a().get('/mkt/nba/performance')
export const runAutomations   = () => a().post('/mkt/run-automations')
export const getForecast      = () => a().get('/mkt/forecast')
export const getPipeline      = (p = {}) => a().get(`/mkt/pipeline?${new URLSearchParams(p).toString()}`)
export const moveCard         = (userId, d) => a().put(`/mkt/pipeline/${userId}`, d)
export const resetCard        = userId => a().delete(`/mkt/pipeline/${userId}`)
export const getAdoptions     = () => a().get('/mkt/adoptions')
export const checkAdoptions   = () => a().post('/mkt/adoptions/check')
export const revertAdoption   = id => a().post(`/mkt/adoptions/${id}/revert`)
export const askCopilot       = question => a().post('/mkt/copilot', { question })
export const getCopilotInfo   = () => a().get('/mkt/copilot')
