"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Copy, Check } from "lucide-react";
import { useState } from "react";

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
      <div className="space-y-4 animate-pulse">
        <div className="h-4 bg-muted rounded w-3/4"></div>
        <div className="h-4 bg-muted rounded w-full"></div>
        <div className="h-4 bg-muted rounded w-5/6"></div>
        <div className="h-40 bg-muted rounded w-full"></div>
      </div>
    );
  }

  if (!lyrics) return null;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center bg-accent/20 p-4 rounded-xl border">
        <div className="flex items-center gap-4">
          <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20">
            Fidelity: {(versions[0]?.style_fidelity * 100).toFixed(0)}%
          </Badge>
          <span className="text-sm text-muted-foreground">Version A (Highest Fidelity)</span>
        </div>
        <Button variant="ghost" size="sm" onClick={handleCopy}>
          {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
        </Button>
      </div>

      <Tabs defaultValue="best" className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-6 bg-muted/30">
          <TabsTrigger value="best">🏆 Best (A)</TabsTrigger>
          <TabsTrigger value="v2">Version B</TabsTrigger>
          <TabsTrigger value="v3">Version C</TabsTrigger>
        </TabsList>
        
        <TabsContent value="best" className="mt-0">
          <LyricsCard text={lyrics} />
        </TabsContent>
        <TabsContent value="v2" className="mt-0">
          <LyricsCard text={versions[1]?.lyrics || "Variant not generated."} />
        </TabsContent>
        <TabsContent value="v3" className="mt-0">
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
          <div className="absolute -left-4 top-1/2 -translate-y-1/2 w-1 h-4 bg-primary rounded-full opacity-50 group-hover:opacity-100 transition-opacity"></div>
          <div className="text-primary/80 font-bold mt-8 mb-4 text-xs tracking-widest uppercase flex items-center gap-2">
            <Sparkles className="w-3 h-3" />
            {trimmed.slice(1, -1)}
          </div>
        </div>
      );
    }
    return <p key={i} className="text-slate-300 leading-relaxed font-medium mb-1 pl-1 transition-colors hover:text-white">{line}</p>;
  });

  return (
    <Card className="bg-slate-900/40 backdrop-blur-md border-slate-800 shadow-2xl relative overflow-hidden group">
      <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl -mr-16 -mt-16 group-hover:bg-primary/10 transition-colors"></div>
      <CardContent className="p-10 font-sans whitespace-pre-wrap relative z-10">
        {formattedText}
      </CardContent>
    </Card>
  );
}

import { Sparkles } from "lucide-react";
