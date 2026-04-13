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
      const url = await generateVoice(lyrics.substring(0, 1000)); // Limit to first 1k chars for safety
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
      <Card className="border-dashed h-full flex flex-col items-center justify-center p-8 bg-muted/10">
        <div className="bg-muted rounded-full p-6 mb-4">
          <MusicIcon className="w-12 h-12 text-muted-foreground" />
        </div>
        <CardTitle className="text-center text-muted-foreground font-semibold">Production Hub</CardTitle>
        <p className="text-center text-sm text-muted-foreground mt-2">Generate lyrics first to unlock voice synthesis and music production.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden border-2 border-primary/20 shadow-xl">
        <CardHeader className="bg-primary/5 pb-4">
          <CardTitle className="text-lg flex items-center gap-2">
            <Mic className="w-5 h-5 text-primary" />
            Vocal Synthesis
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-6">
          {vocalUrl ? (
            <div className="space-y-4">
               <audio controls className="w-full">
                <source src={vocalUrl} type="audio/mpeg" />
                Your browser does not support the audio element.
              </audio>
              <p className="text-xs text-muted-foreground text-center italic">Powered by ElevenLabs Multilingual V2</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-6 text-center space-y-4">
              <p className="text-sm text-muted-foreground">Synthesize this song into high-quality vocals.</p>
              <Button onClick={handleVoice} disabled={isGenerating || !lyrics}>Generate Voice</Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="overflow-hidden border-2 border-primary/20 shadow-xl">
        <CardHeader className="bg-primary/5 pb-4">
          <CardTitle className="text-lg flex items-center gap-2">
            <MusicIcon className="w-5 h-5 text-primary" />
            Full track production
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-6">
          {musicUrls.length > 0 ? (
             <div className="space-y-4">
              {musicUrls.map((url, i) => (
                <div key={i} className="space-y-2">
                  <span className="text-xs font-semibold">Variation {i + 1}</span>
                  <audio controls className="w-full">
                    <source src={url} type="audio/mpeg" />
                  </audio>
                </div>
              ))}
              <p className="text-xs text-muted-foreground text-center italic">Produced via Suno AI Engine</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-6 text-center space-y-4">
              <p className="text-sm text-muted-foreground">Generate complete backing tracks with the click of a button.</p>
              <Button onClick={handleMusic} disabled={isGenerating || !lyrics}>Generate Music</Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

import { generateVoice, generateMusic } from "@/lib/api";
