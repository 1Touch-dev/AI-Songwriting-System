import axios from 'axios';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
});

export const searchArtists = async (query: string) => {
  const { data } = await api.get(`/search-artists?q=${query}`);
  return data.results as string[];
};

export const generateLyrics = async (payload: any) => {
  const { data } = await api.post('/generate', payload);
  return data;
};

export const generateVoice = async (text: string, voiceId?: string) => {
  const { data } = await api.post('/generate-voice', { text, voice_id: voiceId }, { responseType: 'blob' });
  return URL.createObjectURL(data);
};

export const generateMusic = async (lyrics: string, styleTags: string, title: string) => {
  const { data } = await api.post('/generate-music', { lyrics, style_tags: styleTags, title });
  return data.audio_urls as string[];
};

export default api;
