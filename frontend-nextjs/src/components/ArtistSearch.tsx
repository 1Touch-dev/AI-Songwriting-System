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
          <Badge key={artist} variant="secondary" className="px-3 py-1 text-sm font-medium flex items-center gap-2">
            {artist}
            <X 
              className="w-3 h-3 cursor-pointer hover:text-destructive" 
              onClick={() => removeArtist(artist)}
            />
          </Badge>
        ))}
        {selectedArtists.length === 0 && <span className="text-muted-foreground text-xs">No artists selected</span>}
      </div>

      <div className="relative">
        <div className="relative">
          <Search className="absolute left-3 top-3 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search artists on Genius..."
            className="pl-9 h-11"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setShowDropdown(true);
            }}
            onFocus={() => setShowDropdown(true)}
          />
          {loading && (
            <Loader2 className="absolute right-3 top-3 w-4 h-4 animate-spin text-primary" />
          )}
        </div>

        {showDropdown && suggestions.length > 0 && (
          <div className="absolute z-50 w-full mt-1 bg-popover text-popover-foreground border rounded-md shadow-lg overflow-hidden">
            <ul className="max-h-60 overflow-y-auto">
              {suggestions.map((artist, idx) => (
                <li
                  key={idx}
                  className="px-4 py-3 text-sm hover:bg-accent hover:text-accent-foreground cursor-pointer transition-colors border-b last:border-0"
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
