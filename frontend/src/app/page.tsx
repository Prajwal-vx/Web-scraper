'use client';

import React, { useState, useEffect } from 'react';
import { 
  ScanEye, Plus, Activity, Database, Radar, Sparkles, 
  CheckCircle, Cpu, Layers, Award, BookOpen, Key, ShieldCheck
} from 'lucide-react';

export default function Home() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [stats, setStats] = useState({ totalJobs: 0, totalRecords: 0, successRate: '100%' });
  const [targetUrl, setTargetUrl] = useState('https://example.com');
  const [inspectionResult, setInspectionResult] = useState<any>(null);
  const [inspecting, setInspecting] = useState(false);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/v1/jobs');
      if (res.ok) {
        const jobs = await res.json();
        const records = jobs.reduce((acc: number, j: any) => acc + (j.records_count || 0), 0);
        setStats({
          totalJobs: jobs.length,
          totalRecords: records,
          successRate: jobs.length > 0 ? `${Math.round((jobs.filter((j: any) => j.status === 'completed').length / jobs.length) * 100)}%` : '100%'
        });
      }
    } catch (e) {
      // Backend proxy fallback
    }
  };

  const handleInspect = async () => {
    setInspecting(true);
    try {
      const res = await fetch('/api/v1/inspect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: targetUrl, mode: 'http' })
      });
      if (res.ok) {
        const data = await res.json();
        setInspectionResult(data);
      } else {
        const err = await res.json();
        alert('Inspection failed: ' + (err.detail || 'error'));
      }
    } catch (e: any) {
      alert('Network error: ' + e.message);
    } finally {
      setInspecting(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#0a0d14] text-slate-100 antialiased overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-slate-800 bg-[#111622]/80 p-4 flex flex-col justify-between shrink-0">
        <div className="space-y-6">
          <div className="flex items-center space-x-3 px-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <ScanEye className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-1.5">
                <span className="font-bold tracking-tight text-white">NEXUS</span>
                <span className="text-indigo-400 font-bold">SCRAPE</span>
              </div>
              <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">AI Pro Edition</p>
            </div>
          </div>

          <nav className="space-y-1">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition ${
                activeTab === 'dashboard' ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30' : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span>Dashboard</span>
            </button>
            <button
              onClick={() => setActiveTab('builder')}
              className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition ${
                activeTab === 'builder' ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30' : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>Visual Builder & AI</span>
            </button>
            <button
              onClick={() => setActiveTab('datasets')}
              className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition ${
                activeTab === 'datasets' ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30' : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <Database className="w-4 h-4" />
              <span>Datasets & Export</span>
            </button>
            <button
              onClick={() => setActiveTab('radar')}
              className={`w-full flex items-center space-x-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition ${
                activeTab === 'radar' ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30' : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <Radar className="w-4 h-4" />
              <span>Website Change Radar</span>
            </button>
          </nav>
        </div>

        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 text-[11px] space-y-1">
          <p className="font-semibold text-slate-300 flex items-center">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 mr-1" /> SSRF Defense Active
          </p>
          <p className="text-slate-500">Private & Metadata IPs Blocked</p>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-8 space-y-6">
        <header className="flex items-center justify-between pb-6 border-b border-slate-800">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white capitalize">{activeTab}</h1>
            <p className="text-xs text-slate-400 mt-1">Autonomous web crawling, JavaScript rendering, and data extraction engine.</p>
          </div>
          <div className="flex items-center space-x-3">
            <a
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              className="px-3.5 py-2 rounded-xl border border-slate-800 hover:border-slate-700 text-xs font-semibold text-slate-300 flex items-center space-x-2"
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>FastAPI Docs</span>
            </a>
            <a
              href="http://127.0.0.1:8000"
              target="_blank"
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/30 flex items-center space-x-2"
            >
              <ScanEye className="w-3.5 h-3.5" />
              <span>Full Local Dashboard</span>
            </a>
          </div>
        </header>

        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800">
                <span className="text-xs font-medium text-slate-400">Total Crawl Jobs</span>
                <div className="text-3xl font-bold text-white mt-2">{stats.totalJobs}</div>
                <p className="text-[11px] text-slate-500 mt-1">Executed crawler runs</p>
              </div>
              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800">
                <span className="text-xs font-medium text-slate-400">Records Collected</span>
                <div className="text-3xl font-bold text-white mt-2">{stats.totalRecords}</div>
                <p className="text-[11px] text-slate-500 mt-1">Normalized structured data</p>
              </div>
              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800">
                <span className="text-xs font-medium text-slate-400">Crawl Success Rate</span>
                <div className="text-3xl font-bold text-white mt-2">{stats.successRate}</div>
                <p className="text-[11px] text-emerald-400 mt-1">Compliant executions</p>
              </div>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/40 border border-slate-800 space-y-4">
              <h3 className="text-sm font-semibold text-white">Quick URL Inspector</h3>
              <div className="flex space-x-3">
                <input
                  type="url"
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  placeholder="https://example.com"
                  className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-xs text-white"
                />
                <button
                  onClick={handleInspect}
                  disabled={inspecting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold"
                >
                  {inspecting ? 'Inspecting...' : 'Inspect Site'}
                </button>
              </div>

              {inspectionResult && (
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono space-y-2">
                  <div className="text-emerald-400">Title: {inspectionResult.title}</div>
                  <div className="text-slate-400">robots.txt: {inspectionResult.robots_allowed ? 'Allowed' : 'Disallowed'}</div>
                  <div className="text-slate-400">Links Discovered: {inspectionResult.discovered_links?.length || 0}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
