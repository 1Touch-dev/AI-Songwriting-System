"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { searchArtists } from "@/lib/api";
import { Loader2, Search, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useStore } from "@/store/useStore";

export function ArtistSearch() {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  
  const { selectedArtists, setArtists } = useStore();

  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.length < 3) {
      setSuggestions([]);
      return;
    }
    setLoading(true);
    try {
      const results = await searchArtists(q);
      setSuggestions(results);
    } catch (error) {
      console.error("Search error:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchSuggestions(query);
    }, 300);
    return () => clearTimeout(timer);
  }, [query, fetchSuggestions]);

  const addArtist = (artist: string) => {
    if (!selectedArtists.includes(artist) && selectedArtists.length < 4) {
      setArtists([...selectedArtists, artist]);
    }
    setQuery("");
    setSuggestions([]);
    setShowDropdown(false);
  };

  const removeArtist = (artist: string) => {
    setArtists(selectedArtists.filter((a) => a !== artist));
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {selectedArtists.map((artist) => (
          <Badge key={artist} variant="secondary" className="px-3 py-1.5 text-xs font-semibold bg-white/5 border-white/10 text-slate-300 hover:bg-white/10 transition-colors flex items-center gap-2 rounded-full">
            {artist}
            <X 
              className="w-3.5 h-3.5 cursor-pointer hover:text-neon-blue transition-colors" 
              onClick={() => removeArtist(artist)}
            />
          </Badge>
        ))}
        {selectedArtists.length === 0 && <span className="text-slate-500 text-[10px] uppercase font-bold tracking-widest">No artists selected</span>}
      </div>

      <div className="relative">
        <div className="relative group">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-neon-blue transition-colors" />
          <Input
            placeholder="Search artists on Genius..."
            className="glass-input pl-10 h-12 text-sm rounded-xl placeholder:text-slate-600"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setShowDropdown(true);
            }}
            onFocus={() => setShowDropdown(true)}
          />
          {loading && (
            <Loader2 className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-neon-blue" />
          )}
        </div>

        {showDropdown && suggestions.length > 0 && (
          <div className="absolute z-50 w-full mt-2 glass-panel rounded-2xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-2 duration-300">
            <ul className="max-h-60 overflow-y-auto custom-scrollbar">
              {suggestions.map((artist, idx) => (
                <li
                  key={idx}
                  className="px-5 py-3.5 text-sm font-medium text-slate-300 hover:bg-white/5 hover:text-white cursor-pointer transition-colors border-b border-white/5 last:border-0"
                  onClick={() => addArtist(artist)}
                >
                  {artist}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
