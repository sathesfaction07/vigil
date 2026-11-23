const { useState, useRef, useEffect } = React;
const API = "http://localhost:5050";

function App() {
    const [mode, setMode] = useState("single"); // "single" | "batch"
    const [productId, setProductId] = useState("");
    const [marketplaces, setMarketplaces] = useState("US");
    const [jobs, setJobs] = useState([]);
    const [activeJob, setActiveJob] = useState(null);
    const [result, setResult] = useState(null);
    const [streaming, setStreaming] = useState(false);
    const [messages, setMessages] = useState([]);
    const fileInputRef = useRef(null);

    function submitSingle() {
        if (!productId.trim()) return;
        const mps = marketplaces.split(",").map(m => m.trim()).filter(Boolean);
        fetch(`${API}/api/analyze`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ product_id: productId, marketplaces: mps }),
        })
            .then(r => r.json())
            .then(data => {
                setActiveJob(data.job_id);
                setResult(null);
                setMessages([]);
                startStream(data.job_id);
            });
    }

    async function submitCSV(file) {
        const formData = new FormData();
        formData.append("file", file);
        const resp = await fetch(`${API}/api/batch/csv`, { method: "POST", body: formData });
        const data = await resp.json();
        setJobs(data.jobs || []);
        if (data.jobs?.length) {
            setActiveJob(data.jobs[0].job_id);
            startStream(data.jobs[0].job_id);
        }
    }

    function startStream(jobId) {
        setStreaming(true);
        setMessages([]);
        const src = new EventSource(`${API}/api/stream/${jobId}`);
        src.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type === "progress") {
                setMessages(prev => [...prev, data.message]);
            } else if (data.type === "complete") {
                setResult(data.result);
                setStreaming(false);
                src.close();
            } else if (data.type === "failed") {
                setMessages(prev => [...prev, `ERROR: ${data.error}`]);
                setStreaming(false);
                src.close();
            }
        };
    }

    function pollResult(jobId) {
        fetch(`${API}/api/result/${jobId}`).then(r => r.json()).then(data => {
            if (data.result) setResult(data.result);
        });
    }

    const classification = result?.classification;
    const badgeClass = classification === "VIOLATION" ? "badge-violation" : classification === "COMPLIANT" ? "badge-compliant" : "badge-uncertain";

    return (
        <div className="max-w-4xl mx-auto px-6 py-10">
            <nav className="fixed top-0 left-0 right-0 z-50 nav-blur border-b border-white/5">
                <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <span className="text-accent font-semibold text-sm tracking-wide">ContentGuard</span>
                        <span className="text-[10px] text-slate-500 font-mono bg-white/5 px-2 py-0.5 rounded">v2</span>
                    </div>
                    <div className="flex gap-1">
                        <button onClick={() => setMode("single")} className={`text-[11px] px-3 py-1 rounded-lg transition ${mode === "single" ? "bg-accent/10 text-accent" : "text-slate-500 hover:text-slate-300"}`}>Single</button>
                        <button onClick={() => setMode("batch")} className={`text-[11px] px-3 py-1 rounded-lg transition ${mode === "batch" ? "bg-accent/10 text-accent" : "text-slate-500 hover:text-slate-300"}`}>Batch CSV</button>
                    </div>
                </div>
            </nav>

            <div className="pt-20 space-y-6">
                {/* Input */}
                <div className="card glow p-6 fade-in">
                    {mode === "single" ? (
                        <div className="space-y-4">
                            <div>
                                <label className="text-[10px] uppercase tracking-wider text-slate-500 block mb-2">Product ID</label>
                                <input
                                    value={productId}
                                    onChange={e => setProductId(e.target.value)}
                                    onKeyDown={e => e.key === "Enter" && submitSingle()}
                                    placeholder="SKU-001"
                                    className="w-full px-4 py-2.5 bg-white/3 border border-white/8 rounded-xl text-sm font-mono outline-none focus:border-accent/40 transition"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] uppercase tracking-wider text-slate-500 block mb-2">Marketplaces</label>
                                <input
                                    value={marketplaces}
                                    onChange={e => setMarketplaces(e.target.value)}
                                    placeholder="US, DE, JP"
                                    className="w-full px-4 py-2.5 bg-white/3 border border-white/8 rounded-xl text-sm outline-none focus:border-accent/40 transition"
                                />
                            </div>
                            <button onClick={submitSingle} disabled={streaming} className="w-full bg-accent hover:bg-accent/90 text-surface font-semibold text-sm py-3 rounded-xl transition shadow-[0_0_20px_-5px_rgba(0,212,170,0.3)] disabled:opacity-40">
                                {streaming ? "Analyzing..." : "Analyze Product"}
                            </button>
                        </div>
                    ) : (
                        <div className="text-center py-8">
                            <div
                                onClick={() => fileInputRef.current?.click()}
                                className="cursor-pointer"
                            >
                                <div className="text-accent text-2xl mb-2">⬆</div>
                                <p className="text-sm text-slate-300">Upload CSV file</p>
                                <p className="text-[11px] text-slate-500 mt-1">Columns: product_id, marketplaces (optional)</p>
                            </div>
                            <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={e => e.target.files[0] && submitCSV(e.target.files[0])} />
                            {jobs.length > 0 && <p className="text-xs text-accent mt-4">{jobs.length} products enqueued</p>}
                        </div>
                    )}
                </div>

                {/* Stream */}
                {messages.length > 0 && (
                    <div className="card p-4 fade-in">
                        <label className="text-[10px] uppercase tracking-wider text-slate-500 block mb-2">Progress</label>
                        <div className="space-y-1 max-h-32 overflow-y-auto">
                            {messages.map((msg, i) => (
                                <div key={i} className="text-[11px] font-mono text-slate-400 flex items-center gap-2">
                                    <span className={`w-1.5 h-1.5 rounded-full ${i === messages.length - 1 && streaming ? "bg-accent animate-pulse" : "bg-slate-600"}`}></span>
                                    {msg}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Result */}
                {result && (
                    <div className="card glow p-6 fade-in space-y-5">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <span className={`text-xs font-semibold px-3 py-1 rounded-full ${badgeClass}`}>{classification}</span>
                                <span className="text-sm font-mono text-slate-300">{result.confidence_pct}%</span>
                                <span className="text-[10px] text-slate-500 uppercase">{result.confidence_level}</span>
                            </div>
                            <span className="text-[10px] font-mono text-slate-500">{result.product_id}</span>
                        </div>

                        <div>
                            <label className="text-[10px] uppercase tracking-wider text-slate-500 block mb-1">Reasoning</label>
                            <p className="text-sm text-slate-300 leading-relaxed">{result.reasoning}</p>
                        </div>

                        {result.evidence?.length > 0 && (
                            <div>
                                <label className="text-[10px] uppercase tracking-wider text-slate-500 block mb-2">Evidence</label>
                                <div className="space-y-1">
                                    {result.evidence.map((e, i) => (
                                        <div key={i} className="text-[11px] font-mono text-slate-400 bg-white/3 px-3 py-1.5 rounded-lg">{e}</div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {result.keyword_matches?.length > 0 && (
                            <div>
                                <label className="text-[10px] uppercase tracking-wider text-slate-500 block mb-2">Keyword Matches</label>
                                <div className="flex flex-wrap gap-2">
                                    {result.keyword_matches.map((m, i) => (
                                        <span key={i} className={`text-[10px] px-2 py-0.5 rounded-full ${m.category === "red" ? "badge-violation" : "badge-compliant"}`}>
                                            [{m.language}] {m.keyword}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {result.entities_detected?.length > 0 && (
                            <div>
                                <label className="text-[10px] uppercase tracking-wider text-slate-500 block mb-2">Entities Detected</label>
                                <div className="flex flex-wrap gap-2">
                                    {result.entities_detected.map((e, i) => (
                                        <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-slate-400 border border-white/8">
                                            {e.entity_type}: {e.text}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="flex items-center gap-4 pt-2 border-t border-white/5">
                            {result.detected_language && <span className="text-[10px] text-slate-500">Language: {result.detected_language}</span>}
                            {result.marketplaces_scanned > 0 && <span className="text-[10px] text-slate-500">Marketplaces scanned: {result.marketplaces_scanned}</span>}
                            {result.multimodal && <span className="text-[10px] text-accent">Multimodal</span>}
                            {result.image_review_recommended && <span className="text-[10px] text-amber-400">Image review recommended</span>}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
