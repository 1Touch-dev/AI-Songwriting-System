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
    <div className="flex flex-col h-screen bg-[#050505] text-slate-100 font-sans selection:bg-neon-blue/30 relative overflow-hidden">
      {/* Dynamic Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[600px] h-[600px] bg-neon-blue/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[500px] h-[500px] bg-neon-purple/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Header */}
      <header className="h-16 border-b border-white/5 flex items-center justify-between px-8 bg-black/40 backdrop-blur-xl z-20">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center shadow-lg shadow-neon-blue/20">
            <Music className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white leading-tight">Global AI Music Studio</h1>
            <p className="text-[10px] text-slate-500 font-bold uppercase tracking-widest leading-none">V3.2.0 • Premium Production Hub</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <SongHistory />
          <div className="h-4 w-px bg-white/10 mx-2" />
          <div className="flex items-center gap-3 pr-2">
            <span className="text-[11px] font-semibold text-slate-400 hidden md:block">{store.user?.email}</span>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-white/10 to-white/5 border border-white/10 flex items-center justify-center overflow-hidden">
                <Mic className="w-4 h-4 text-slate-500" />
            </div>
          </div>
          <Button variant="ghost" size="sm" className="text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-colors" onClick={handleLogout}>
             <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </header>

      {/* Workspace */}
      <main className="flex-1 flex overflow-hidden z-10">
        {/* Left Panel: Studio Config */}
        <aside className="w-80 glass-panel border-y-0 border-l-0 overflow-y-auto custom-scrollbar">
          <div className="p-8 space-y-10">
            <section className="space-y-5">
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] flex items-center gap-2">
                <Mic className="w-3 h-3 text-neon-blue" />
                Artistic Engine
              </label>
              <ArtistSearch />
            </section>

            <section className="space-y-8">
               <div className="space-y-5">
                 <Label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] flex items-center gap-2">
                    <Languages className="w-3 h-3 text-neon-blue" />
                    Linguistic Tone
                 </Label>
                 <Select value={store.language} onValueChange={(val) => val && store.setLanguage(val)}>
                    <SelectTrigger className="glass-input h-11 border-white/5 rounded-xl">
                      <SelectValue placeholder="Language" />
                    </SelectTrigger>
                    <SelectContent className="glass-panel border-white/10 rounded-xl">
                      <SelectItem value="English">English</SelectItem>
                      <SelectItem value="Spanish">Spanish</SelectItem>
                      <SelectItem value="French">French</SelectItem>
                      <SelectItem value="German">German</SelectItem>
                    </SelectContent>
                 </Select>
               </div>

               <div className="space-y-5">
                  <div className="flex justify-between items-center">
                    <Label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] flex items-center gap-2">
                      <Layers className="w-3 h-3 text-neon-blue" />
                      Song Length
                    </Label>
                    <span className="text-[11px] font-bold text-neon-blue tracking-tighter">{store.bars} BARS</span>
                  </div>
                  <Slider 
                    value={[store.bars]} 
                    max={32} 
                    min={4} 
                    step={4} 
                    onValueChange={(val) => store.setBars(val[0])}
                    className="py-2"
                  />
               </div>

               <div className="space-y-5">
                  <Label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] flex items-center gap-2">
                    <Settings2 className="w-3 h-3 text-neon-blue" />
                    Creative Parameters
                  </Label>
                  <Select value={store.creativeMode} onValueChange={(val: any) => store.setCreativeMode(val)}>
                    <SelectTrigger className="glass-input h-11 border-white/5 rounded-xl">
                      <SelectValue placeholder="Generation Mode" />
                    </SelectTrigger>
                    <SelectContent className="glass-panel border-white/10 rounded-xl">
                      <SelectItem value="generate">Generate New</SelectItem>
                      <SelectItem value="continue">Continue Story</SelectItem>
                      <SelectItem value="remix">Remix Style</SelectItem>
                    </SelectContent>
                  </Select>
                  
                  <Select value={store.perspectiveMode} onValueChange={(val: any) => store.setPerspectiveMode(val)}>
                    <SelectTrigger className="glass-input h-11 border-white/5 rounded-xl">
                      <SelectValue placeholder="POV Logic" />
                    </SelectTrigger>
                    <SelectContent className="glass-panel border-white/10 rounded-xl">
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
        <section className="flex-1 overflow-y-auto bg-black/10 custom-scrollbar">
          <div className="max-w-3xl mx-auto p-12 lg:p-16 space-y-16">
            <div className="space-y-8 animate-in fade-in slide-in-from-top-4 duration-700">
              <div className="flex items-center gap-4">
                <span className="w-10 h-10 rounded-2xl bg-neon-blue/10 flex items-center justify-center text-neon-blue font-black text-sm border border-neon-blue/20">1</span>
                <h2 className="text-3xl font-bold text-white tracking-tight">Theme & Narrative</h2>
              </div>
              
              <div className="space-y-4">
                 <Input 
                  placeholder="What is this song about?" 
                  className="glass-input h-16 text-xl px-6 rounded-2xl placeholder:text-slate-600 focus:ring-neon-blue/20"
                  value={store.theme}
                  onChange={(e) => store.setTheme(e.target.value)}
                />
                <Textarea 
                  placeholder="Paste reference lyrics or existing bars (optional)..." 
                  className="glass-input min-h-[160px] p-6 text-lg rounded-2xl placeholder:text-slate-600 focus:ring-neon-blue/20 resize-none leading-relaxed"
                  value={store.referenceLyrics}
                  onChange={(e) => store.setReferenceLyrics(e.target.value)}
                />
              </div>
            </div>

            <div className="flex flex-col items-center gap-8 py-4">
              <div className="relative group">
                <div className="absolute -inset-1 bg-gradient-to-r from-neon-blue to-neon-purple rounded-full blur opacity-25 group-hover:opacity-60 transition duration-1000 group-hover:duration-200"></div>
                <Button 
                  size="lg" 
                  className="relative h-20 px-16 rounded-full text-xl font-black gap-4 transition-all active:scale-95 bg-black border border-white/10 hover:border-white/20 text-white shadow-2xl"
                  onClick={handleGenerate}
                  disabled={isGenerating}
                >
                  {isGenerating ? <Loader2 className="w-7 h-7 animate-spin text-neon-blue" /> : <Sparkles className="w-7 h-7 text-neon-blue" />}
                  Ignite Production
                </Button>
              </div>
              <p className="text-[11px] text-slate-500 uppercase tracking-[0.3em] font-black text-glow">Artificial Intelligence Synthesis Hub</p>
            </div>

            <div className="pt-8 mb-20">
              <LyricsOutput />
            </div>
          </div>
        </section>

        {/* Right Panel: Production Playback */}
        <aside className="w-80 glass-panel border-y-0 border-r-0 p-8 overflow-y-auto custom-scrollbar">
          <label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] mb-10 block flex items-center gap-2">
            <Layers className="w-3 h-3 text-neon-purple" />
            Workspace Output
          </label>
          <AudioHub />
        </aside>
      </main>
    </div>
  );
}
