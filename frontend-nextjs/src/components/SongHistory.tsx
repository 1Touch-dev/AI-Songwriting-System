"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { History, Play, Bookmark, Music, Calendar } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export function SongHistory() {
  const { history, setLyrics, setTheme, setArtists, setLanguage, setBars } = useStore();

  const loadSong = (song: any) => {
    setTheme(song.theme);
    setArtists(song.artists || []);
    setLyrics(song.lyrics);
    setLanguage(song.language || "English");
    setBars(song.bars || 16);
  };

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white group">
          <History className="w-4 h-4 mr-2 group-hover:rotate-[-45deg] transition-transform" />
          My Songs
        </Button>
      </SheetTrigger>
      <SheetContent className="w-[400px] sm:w-[540px] bg-[#020617] border-slate-800 text-slate-50">
        <SheetHeader className="mb-8">
          <SheetTitle className="text-2xl font-bold flex items-center gap-3">
            <Bookmark className="text-primary" />
            Song Archive
          </SheetTitle>
          <SheetDescription className="text-slate-400">
            Revisit and remix your past lyrical masterpieces.
          </SheetDescription>
        </SheetHeader>

        {history.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-[60vh] text-center space-y-4">
            <div className="bg-slate-900/50 p-6 rounded-full">
               <Music className="w-12 h-12 text-slate-700" />
            </div>
            <p className="text-slate-500 font-medium">No songs in your archive yet.</p>
            <p className="text-xs text-slate-600 max-w-[200px]">Generate some lyrics to start building your professional portfolio.</p>
          </div>
        ) : (
          <ScrollArea className="h-[calc(100vh-180px)] pr-4 custom-scrollbar">
            <div className="space-y-4">
              {history.map((song, i) => (
                <Card key={i} className="bg-slate-900/40 border-slate-800 hover:border-primary/50 transition-colors group cursor-pointer overflow-hidden">
                  <CardContent className="p-5 space-y-4">
                    <div className="flex justify-between items-start">
                      <div className="space-y-1">
                        <h4 className="font-bold text-slate-200 line-clamp-1 group-hover:text-primary transition-colors">
                          {song.theme || "Untitled Project"}
                        </h4>
                        <div className="flex flex-wrap gap-2 pt-1">
                          {song.artists?.map((artist: string) => (
                            <Badge key={artist} variant="secondary" className="bg-slate-800 text-[10px] py-0 px-2 h-5">
                              {artist}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <Badge variant="outline" className="text-[10px] text-slate-500 border-slate-800">
                        {song.language}
                      </Badge>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                       <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                         <Calendar className="w-3 h-3" />
                         {new Date(song.created_at || Date.now()).toLocaleDateString()}
                       </div>
                       <Button 
                         size="sm" 
                         variant="secondary" 
                         className="h-8 gap-2 bg-primary/10 text-primary hover:bg-primary hover:text-white"
                         onClick={() => loadSong(song)}
                       >
                         <Play className="w-3 h-3" />
                         Load Studio
                       </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  );
}
