import axios from 'axios'
const tok = () => localStorage.getItem('mkt_token') || ''
const a   = () => axios.create({ baseURL:'/api', headers: { Authorization: `Bearer ${tok()}` } })

export const mktLogin        = d  => axios.post('/api/mkt/login', d)
export const getStats        = () => a().get('/mkt/stats')
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
export const queueSms        = d  => a().post('/mkt/sms-queue', d)
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
export const seedAbTestDemo   = (id, perVariant = 8) => a().post(`/mkt/ab-tests/${id}/seed-demo?per_variant=${perVariant}`)