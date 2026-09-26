import { useState } from "react";
import "./App.css";

function App() {
    const [username, setUsername] = useState("");
    const [fileName, setFileName] = useState<string | null>(null);
    const [filePath, setFilePath] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [report, setReport] = useState<any | null>(null);

    // Mock file selection for now (later we will use Tauri's dialog API to pick .dem files)
    const handleFileMock = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            setFileName(file.name);
            setFilePath(file.path); // Tauri exposes path on files
        }
    };

    const handleAnalyze = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!username || !filePath) {
            alert("Please enter your username and select a .dem replay file.");
            return;
        }

        setIsLoading(true);

        // Later: We will invoke our Python script or backend command here via Tauri
        setTimeout(() => {
            setIsLoading(false);
            setReport({
                match_id: "match_12345",
                user: username,
                final_win_prob: 87,
                outcome: "Victory",
                timeline_events: [
                    "From 0:15 to 6:15, your team steadily pulled ahead with no single decisive event, win chance moving from 61% to 77%.",
                    "Your teammate seiryuu died at 5:54, which hurt your win chance by 11% (now 72%).",
                    "The enemy Malorak died at 10:10, which boosted your win chance by 5% (now 87%)."
                ]
            });
        }, 1500);
    };

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 font-sans">
            <div className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-8">

                {/* Header */}
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400">
                        Deadlock Match Analyzer
                    </h1>
                    <p className="text-sm text-slate-400 mt-2">
                        Upload your local .dem replay file and enter your username for an AI-powered breakdown.
                    </p>
                </div>

                {!report ? (
                    /* Input Form */
                    <form onSubmit={handleAnalyze} className="space-y-6">
                        <div>
                            <label className="block text-sm font-medium text-slate-300 mb-2">
                                Deadlock Username
                            </label>
                            <input
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="e.g. seiryuu"
                                className="w-full px-4 py-3 bg-slate-950 border border-slate-800 rounded-xl focus:outline-none focus:border-indigo-500 text-slate-100 placeholder-slate-600 transition"
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-300 mb-2">
                                Match Replay (.dem)
                            </label>
                            <div className="border-2 border-dashed border-slate-800 hover:border-slate-700 rounded-xl p-6 text-center cursor-pointer transition relative bg-slate-950/50">
                                <input
                                    type="file"
                                    accept=".dem"
                                    onChange={handleFileMock}
                                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                                />
                                <div className="space-y-2">
                                    <svg className="mx-auto h-10 w-10 text-slate-500" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                                        <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                    </svg>
                                    <p className="text-sm text-slate-300 font-medium">
                                        {fileName ? <span className="text-indigo-400">{fileName}</span> : "Drop your .dem file here, or browse"}
                                    </p>
                                </div>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full py-3.5 px-4 bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold rounded-xl shadow-lg transition duration-200 disabled:opacity-50"
                        >
                            {isLoading ? "Analyzing Match & Running ML Model..." : "Generate Match Report"}
                        </button>
                    </form>
                ) : (
                    /* Temporary Report View */
                    <div className="space-y-6">
                        <div className="flex justify-between items-center bg-slate-950 p-4 rounded-xl border border-slate-800">
                            <div>
                                <span className="text-xs text-slate-500 uppercase tracking-wider">Outcome</span>
                                <p className="text-xl font-bold text-emerald-400">{report.outcome} ({report.final_win_prob}%)</p>
                            </div>
                            <button
                                onClick={() => setReport(null)}
                                className="text-xs px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-300 transition"
                            >
                                Analyze Another
                            </button>
                        </div>

                        <div className="space-y-3">
                            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Match Narrative</h3>
                            {report.timeline_events.map((line: string, index: number) => (
                                <div key={index} className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl text-sm text-slate-300">
                                    {line}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

            </div>
        </div>
    );
}

export default App;