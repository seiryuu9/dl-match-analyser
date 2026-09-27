import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";

interface Player {
  username: string;
  team: number;
}

function App() {
  const [fileName, setFileName] = useState<string | null>(null);
  const [filePath, setFilePath] = useState<string | null>(null);
  
  const [step, setStep] = useState<"upload" | "select_user" | "report">("upload");
  const [isLoading, setIsLoading] = useState(false);
  
  const [availablePlayers, setAvailablePlayers] = useState<Player[]>([]);
  const [selectedUsername, setSelectedUsername] = useState("");
  const [report, setReport] = useState<any | null>(null);

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const name = file.name;
      const path = (file as any).path || name;
      
      setFileName(name);
      setFilePath(path);
      setIsLoading(true);
      
      try {
        const players: Player[] = await invoke("parse_replay_players", { filePath: path });
        
        setAvailablePlayers(players);
        setStep("select_user");
      } catch (error) {
        console.error("Failed to parse replay:", error);
        alert("Rust Backend Error: " + error);
      } finally {
        setIsLoading(false);
      }
    }
  };

  const handleAnalyze = async (e: React.FormEvent) => {
      e.preventDefault();
      if (!selectedUsername) return;

      setIsLoading(true);

      try {
        const reportData = await invoke("run_analysis", { username: selectedUsername });
        
        setReport(reportData);
        setStep("report");
      } catch (error) {
        console.error("Failed to analyze match:", error);
        alert("Analysis Error: " + error);
      } finally {
        setIsLoading(false);
      }
    };

  return (
    <div className="min-h-screen bg-[#0e0f17] text-[#dedede] font-['Inter',sans-serif] flex flex-col items-center justify-center p-8 selection:bg-[#d4af37]/30">
      
      {/* Container with Deadlock Brass Border */}
      <div className="w-full max-w-2xl bg-[#141622] border border-[#2d3148] shadow-[0_0_50px_rgba(0,0,0,0.8)] rounded-lg p-8 relative overflow-hidden">
        
        {/* Subtle Top Gold Accent Bar */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-[#b38938] via-[#f3eb88] to-[#b38938]" />

        {/* Title Header */}
        <div className="text-center mb-10">
          <h1 className="font-['Cinzel',serif] text-4xl font-black tracking-widest text-transparent bg-clip-text bg-gradient-to-b from-[#fff2a1] via-[#d4af37] to-[#8a6a1c] drop-shadow-md uppercase">
            Deadlock Match Analyser
          </h1>
          <p className="text-xs text-[#8e95b0] lowercase tracking-widest mt-2 font-semibold">
            so you exactly know which teammates to flame {"<3"}
          </p>
        </div>

        {/* STEP 1: FILE UPLOAD */}
        {step === "upload" && (
          <div className="space-y-6">
            <div className="border-2 border-dashed border-[#2d3148] hover:border-[#d4af37]/60 rounded-lg p-10 text-center cursor-pointer transition-all duration-300 bg-[#090a10]/50 group relative">
              <input
                type="file"
                accept=".dem"
                onChange={handleFileSelected}
                disabled={isLoading}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <div className="space-y-4 pointer-events-none">
                <div className="w-12 h-12 mx-auto rounded-full bg-[#1e2235] border border-[#d4af37]/30 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <span className="text-[#d4af37] text-xl font-bold">🖹</span>
                </div>
                <div>
                  <p className="text-base font-semibold text-[#f0f0f0] font-['Cinzel',serif]">
                    {isLoading ? "PARSING REPLAY FILE..." : "SELECT .DEM REPLAY FILE"}
                  </p>
                  <p className="text-xs text-[#6e7590] mt-1">
                    Drag and drop your Deadlock demo file or click to browse
                  </p>
                </div>
              </div>
            </div>
            
            {/* Replay Path Note */}
            <div className="text-center text-[11px] text-[#6e7590]">
              <p className="mb-1 uppercase tracking-wider font-bold">Default Replay Folder:</p>
              <code className="bg-[#1e2235] border border-[#2d3148] px-3 py-1.5 rounded text-[#a6b0cf] select-all cursor-copy">
                C:\Program Files (x86)\Steam\steamapps\common\Deadlock\game\citadel\replays
              </code>
            </div>
          </div>
        )}

        {/* STEP 2: SELECT USERNAME */}
        {step === "select_user" && (
          <form onSubmit={handleAnalyze} className="space-y-6">
            <div className="flex items-center justify-between bg-[#090a10] px-4 py-3 rounded border border-[#23273a] text-xs">
              <span className="text-[#8e95b0]">Loaded Replay: <strong className="text-[#f3eb88]">{fileName}</strong></span>
              <button
                type="button"
                onClick={() => setStep("upload")}
                className="text-[#d4af37] hover:underline uppercase text-[10px] tracking-wider font-semibold"
              >
                Change File
              </button>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#b8becc] uppercase tracking-wider mb-2 font-['Cinzel',serif]">
                Select Your Player Name
              </label>
              <select
                value={selectedUsername}
                onChange={(e) => setSelectedUsername(e.target.value)}
                className="w-full px-4 py-3 bg-[#090a10] border border-[#2d3148] focus:border-[#d4af37] rounded text-sm text-[#f0f0f0] outline-none transition"
              >
                <option value="">-- Choose player from match --</option>
                {availablePlayers.map((p, idx) => (
                  <option key={idx} value={p.username}>
                    {p.username} — {p.team === 2 ? "Amber Team" : "Sapphire Team"}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={isLoading || !selectedUsername}
              className="w-full py-3.5 px-4 bg-gradient-to-r from-[#8a6a1c] via-[#d4af37] to-[#8a6a1c] hover:brightness-110 text-[#0e0f17] font-extrabold text-sm uppercase tracking-wider rounded transition shadow-md disabled:opacity-40 font-['Cinzel',serif]"
            >
              {isLoading ? "Running Model..." : "Generate Analysis Report"}
            </button>
          </form>
        )}

        {/* STEP 3: REPORT DISPLAY */}
        {step === "report" && report && (
          <div className="space-y-6">
            <div className="flex justify-between items-center bg-[#090a10] p-4 rounded border border-[#2d3148]">
              <div>
                <span className="text-[10px] text-[#6e7590] uppercase tracking-widest block font-bold">Player Report</span>
                <p className="text-lg font-bold text-[#f3eb88] font-['Cinzel',serif]">{report.user}</p>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-[#6e7590] uppercase tracking-widest block font-bold">Outcome</span>
                <p className="text-lg font-bold text-[#4ae2a2] font-['Cinzel',serif]">{report.outcome} ({report.final_win_prob}%)</p>
              </div>
            </div>

            <div className="space-y-3">
              <h3 className="text-xs font-bold text-[#b8becc] uppercase tracking-wider font-['Cinzel',serif]">Match Timeline & Insights</h3>
              {report.timeline_events.map((line: string, index: number) => (
                <div key={index} className="p-3 bg-[#090a10]/80 border border-[#23273a] rounded text-xs text-[#d0d4e0] leading-relaxed">
                  {line}
                </div>
              ))}
            </div>

            <button
              onClick={() => { setReport(null); setStep("upload"); }}
              className="w-full py-2.5 bg-[#1e2235] hover:bg-[#282d46] border border-[#2d3148] text-[#d4af37] text-xs font-bold uppercase tracking-wider rounded transition"
            >
              Analyze Another Match
            </button>
          </div>
        )}

      </div>
    </div>
  );
}

export default App;