"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Copy, Check } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Sparkles } from "lucide-react";

export function LyricsOutput() {
  const { lyrics, versions, isGenerating } = useStore();
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(lyrics);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isGenerating && !lyrics) {
    return (
      <div className="space-y-6 max-w-2xl mx-auto">
        <div className="flex items-center gap-4 animate-pulse">
          <div className="h-6 bg-white/5 rounded-full w-24"></div>
          <div className="h-4 bg-white/5 rounded-full w-48"></div>
        </div>
        <div className="glass-card p-10 space-y-4 animate-pulse">
          <div className="h-4 bg-white/5 rounded w-3/4"></div>
          <div className="h-4 bg-white/5 rounded w-full"></div>
          <div className="h-4 bg-white/5 rounded w-5/6"></div>
          <div className="h-32 bg-white/5 rounded w-full"></div>
        </div>
      </div>
    );
  }

  if (!lyrics) return null;

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      <div className="flex justify-between items-center glass-card p-5">
        <div className="flex items-center gap-5">
          <Badge variant="outline" className="bg-neon-blue/10 text-neon-blue border-neon-blue/20 px-3 py-1 text-[10px] uppercase font-bold tracking-tighter">
            Fidelity: {(versions[0]?.style_fidelity * 100).toFixed(0)}%
          </Badge>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-widest">Master Version (A)</span>
        </div>
        <Button variant="ghost" size="sm" onClick={handleCopy} className="hover:bg-white/5 text-slate-400 hover:text-white transition-colors">
          {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
        </Button>
      </div>

      <Tabs defaultValue="best" className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-8 bg-white/5 border border-white/10 p-1.5 rounded-2xl">
          <TabsTrigger value="best" className="rounded-xl data-[state=active]:bg-white/10 data-[state=active]:text-white data-[state=active]:shadow-lg text-xs font-bold uppercase tracking-widest text-slate-500 py-3">🏆 Best (A)</TabsTrigger>
          <TabsTrigger value="v2" className="rounded-xl data-[state=active]:bg-white/10 data-[state=active]:text-white data-[state=active]:shadow-lg text-xs font-bold uppercase tracking-widest text-slate-500 py-3">Variant B</TabsTrigger>
          <TabsTrigger value="v3" className="rounded-xl data-[state=active]:bg-white/10 data-[state=active]:text-white data-[state=active]:shadow-lg text-xs font-bold uppercase tracking-widest text-slate-500 py-3">Variant C</TabsTrigger>
        </TabsList>
        
        <TabsContent value="best" className="mt-0 ring-offset-0 focus-visible:ring-0">
          <LyricsCard text={lyrics} />
        </TabsContent>
        <TabsContent value="v2" className="mt-0 ring-offset-0 focus-visible:ring-0">
          <LyricsCard text={versions[1]?.lyrics || "Variant not generated."} />
        </TabsContent>
        <TabsContent value="v3" className="mt-0 ring-offset-0 focus-visible:ring-0">
          <LyricsCard text={versions[2]?.lyrics || "Variant not generated."} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function LyricsCard({ text }: { text: string }) {
  const formattedText = text.split("\n").map((line, i) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      return (
        <div key={i} className="group relative">
          <div className="absolute -left-6 top-1/2 -translate-y-1/2 w-1 h-5 bg-neon-purple rounded-full opacity-0 group-hover:opacity-100 transition-all blur-sm shadow-[0_0_10px_rgba(139,92,246,0.5)]"></div>
          <div className="text-neon-purple font-bold mt-10 mb-5 text-[10px] tracking-[0.2em] uppercase flex items-center gap-3">
            <Sparkles className="w-3.5 h-3.5" />
            {trimmed.slice(1, -1)}
          </div>
        </div>
      );
    }
    return <p key={i} className="text-slate-300 leading-relaxed font-medium mb-1.5 pl-1 transition-colors hover:text-white selection:bg-neon-blue/30">{line}</p>;
  });

  return (
    <div className="glass-card relative overflow-hidden group">
      <div className="absolute top-0 right-0 w-64 h-64 bg-neon-blue/5 rounded-full blur-[100px] -mr-32 -mt-32 pointer-events-none group-hover:bg-neon-blue/10 transition-all duration-700"></div>
      <div className="absolute bottom-0 left-0 w-48 h-48 bg-neon-purple/5 rounded-full blur-[80px] -ml-24 -mb-24 pointer-events-none group-hover:bg-neon-purple/10 transition-all duration-700"></div>
      
      <div className="p-12 font-sans whitespace-pre-wrap relative z-10 text-lg md:text-xl">
        {formattedText}
      </div>
    </div>
  );
}
