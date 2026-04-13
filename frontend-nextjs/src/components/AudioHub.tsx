"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Mic, Music as MusicIcon, Play, Square, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AudioHub() {
  const { vocalUrl, musicUrls, isGenerating, lyrics, setVocalUrl, setMusicUrls } = useStore();

  const handleVoice = async () => {
    if (!lyrics) return;
    try {
      const url = await generateVoice(lyrics.substring(0, 1000));
      setVocalUrl(url);
    } catch (error) {
      console.error("Voice generation failed:", error);
    }
  };

  const handleMusic = async () => {
    if (!lyrics) return;
    try {
      const urls = await generateMusic(lyrics, "modern, high fidelity, catch", "My Song Asset");
      setMusicUrls(urls);
    } catch (error) {
      console.error("Music generation failed:", error);
    }
  };

  if (!lyrics && !vocalUrl && musicUrls.length === 0) {
    return (
      <div className="glass-card h-full flex flex-col items-center justify-center p-12 bg-white/[0.02]">
        <div className="bg-white/5 rounded-full p-8 mb-6 border border-white/10 text-slate-500 animate-pulse">
          <MusicIcon className="w-12 h-12" />
        </div>
        <h3 className="text-center text-slate-400 font-bold uppercase tracking-[0.2em] text-xs">Production Hub</h3>
        <p className="text-center text-sm text-slate-500 mt-4 max-w-[200px] leading-relaxed">Generate lyrics first to unlock voice synthesis and music production.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="glass-card overflow-hidden group">
        <div className="p-6 border-b border-white/5 bg-white/[0.02] flex items-center gap-3">
          <Mic className="w-4 h-4 text-neon-blue" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">Vocal Synthesis</h3>
        </div>
        <div className="p-8">
          {vocalUrl ? (
            <div className="space-y-5">
              <audio controls className="w-full h-10 custom-audio-player">
                <source src={vocalUrl} type="audio/mpeg" />
              </audio>
              <p className="text-[10px] text-slate-500 text-center uppercase tracking-widest font-bold">Powered by ElevenLabs V2</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center text-center space-y-5">
              <p className="text-sm text-slate-400 leading-relaxed font-medium">Synthesize this song into high-quality vocals.</p>
              <Button 
                onClick={handleVoice} 
                disabled={isGenerating || !lyrics}
                className="w-full bg-white/5 hover:bg-white/10 border-white/10 text-white rounded-xl h-12 font-bold transition-all"
              >
                Generate Voice
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="glass-card overflow-hidden group">
        <div className="p-6 border-b border-white/5 bg-white/[0.02] flex items-center gap-3">
          <MusicIcon className="w-4 h-4 text-neon-purple" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400">Full Track Production</h3>
        </div>
        <div className="p-8">
          {musicUrls.length > 0 ? (
             <div className="space-y-6">
              {musicUrls.map((url, i) => (
                <div key={i} className="space-y-3">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Master Mix {i + 1}</span>
                  <audio controls className="w-full h-10 custom-audio-player">
                    <source src={url} type="audio/mpeg" />
                  </audio>
                </div>
              ))}
              <p className="text-[10px] text-slate-500 text-center uppercase tracking-widest font-bold">Produced via Suno AI Engine</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center text-center space-y-5">
              <p className="text-sm text-slate-400 leading-relaxed font-medium">Generate complete backing tracks with the click of a button.</p>
              <Button 
                onClick={handleMusic} 
                disabled={isGenerating || !lyrics}
                className="w-full bg-neon-purple/20 hover:bg-neon-purple/30 border-neon-purple/20 text-neon-purple rounded-xl h-12 font-bold transition-all shadow-[0_0_20px_rgba(139,92,246,0.1)] hover:shadow-[0_0_30px_rgba(139,92,246,0.2)]"
              >
                Generate Music
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { generateVoice, generateMusic } from "@/lib/api";
