import { create } from 'zustand';

export interface SongVersion {
  lyrics: string;
  style_fidelity: number;
}

interface SongState {
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
  lyrics: string;
  versions: SongVersion[];
  vocalUrl: string | null;
  musicUrls: string[];
  isGenerating: boolean;
  
  // Setters
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
  setVocalUrl: (url: string | null) => void;
  setMusicUrls: (urls: string[]) => void;
  setGenerating: (status: boolean) => void;
  reset: () => void;
}

export const useStore = create<SongState>((set) => ({
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
  vocalUrl: null,
  musicUrls: [],
  isGenerating: false,
  
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
  setVocalUrl: (vocalUrl) => set({ vocalUrl }),
  setMusicUrls: (musicUrls) => set({ musicUrls }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  reset: () => set({ 
    theme: "", 
    lyrics: "", 
    versions: [],
    vocalUrl: null, 
    musicUrls: [], 
    isGenerating: false,
    selectedArtists: ["Drake"],
    language: "English",
    bars: 16
  }),
}));
