import axios from 'axios';
import { useStore } from '@/store/useStore';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
});

// Request interceptor to attach JWT token
api.interceptors.request.use((config) => {
  const token = useStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
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

// --- Custom JWT Persistence ---

export const saveSong = async (song: any) => {
  const { data } = await api.post('/songs/save', { 
    theme: song.theme,
    artists: song.artists,
    lyrics: song.lyrics,
    audio_url: song.audio_url,
    music_url: song.music_url
  });
  return data;
};

export const getUserSongs = async () => {
  const { data } = await api.get('/songs');
  return data; // Array of song objects from SQLite
};

export default api;
