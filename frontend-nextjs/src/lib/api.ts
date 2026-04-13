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

import { supabase } from './supabase';

export const saveSong = async (song: any) => {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;

  const { data, error } = await supabase
    .from('songs')
    .insert([{ 
      user_id: user.id,
      theme: song.theme,
      artists: song.artists,
      lyrics: song.lyrics,
      language: song.language,
      bars: song.bars,
      creative_mode: song.creative_mode,
      created_at: new Date().toISOString()
    }])
    .select();

  if (error) throw error;
  return data[0];
};

export const getUserSongs = async () => {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return [];

  const { data, error } = await supabase
    .from('songs')
    .select('*')
    .order('created_at', { ascending: false });

  if (error) throw error;
  return data;
};

export default api;
