"use client";

import React, { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Loader2, Music } from "lucide-react";

export function AuthOverlay() {
  const [session, setSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [statusMsg, setStatusMsg] = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleAuth = async () => {
    setLoading(true);
    setStatusMsg("");
    try {
      if (authMode === "signup") {
        const { error } = await supabase.auth.signUp({ email, password: "password123" }); // Simple pass for demo
        if (error) throw error;
        setStatusMsg("Check your email for confirmation!");
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password: "password123" });
        if (error) throw error;
      }
    } catch (error: any) {
      alert(error.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="fixed inset-0 z-[100] bg-black flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (session) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-xl flex items-center justify-center p-4">
      <Card className="w-full max-w-md bg-slate-900 border-slate-800 shadow-2xl">
        <CardHeader className="text-center space-y-4">
          <div className="mx-auto bg-primary w-12 h-12 rounded-xl flex items-center justify-center shadow-lg shadow-primary/30">
            <Music className="w-6 h-6 text-white" />
          </div>
          <div>
            <CardTitle className="text-2xl font-bold tracking-tight text-white">Global AI Studio</CardTitle>
            <CardDescription className="text-slate-400">Join the future of global songwriting.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label className="text-slate-300">Email Address</Label>
            <Input 
              type="email" 
              placeholder="name@company.com" 
              className="bg-slate-800 border-slate-700 text-white"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          
          <Button className="w-full font-bold h-12" onClick={handleAuth} disabled={loading}>
            {authMode === "login" ? "Enter Studio" : "Create Account"}
          </Button>

          <div className="text-center">
            <button 
              className="text-xs text-slate-500 hover:text-primary transition-colors hover:underline"
              onClick={() => setAuthMode(authMode === "login" ? "signup" : "login")}
            >
              {authMode === "login" ? "Don't have an account? Sign up" : "Already have an account? Log in"}
            </button>
          </div>

          {statusMsg && <p className="text-xs text-center text-green-500 font-medium">{statusMsg}</p>}
        </CardContent>
      </Card>
    </div>
  );
}

import { Label } from "./ui/label";
