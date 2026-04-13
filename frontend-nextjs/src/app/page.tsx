"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useStore } from "@/store/useStore";
import { ArtistSearch } from "@/components/ArtistSearch";
import { LyricsOutput } from "@/components/LyricsOutput";
import { AudioHub } from "@/components/AudioHub";
import { generateLyrics, saveSong, getUserSongs } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Sparkles, History, Music, Mic, Layers, Settings2, Languages, LogOut, Loader2 } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SongHistory } from "@/components/SongHistory";

export default function StudioPage() {
  const router = useRouter();
  const store = useStore();
  const [isGenerating, setIsGenerating] = useState(false);

  // --- Auth Guard ---
  useEffect(() => {
    if (!store.isAuthenticated) {
      router.push("/login");
    }
  }, [store.isAuthenticated, router]);

  // Initial fetch of user history
  useEffect(() => {
    if (store.isAuthenticated) {
      const fetchHistory = async () => {
        try {
          const history = await getUserSongs();
          store.setHistory(history);
        } catch (err) {
          console.error("Failed to fetch history:", err);
        }
      };
      fetchHistory();
    }
  }, [store.isAuthenticated]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    store.setGenerating(true);
    try {
      const result = await generateLyrics({
        artists: store.selectedArtists,
        theme: store.theme,
        structure: store.structure,
        language: store.language,
        gender: store.gender,
        bars: store.bars,
        reference_lyrics: store.referenceLyrics,
        style_strength: 0.85,
        gen_mode: store.creativeMode,
        perspective_mode: store.perspectiveMode
      });
      
      store.setLyrics(result.lyrics);
      store.setVersions(result.versions || []);

      // Auto-save to SQLite (via FastAPI)
      const saveRes = await saveSong({
        theme: store.theme,
        artists: store.selectedArtists,
        lyrics: result.lyrics,
        language: store.language,
        bars: store.bars,
        creative_mode: store.creativeMode
      });
      
      if (saveRes.status === "success") {
        // Fetch history again to ensure UI is in sync
        const history = await getUserSongs();
        store.setHistory(history);
      }
    } catch (error) {
      console.error("Generation failed:", error);
    } finally {
      setIsGenerating(false);
      store.setGenerating(false);
    }
  };

  const handleLogout = () => {
    store.logout();
    router.push("/login");
  };

  if (!store.isAuthenticated) return null; // Prevents flashing

  return (
    <div className="flex flex-col h-screen bg-[#020617] text-slate-50 font-sans selection:bg-primary/30">
      {/* Header */}
      <header className="h-16 border-b border-slate-800 flex items-center justify-between px-8 bg-black/40 backdrop-blur-md z-10">
        <div className="flex items-center gap-3">
          <div className="bg-primary p-1.5 rounded-lg shadow-lg shadow-primary/20">
            <Music className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">Global AI Music Studio</h1>
          <Badge variant="secondary" className="ml-2 bg-slate-800 text-xs text-slate-400 border-none px-2 py-0">v3.2.0 (JWT)</Badge>
        </div>
        <div className="flex items-center gap-4">
          <SongHistory />
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-red-400 gap-2" onClick={handleLogout}>
             <LogOut className="w-4 h-4" />
             Logout
          </Button>
          <div className="flex items-center gap-2 pl-4 border-l border-slate-800">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-purple-600 border border-slate-700 shadow-inner"></div>
            <span className="text-xs font-medium text-slate-400 truncate max-w-[120px]">{store.user?.email}</span>
          </div>
        </div>
      </header>

      {/* Workspace */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Panel: Studio Config */}
        <aside className="w-80 border-r border-slate-800 bg-[#020617] overflow-y-auto custom-scrollbar">
          <div className="p-6 space-y-8">
            <section className="space-y-4">
              <label className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                <Mic className="w-3.5 h-3.5" />
                Artistic Engine
              </label>
              <ArtistSearch />
            </section>

            <section className="space-y-6">
               <div className="space-y-4">
                 <Label className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                    <Languages className="w-3.5 h-3.5" />
                    Linguistic Tone
                 </Label>
                 <Select value={store.language} onValueChange={(val) => store.setLanguage(val)}>
                    <SelectTrigger className="bg-slate-900/50 border-slate-800">
                      <SelectValue placeholder="Language" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="English">English</SelectItem>
                      <SelectItem value="Spanish">Spanish</SelectItem>
                      <SelectItem value="French">French</SelectItem>
                      <SelectItem value="German">German</SelectItem>
                    </SelectContent>
                 </Select>
               </div>

               <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <Label className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                      <Layers className="w-3.5 h-3.5" />
                      Song Length
                    </Label>
                    <span className="text-xs font-mono text-primary">{store.bars} bars</span>
                  </div>
                  <Slider 
                    value={[store.bars]} 
                    max={32} 
                    min={4} 
                    step={4} 
                    onValueChange={(val) => store.setBars(val[0])}
                  />
               </div>

               <div className="space-y-4">
                  <Label className="text-xs font-bold text-slate-500 uppercase flex items-center gap-2">
                    <Settings2 className="w-3.5 h-3.5" />
                    Creative Parameters
                  </Label>
                  <Select value={store.creativeMode} onValueChange={(val: any) => store.setCreativeMode(val)}>
                    <SelectTrigger className="bg-slate-900/50 border-slate-800">
                      <SelectValue placeholder="Mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="generate">Generate New</SelectItem>
                      <SelectItem value="continue">Continue Story</SelectItem>
                      <SelectItem value="remix">Remix Style</SelectItem>
                    </SelectContent>
                  </Select>
                  
                  <Select value={store.perspectiveMode} onValueChange={(val: any) => store.setPerspectiveMode(val)}>
                    <SelectTrigger className="bg-slate-900/50 border-slate-800">
                      <SelectValue placeholder="Perspective" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="same">Same POV</SelectItem>
                      <SelectItem value="opposite">Opposite POV</SelectItem>
                      <SelectItem value="response">Response Track</SelectItem>
                    </SelectContent>
                  </Select>
               </div>
            </section>
          </div>
        </aside>

        {/* Center Panel: Lyrics Editor */}
        <section className="flex-1 overflow-y-auto bg-black/20 custom-scrollbar">
          <div className="max-w-3xl mx-auto p-12 space-y-12">
            <div className="space-y-6">
              <div className="flex items-center gap-4">
                <span className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-sm">1</span>
                <h2 className="text-2xl font-semibold">Theme & Narrative</h2>
              </div>
              <Input 
                placeholder="What is this song about?" 
                className="h-14 bg-slate-900/40 border-slate-800 text-lg rounded-xl focus-visible:ring-primary/50"
                value={store.theme}
                onChange={(e) => store.setTheme(e.target.value)}
              />
              <Textarea 
                placeholder="Paste reference lyrics or existing bars (optional)..." 
                className="min-h-[120px] bg-slate-900/40 border-slate-800 rounded-xl focus-visible:ring-primary/50"
                value={store.referenceLyrics}
                onChange={(e) => store.setReferenceLyrics(e.target.value)}
              />
            </div>

            <div className="flex flex-col items-center gap-6">
              <Button 
                size="lg" 
                className="h-16 px-12 rounded-full text-lg font-bold gap-3 shadow-2xl shadow-primary/20 transition-all active:scale-95"
                onClick={handleGenerate}
                disabled={isGenerating}
              >
                {isGenerating ? <Loader2 className="w-6 h-6 animate-spin" /> : <Sparkles className="w-6 h-6" />}
                Ignite Production
              </Button>
              <p className="text-xs text-slate-500 uppercase tracking-widest font-semibold">Uses Hybrid RAG + GPT-4o Engine</p>
            </div>

            <div className="pt-8">
              <LyricsOutput />
            </div>
          </div>
        </section>

        {/* Right Panel: Production Playback */}
        <aside className="w-80 border-l border-slate-800 bg-[#020617] p-6 overflow-y-auto custom-scrollbar">
          <label className="text-xs font-bold text-slate-500 uppercase mb-6 flex items-center gap-2">
            <Layers className="w-3.5 h-3.5" />
            Workspace Output
          </label>
          <AudioHub />
        </aside>
      </main>
    </div>
  );
}
