import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface SongVersion {
  lyrics: string;
  style_fidelity: number;
}

interface User {
  id: number;
  email: string;
}

interface SongState {
  // Auth State
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  
  // Session / Project
  selectedArtists: string[];
  theme: string;
  language: string;
  gender: string;
  bars: number;
  structure: string;
  creativeMode: "generate" | "continue" | "remix";
  perspectiveMode: "same" | "opposite" | "response";
  referenceLyrics: string;
  
  // Generation Output
  history: any[];
  lyrics: string;
  versions: SongVersion[];
  isGenerating: boolean;
  vocalUrl: string;
  musicUrls: string[];

  // Actions
  setAuth: (user: User | null, token: string | null) => void;
  logout: () => void;
  setArtists: (artists: string[]) => void;
  setTheme: (theme: string) => void;
  setLanguage: (lang: string) => void;
  setGender: (gender: string) => void;
  setBars: (bars: number) => void;
  setStructure: (structure: string) => void;
  setCreativeMode: (mode: "generate" | "continue" | "remix") => void;
  setPerspectiveMode: (mode: "same" | "opposite" | "response") => void;
  setReferenceLyrics: (lyrics: string) => void;
  setLyrics: (lyrics: string) => void;
  setVersions: (versions: SongVersion[]) => void;
  setGenerating: (status: boolean) => void;
  setHistory: (history: any[]) => void;
  addHistory: (song: any) => void;
  setVocalUrl: (url: string) => void;
  setMusicUrls: (urls: string[]) => void;
  reset: () => void;
}

export const useStore = create<SongState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      selectedArtists: ["Drake"],
      theme: "",
      language: "English",
      gender: "Neutral",
      bars: 16,
      structure: "Standard (V-C-V-C-B-C)",
      creativeMode: "generate",
      perspectiveMode: "same",
      referenceLyrics: "",
      lyrics: "",
      versions: [],
      isGenerating: false,
      history: [],
      vocalUrl: "",
      musicUrls: [],

      setAuth: (user, token) => set({ user, token, isAuthenticated: !!token }),
      logout: () => set({ user: null, token: null, isAuthenticated: false }),
      setArtists: (artists) => set({ selectedArtists: artists }),
      setTheme: (theme) => set({ theme }),
      setLanguage: (language) => set({ language }),
      setGender: (gender) => set({ gender }),
      setBars: (bars) => set({ bars }),
      setStructure: (structure) => set({ structure }),
      setCreativeMode: (creativeMode) => set({ creativeMode }),
      setPerspectiveMode: (perspectiveMode) => set({ perspectiveMode }),
      setReferenceLyrics: (referenceLyrics) => set({ referenceLyrics }),
      setLyrics: (lyrics) => set({ lyrics }),
      setVersions: (versions) => set({ versions }),
      setGenerating: (isGenerating) => set({ isGenerating }),
      setHistory: (history) => set({ history }),
      addHistory: (song) => set((state) => ({ history: [song, ...state.history] })),
      setVocalUrl: (vocalUrl) => set({ vocalUrl }),
      setMusicUrls: (musicUrls) => set({ musicUrls }),
      reset: () => set({
        theme: "", 
        lyrics: "", 
        versions: [],
        isGenerating: false,
        selectedArtists: ["Drake"],
        language: "English",
        bars: 16
      }),
    }),
    {
      name: 'ai-songwriter-storage',
      partialize: (state) => ({ token: state.token, user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
);
