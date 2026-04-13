import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const loginUser = async (email: string, password: string) => {
  const formData = new URLSearchParams();
  formData.append('username', email); // FastAPI OAuth2 expects 'username'
  formData.append('password', password);

  const { data } = await axios.post(`${API_URL}/auth/login`, formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return data; // { access_token, token_type }
};

export const signupUser = async (email: string, password: string) => {
  const { data } = await axios.post(`${API_URL}/auth/signup`, { email, password });
  return data;
};

export const getMe = async (token: string) => {
  const { data } = await axios.get(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data;
};
