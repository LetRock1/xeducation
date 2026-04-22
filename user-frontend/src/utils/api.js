// frontend/src/utils/api.js
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

// 🔥 INTERCEPTOR - Automatically attaches token from localStorage (xe_token)
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('xe_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Optional: Auto-logout on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn("🔴 401 Unauthorized - Token expired or invalid");
      localStorage.removeItem('xe_token');
      localStorage.removeItem('xe_sid');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Export all your functions using this secured instance
export const signup        = (d) => api.post('/auth/signup', d);
export const verifyOtp     = (d) => api.post('/auth/verify-otp', d);
export const login         = (d) => api.post('/auth/login', d);
export const getMe         = () => api.get('/auth/me');
export const completeProfile = (d) => api.post('/profile/complete', d);
export const updatePrefs   = (d) => api.put('/profile/preferences', d);
export const startSession  = (d) => api.post('/session/start', d);
export const trackEvent    = (d) => api.post('/track', d);
export const getRecommendations = () => api.get('/recommendations');
export const getCart       = () => api.get('/cart');
export const addToCart     = (d) => api.post('/cart', d);
export const removeFromCart= (s) => api.delete(`/cart/${s}`);
export const getWishlist   = () => api.get('/wishlist');
export const addToWishlist = (d) => api.post('/wishlist', d);
export const removeFromWishlist = (s) => api.delete(`/wishlist/${s}`);
export const checkout      = (d) => api.post('/checkout', d);
export const getPurchases  = () => api.get('/purchases');
export const submitEnquiry = (d) => api.post('/enquiry', d);
export const getReviews    = (s) => api.get(`/reviews/${s}`);
export const addReview     = (d) => api.post('/reviews', d);
export const getQnA        = (s) => api.get(`/qna/${s}`);
export const askQuestion   = (d) => api.post('/qna', d);
export const getDashboard  = () => api.get('/dashboard');
export const getCoupons    = () => api.get('/coupons');

export default api;