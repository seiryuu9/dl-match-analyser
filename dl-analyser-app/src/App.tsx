import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

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
  
  // State for toggling the timeline dropdown
  const [showTimeline, setShowTimeline] = useState(false);

  // Native Tauri File Picker Dialog
  const handleOpenFileDialog = async () => {
    try {
      const selected = await open({
        multiple: false,
        filters: [{
          name: 'Deadlock Replays',
          extensions: ['dem']
        }]
      });

      if (selected && typeof selected === 'string') {
        const path = selected;
        const name = path.split("\\").pop()?.split("/").pop() || "replay.dem";
        
        setFileName(name);
        setFilePath(path);
        setIsLoading(true);
        setShowTimeline(false);
        
        const players: Player[] = await invoke("parse_replay_players", { filePath: path });
        
        const sortedPlayers = [...players].sort((a, b) => {
          if (a.team !== b.team) {
            return a.team - b.team; 
          }
          return a.username.localeCompare(b.username, undefined, { sensitivity: "base" });
        });

        setAvailablePlayers(sortedPlayers);
        setStep("select_user");
      }
    } catch (error) {
      console.error("Failed to parse replay:", error);
      alert("Rust Backend Error: " + error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAnalyze = async (e: React.FormEvent) => {
      e.preventDefault();
      if (!selectedUsername || !filePath) return;

      setIsLoading(true);

      try {
        const reportData = await invoke("run_analysis", { 
          username: selectedUsername, 
          filePath: filePath 
        });
        
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
            <div 
              onClick={isLoading ? undefined : handleOpenFileDialog}
              className={`border-2 border-dashed ${isLoading ? 'border-[#d4af37] bg-[#090a10]' : 'border-[#2d3148] hover:border-[#d4af37]/60 bg-[#090a10]/50'} rounded-lg p-10 text-center cursor-pointer transition-all duration-300 group relative`}
            >
              <div className="space-y-4 pointer-events-none">
                <div className="w-12 h-12 mx-auto rounded-full bg-[#1e2235] border border-[#d4af37]/30 flex items-center justify-center group-hover:scale-110 transition-transform">
                  {isLoading ? (
                    <div className="w-5 h-5 border-2 border-[#d4af37] border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <span className="text-[#d4af37] text-xl font-bold">🖹</span>
                  )}
                </div>
                <div>
                  <p className="text-base font-semibold text-[#f0f0f0] font-['Cinzel',serif] flex items-center justify-center gap-2">
                    {isLoading ? (
                      <>
                        PARSING REPLAY FILE
                        <span className="flex gap-1">
                          <span className="w-1.5 h-1.5 bg-[#d4af37] rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                          <span className="w-1.5 h-1.5 bg-[#d4af37] rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                          <span className="w-1.5 h-1.5 bg-[#d4af37] rounded-full animate-bounce"></span>
                        </span>
                      </>
                    ) : (
                      "SELECT .DEM REPLAY FILE"
                    )}
                  </p>
                  <p className="text-xs text-[#6e7590] mt-1">
                    {isLoading ? "" : "Click to browse for any Deadlock demo file on your PC"}
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
            {/* Back Button Header */}
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setStep("upload")}
                className="text-xs text-[#d4af37] hover:text-[#fff2a1] font-bold uppercase tracking-wider flex items-center gap-1.5 transition-colors"
              >
                <span>←</span> Back to Upload
              </button>
            </div>

            <div className="flex items-center justify-between bg-[#090a10] px-4 py-3 rounded border border-[#23273a] text-xs">
              <span className="text-[#8e95b0]">Loaded Replay: <strong className="text-[#f3eb88]">{fileName}</strong></span>
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
                
                <optgroup label="Amber Team">
                  {availablePlayers
                    .filter((p) => p.team === 2)
                    .map((p, idx) => (
                      <option key={idx} value={p.username}>
                        {p.username}
                      </option>
                    ))}
                </optgroup>

                <optgroup label="Sapphire Team">
                  {availablePlayers
                    .filter((p) => p.team !== 2)
                    .map((p, idx) => (
                      <option key={idx} value={p.username}>
                        {p.username}
                      </option>
                    ))}
                </optgroup>
              </select>
            </div>

            <button
              type="submit"
              disabled={isLoading || !selectedUsername}
              className="w-full py-3.5 px-4 bg-gradient-to-r from-[#8a6a1c] via-[#d4af37] to-[#8a6a1c] hover:brightness-110 text-[#0e0f17] font-extrabold text-sm uppercase tracking-wider rounded transition shadow-md disabled:opacity-40 font-['Cinzel',serif] flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  RUNNING MODEL
                  <span className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-[#0e0f17] rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                    <span className="w-1.5 h-1.5 bg-[#0e0f17] rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                    <span className="w-1.5 h-1.5 bg-[#0e0f17] rounded-full animate-bounce"></span>
                  </span>
                </>
              ) : (
                "Generate Analysis Report"
              )}
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
                <p className={`text-lg font-bold font-['Cinzel',serif] ${report.outcome === "Victory" ? "text-[#4ae2a2]" : "text-[#e24a4a]"}`}>
                  {report.outcome} ({Number(report.final_win_prob).toFixed(2)}%)
                </p>
              </div>
            </div>

            {/* Split events into Summary (last 2) and Timeline (the rest) */}
            <div className="space-y-3">
              {report.timeline_events.slice(-2).map((line: string, index: number) => (
                <div 
                  key={`summary-${index}`} 
                  className="p-4 bg-gradient-to-r from-[#211a0d] to-[#141007] border border-[#d4af37]/40 rounded text-sm text-[#f3eb88] leading-relaxed font-semibold shadow-[0_4px_20px_rgba(212,175,55,0.08)]"
                >
                  {line}
                </div>
              ))}
            </div>

            {/* Expandable Timeline Section */}
            {report.timeline_events.length > 2 && (
              <div className="flex flex-col items-center pt-2">
                <button
                  onClick={() => setShowTimeline(!showTimeline)}
                  className="text-[10px] text-[#d4af37] hover:text-[#fff2a1] font-bold uppercase tracking-widest flex flex-col items-center gap-1.5 transition-colors"
                >
                  {showTimeline ? "Hide Full Match Timeline" : "See Entire Match Timeline & Swings"}
                  <span className={`transform transition-transform duration-300 ${showTimeline ? "rotate-180" : ""}`}>
                    ▼
                  </span>
                </button>
                
                {/* Expanding Content */}
                <div 
                  className={`w-full overflow-hidden transition-all duration-500 ease-in-out ${
                    showTimeline ? "max-h-[800px] opacity-100 mt-5 overflow-y-auto pr-2 custom-scrollbar" : "max-h-0 opacity-0 mt-0"
                  }`}
                >
                  <div className="space-y-3 border-t border-[#23273a] pt-5">
                    {report.timeline_events.slice(0, -2).map((line: string, index: number) => (
                      <div 
                        key={`timeline-${index}`} 
                        className="p-3 bg-[#090a10]/80 border border-[#23273a] rounded text-xs text-[#d0d4e0] leading-relaxed"
                      >
                        {line}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <button
              onClick={() => { 
                setReport(null); 
                setStep("upload"); 
                setShowTimeline(false); 
              }}
              className="w-full py-2.5 bg-[#1e2235] hover:bg-[#282d46] border border-[#2d3148] text-[#d4af37] text-xs font-bold uppercase tracking-wider rounded transition mt-4"
            >
              Analyse Another Match
            </button>
          </div>
        )}

      </div>
      
      {/* Custom Scrollbar CSS */}
      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: #0e0f17;
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #2d3148;
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #d4af37;
        }
      `}} />
    </div>
  );
}

export default App;