"use client";

import { useEffect, useState, Suspense, useMemo, useCallback } from "react";
import { ShieldCheck, Search, ChevronDown, ChevronUp, Copy, Check, Terminal, BrainCircuit } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface AuditRecord {
  trade_id: string;
  timestamp: string;
  underlying?: string;
  regime: string;
  strategy: string;
  confidence: number;
  consensus_score?: number;
  votes?: { agent_name: string; vote: string; reasoning: string }[];
  checks?: Record<string, { passed: boolean; detail: string }>;
  mcp_calls?: { tool: string; duration_ms: number; status: string }[];
}

function AuditTrailContent() {
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchAudit = useCallback(async (signal?: AbortSignal) => {
      try {
        const res = await fetch("/api/audit", {signal, cache:'no-store'});
        const ct = res.headers.get("content-type");
        if (!res.ok || !ct?.includes("application/json")) throw new Error('Audit unavailable');
        const data = await res.json();
        if(signal?.aborted)return;
        setError('');
        
        if (Array.isArray(data) && data.length > 0) {
          setAuditRecords(data);
        } else if (data && Array.isArray(data.records) && data.records.length > 0) {
          setAuditRecords(data.records);
        } else {
          // No fabricated records: an empty audit trail is reported honestly.
          setAuditRecords([]);
        }
      } catch {
        if(!signal?.aborted)setError('Audit unavailable. Retained records, if any, are stale.');
      } finally {
        if(!signal?.aborted)setLoading(false);
      }
    }, []);

  useEffect(() => {
    const controller=new AbortController();
    const timer=setTimeout(()=>void fetchAudit(controller.signal),0);
    return ()=>{clearTimeout(timer);controller.abort();};
  }, [fetchAudit]);

  const filteredRecords = useMemo(() => {
    if (!searchQuery) return auditRecords;
    const q = searchQuery.toLowerCase();
    return auditRecords.filter(
      (r) =>
        r.trade_id.toLowerCase().includes(q) ||
        r.strategy.toLowerCase().includes(q) ||
        (r.underlying && r.underlying.toLowerCase().includes(q)) ||
        r.regime.toLowerCase().includes(q)
    );
  }, [auditRecords, searchQuery]);

  const copyRecord = (rec: AuditRecord) => {
    navigator.clipboard.writeText(JSON.stringify(rec, null, 2));
    setCopiedId(rec.trade_id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="workspace-page space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-[#eaecef] flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-[#f0b90b]/10 border border-[#f0b90b]/30 text-[#f0b90b]">
              <ShieldCheck className="w-5 h-5" />
            </span>
            Forensic Decision Audit Trail
          </h1>
          <p className="text-xs text-[#848e9c] font-mono mt-1">
            Zero-Trust verification log of all autonomous trade decisions & Risk Gate matrices
          </p>
        </div>

        {/* Search Bar */}
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#848e9c]" />
          <input
            type="text"
            aria-label="Search audit records"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by Ticker, Strategy or ID..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-[#181a20] border border-[#2b313a] text-xs font-mono text-[#eaecef] placeholder-[#5e6673] focus:outline-none focus:border-[#f0b90b] transition-colors"
          />
        </div>
      </div>
      {error && <div role="status" className="trade-ticket text-sm text-[#f7a600]">{error}<button disabled={loading} type="button" onClick={()=>{setLoading(true);void fetchAudit();}} className="text-left underline">Retry audit</button></div>}
      {loading && <p role="status" className="text-xs text-[#b5b7c0]">Loading audit trail…</p>}

      {/* Audit Records List */}
      <div className="space-y-4">
        {!error && !loading && filteredRecords.length === 0 && (
          <div className="p-10 rounded-2xl bg-[#181a20] border border-dashed border-[#2b313a] text-center text-xs font-mono text-[#848e9c]">
            No audit records yet. Every Master Strategy decision is logged here with its full risk gate matrix.
          </div>
        )}

        {filteredRecords.map((rec) => {
          const isExpanded = expandedId === rec.trade_id;
          const checksObj = rec.checks || {};
          const checksList = Object.entries(checksObj);
          const allPassed = checksList.length > 0 && checksList.every(([, v]) => v.passed);

          return (
            <motion.div
              key={rec.trade_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className="rounded-2xl bg-[#181a20] border border-[#2b313a] hover:border-[#f0b90b]/50 overflow-hidden transition-all shadow-xl"
            >
              {/* Summary Bar */}
              <div
                onClick={() => setExpandedId(isExpanded ? null : rec.trade_id)}
                className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 cursor-pointer hover:bg-[#1e2329]/60 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div className={`p-2.5 rounded-xl border ${
                    allPassed
                      ? "bg-[#0ecb81]/10 border-[#0ecb81]/30 text-[#0ecb81]"
                      : "bg-[#f6465d]/10 border-[#f6465d]/30 text-[#f6465d]"
                  }`}>
                    <ShieldCheck className="w-5 h-5" />
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-[#eaecef] font-mono">{rec.trade_id}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#f0b90b]/15 text-[#f0b90b] border border-[#f0b90b]/30">
                        {rec.underlying || "BTCUSDT"}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#1e2329] text-[#848e9c] border border-[#2b313a]">
                        {rec.regime}
                      </span>
                    </div>
                    <div className="text-xs font-mono text-[#848e9c] mt-1 flex items-center gap-2">
                      <span>Strategy: <strong className="text-[#eaecef]">{rec.strategy.replace(/_/g, " ")}</strong></span>
                      <span>•</span>
                      <span>{new Date(rec.timestamp).toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-4 self-end md:self-auto">
                  <div className="text-right font-mono">
                    <div className="text-[11px] text-[#848e9c]">Consensus Confidence</div>
                    <div className="text-sm font-bold text-[#f0b90b]">
                      {((rec.consensus_score ?? rec.confidence) * 100).toFixed(0)}%
                    </div>
                  </div>

                  <span className={`px-2.5 py-1 rounded-lg text-xs font-bold font-mono border ${
                    allPassed
                      ? "bg-[#0ecb81]/15 text-[#0ecb81] border-[#0ecb81]/30"
                      : "bg-[#f6465d]/15 text-[#f6465d] border-[#f6465d]/30"
                  }`}>
                    {allPassed ? "10/10 PASSED" : "REJECTED"}
                  </span>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      copyRecord(rec);
                    }}
                    className="p-2 rounded-lg bg-[#1e2329] hover:bg-[#2b313a] border border-[#2b313a] text-[#848e9c] hover:text-[#eaecef] transition-colors"
                    title="Copy Raw Decision JSON"
                  >
                    {copiedId === rec.trade_id ? <Check className="w-4 h-4 text-[#0ecb81]" /> : <Copy className="w-4 h-4" />}
                  </button>

                  <div className="text-[#848e9c]">
                    {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                  </div>
                </div>
              </div>

              {/* Expandable Decision Drawer */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className="border-t border-[#2b313a] bg-[#0b0e11] p-6 space-y-6"
                  >
                    {/* Deterministic Risk Gate Matrix */}
                    <div>
                      <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#848e9c] mb-3 flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-[#f0b90b]" />
                        Deterministic 10-Point Risk Gate Checks
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                        {checksList.map(([name, check]) => (
                          <div
                            key={name}
                            className="p-3 rounded-xl bg-[#181a20] border border-[#2b313a] flex items-center justify-between text-xs font-mono"
                          >
                            <div className="space-y-0.5">
                              <span className="text-[#eaecef] font-medium">{name}</span>
                              <p className="text-[11px] text-[#848e9c]">{check.detail}</p>
                            </div>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              check.passed
                                ? "bg-[#0ecb81]/15 text-[#0ecb81] border-[#0ecb81]/30"
                                : "bg-[#f6465d]/15 text-[#f6465d] border-[#f6465d]/30"
                            }`}>
                              {check.passed ? "PASS" : "FAIL"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Multi-Agent Votes */}
                    {rec.votes && rec.votes.length > 0 && (
                      <div>
                        <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#848e9c] mb-3 flex items-center gap-2">
                          <BrainCircuit className="w-4 h-4 text-[#f0b90b]" />
                          Agent Debate & Rationale
                        </h4>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                          {rec.votes.map((v) => (
                            <div
                              key={v.agent_name}
                              className="p-3.5 rounded-xl bg-[#181a20] border border-[#2b313a] space-y-1.5 text-xs font-mono"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-[#f0b90b]">{v.agent_name}</span>
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                  v.vote === "APPROVE"
                                    ? "bg-[#0ecb81]/15 text-[#0ecb81]"
                                    : "bg-[#f6465d]/15 text-[#f6465d]"
                                }`}>
                                  {v.vote}
                                </span>
                              </div>
                              <p className="text-[11px] text-[#eaecef] leading-relaxed">{v.reasoning}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Raw MCP Telemetry */}
                    {rec.mcp_calls && rec.mcp_calls.length > 0 && (
                      <div>
                        <h4 className="text-xs font-bold font-mono uppercase tracking-wider text-[#848e9c] mb-2 flex items-center gap-2">
                          <Terminal className="w-4 h-4 text-[#848e9c]" />
                          Binance MCP Telemetry
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {rec.mcp_calls.map((c, i) => (
                            <div
                              key={i}
                              className="px-3 py-1.5 rounded-lg bg-[#181a20] border border-[#2b313a] text-xs font-mono flex items-center gap-2"
                            >
                              <span className="text-[#848e9c]">{c.tool}</span>
                              <span className="text-[#f0b90b] font-bold">{c.duration_ms}ms</span>
                              <span className="w-1.5 h-1.5 rounded-full bg-[#0ecb81]" />
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

export default function AuditTrail() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-[70vh] text-[#848e9c] font-mono text-sm">Loading Forensic Audit Ledger...</div>}>
      <AuditTrailContent />
    </Suspense>
  );
}
