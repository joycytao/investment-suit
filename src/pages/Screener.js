import React, { useState, useEffect, useRef } from 'react';
import { 
  TrendingUp, RefreshCw, Trash2, FileSpreadsheet, 
  Download, X, Mail, BarChart3, LayoutGrid, Search
} from 'lucide-react';

/**
 * 💡 使用說明：
 * 1. 請至 https://www.alphavantage.co/support/#api-key 申請免費 API Key
 */
const API_KEY = "EC11LHXL4KC9ZVKT"; 

// 引入 XLSX 庫 (透過 CDN)
const loadXLSX = () => {
  return new Promise((resolve) => {
    if (window.XLSX) return resolve(window.XLSX);
    const script = document.createElement('script');
    script.src = "https://cdn.sheetjs.com/xlsx-0.20.1/package/dist/xlsx.full.min.js";
    script.onload = () => resolve(window.XLSX);
    document.head.appendChild(script);
  });
};

const fetchAlphaVantageData = async (symbol) => {
  const sym = symbol.toUpperCase();
  if (!API_KEY) return { symbol: sym, error: true, errorMsg: "請填入 API Key" };

  try {
    const avUrl = `https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=${sym}&apikey=${API_KEY}`;
    const response = await fetch(avUrl);
    const data = await response.json();

    if (data["Note"]) throw new Error("API 頻率限制 (每分鐘 5 次)");
    if (data["Error Message"]) throw new Error("找不到標的");
    if (!data["Time Series (Daily)"]) throw new Error("數據暫不可用");
    
    const timeSeries = data["Time Series (Daily)"];
    const dates = Object.keys(timeSeries).slice(0, 20);
    const prices = dates.map(date => parseFloat(timeSeries[date]["4. close"]));
    const currentPrice = prices[0];
    const ma20 = prices.reduce((a, b) => a + b, 0) / prices.length;
    const variance = prices.reduce((a, b) => a + Math.pow(b - ma20, 2), 0) / prices.length;
    const stdDev = Math.sqrt(variance);

    const upper = ma20 + (stdDev * 2);
    const lower = ma20 - (stdDev * 2);

    return {
      symbol: sym,
      price: currentPrice,
      ma20: ma20,
      upper: upper,
      lower: lower,
      status: currentPrice >= upper ? 'overbought' : (currentPrice <= lower ? 'oversold' : 'neutral'),
      lastUpdate: new Date().toLocaleTimeString()
    };
  } catch (error) {
    return { symbol: sym, error: true, errorMsg: error.message };
  }
};

const Screener = () => {
  const [watchlist, setWatchlist] = useState([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [lastUpdate, setLastUpdate] = useState('尚未更新');
  const fileInputRef = useRef(null);
  
  // 匯出彈窗狀態
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [emailInput, setEmailInput] = useState('');
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    const savedList = localStorage.getItem('alpha_vantage_watchlist_pro');
    if (savedList) {
      setWatchlist(JSON.parse(savedList));
      setLastUpdate(new Date().toLocaleTimeString());
    }
  }, []);

  useEffect(() => {
    localStorage.setItem('alpha_vantage_watchlist_pro', JSON.stringify(watchlist));
  }, [watchlist]);

  const processInBatches = async (symbolsToFetch) => {
    if (symbolsToFetch.length === 0) return;
    setLoading(true);
    setProgress({ current: 0, total: symbolsToFetch.length });
    
    let updatedResults = [...watchlist];
    let successCount = 0;
    let failedSymbols = [];
    
    for (let i = 0; i < symbolsToFetch.length; i++) {
      const sym = symbolsToFetch[i].trim().toUpperCase();
      if (!sym) continue;
      
      setProgress(prev => ({ ...prev, current: i + 1 }));
      const data = await fetchAlphaVantageData(sym);
      
      if (!data.error) {
        successCount++;
        const index = updatedResults.findIndex(s => s.symbol === sym);
        if (index > -1) {
          updatedResults[index] = data;
        } else {
          updatedResults.unshift(data);
        }
      } else {
        failedSymbols.push({ symbol: sym, reason: data.errorMsg });
      }
      
      // 確保符合免費版 1 分鐘 5 次限制
      if (i < symbolsToFetch.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 13000));
      }
    }
    
    // 所有 API 調用完成後，一次性更新 watchlist
    setWatchlist(updatedResults);
    
    setLastUpdate(new Date().toLocaleTimeString());
    setLoading(false);
    setProgress({ current: 0, total: 0 });
    
    // 顯示結果摘要
    const totalCount = successCount + failedSymbols.length;
    console.log(`✅ 成功: ${successCount}/${totalCount} | ❌ 失敗: ${failedSymbols.length}`);
    
    if (successCount > 0) {
      let message = `✅ 成功添加 ${successCount} 隻`;
      if (failedSymbols.length > 0) {
        message += `\n❌ 失敗 ${failedSymbols.length} 隻: ${failedSymbols.map(s => s.symbol).join(', ')}`;
      }
      alert(message);
    } else if (failedSymbols.length > 0) {
      alert(`❌ 全部失敗\n${failedSymbols.map(s => `${s.symbol}: ${s.reason}`).join('\n')}`);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const XLSX = await loadXLSX();
    const reader = new FileReader();

    reader.onload = (event) => {
      try {
        const data = new Uint8Array(event.target.result);
        const workbook = XLSX.read(data, { type: 'array' });
        const firstSheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[firstSheetName];
        
        // 使用 sheet_to_json 讀取第一列（列A）
        const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 'A' });
        
        // 提取所有非空的 A 列值
        const symbols = Object.values(jsonData)
          .map(row => row?.A)
          .filter(cell => cell && typeof cell === 'string')
          .map(s => s.trim().toUpperCase());
        
        console.log('讀取的所有股票:', symbols);
        
        // 移除重複並過濾已在 watchlist 中的
        const uniqueSymbols = [...new Set(symbols)].filter(s => !watchlist.some(w => w.symbol === s));
        
        console.log(`📊 Excel 中共 ${symbols.length} 隻 | 新增 ${uniqueSymbols.length} 隻`);
        
        if (uniqueSymbols.length > 0) {
          processInBatches(uniqueSymbols);
        } else {
          alert('沒有新的股票代碼要導入');
        }
      } catch (error) {
        console.error('Excel 解析錯誤:', error);
        alert('讀取 Excel 失敗: ' + error.message);
      }
    };
    
    reader.readAsArrayBuffer(file);
    e.target.value = null;
  };

  const addStock = () => {
    if (!newSymbol.trim()) {
      alert('請輸入股票代碼');
      return;
    }
    
    const sym = newSymbol.trim().toUpperCase();
    
    // 檢查是否已經在 watchlist 中
    if (watchlist.some(w => w.symbol === sym)) {
      alert(`${sym} 已經在清單中`);
      return;
    }
    
    console.log(`➕ 新增股票: ${sym}`);
    processInBatches([sym]);
    setNewSymbol('');
  };

  const handleExport = () => {
    setIsExporting(true);
    // 模擬發送 API
    setTimeout(() => {
      setIsExporting(false);
      setIsModalOpen(false);
      setEmailInput('');
      // 在 Canvas 內不能用 alert，改用 console 或狀態顯示
      console.log("報告已發送至: " + emailInput);
    }, 2000);
  };

  const filteredList = watchlist.filter(s => filter === 'all' || s.status === filter);

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 font-sans">
      <nav className="sticky top-0 z-40 bg-white/80 backdrop-blur-md border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-600 p-2 rounded-xl shadow-lg shadow-indigo-200">
              <TrendingUp className="text-white w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-800 tracking-tight">美股策略掃描器</h1>
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">
                {loading ? `隊列處理中: ${progress.current}/${progress.total}` : `最後更新: ${lastUpdate}`}
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={handleFileUpload} 
              className="hidden" 
              accept=".xlsx,.xls,.csv"
            />
            <button 
              onClick={() => fileInputRef.current.click()}
              disabled={loading || !API_KEY}
              className="px-4 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 font-bold text-sm flex items-center gap-2 transition-all disabled:opacity-50"
            >
              <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
              <span className="hidden sm:inline">匯入</span>
            </button>
            <button 
              onClick={() => processInBatches(watchlist.map(s => s.symbol))}
              disabled={loading || !API_KEY || watchlist.length === 0}
              className="px-4 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 font-bold text-sm flex items-center gap-2 transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">刷新</span>
            </button>
            <button 
              onClick={() => setIsModalOpen(true)}
              className="px-4 py-2.5 rounded-xl bg-indigo-600 text-white font-bold text-sm flex items-center gap-2 shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all"
            >
              <Download className="w-4 h-4" />
              <span className="hidden sm:inline">匯出報告</span>
            </button>
          </div>
        </div>
        {loading && (
          <div className="absolute bottom-0 left-0 h-1 bg-indigo-600 transition-all duration-500" style={{ width: `${(progress.current / progress.total) * 100}%` }} />
        )}
      </nav>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <section className="mb-10">
          <div className="bg-white p-2 rounded-[2rem] shadow-xl flex flex-col md:flex-row items-center gap-2 border border-slate-100">
            <div className="relative flex-1 w-full">
              <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-slate-300 w-5 h-5" />
              <input 
                type="text" 
                placeholder="輸入代號並按下 Enter..."
                className="w-full pl-14 pr-6 py-4 bg-transparent border-none focus:ring-0 text-lg font-bold uppercase"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addStock()}
              />
            </div>
            <button 
              onClick={addStock}
              disabled={loading || !API_KEY}
              className="px-8 py-4 bg-slate-900 text-white rounded-[1.5rem] font-bold disabled:opacity-50 w-full md:w-auto hover:bg-black transition-all"
            >
              {loading ? '隊列中' : '新增標的'}
            </button>
          </div>
        </section>

        <div className="flex flex-col lg:flex-row gap-8">
          <aside className="lg:w-72 flex-shrink-0 space-y-4">
            <div className="bg-white rounded-[2rem] p-6 shadow-sm border border-slate-200/50">
              <h3 className="text-xs font-black text-slate-400 uppercase mb-6 flex items-center gap-2">數據過濾</h3>
              <div className="space-y-1.5">
                {['all', 'overbought', 'oversold'].map(id => (
                  <button
                    key={id}
                    onClick={() => setFilter(id)}
                    className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl text-sm font-bold transition-all ${
                      filter === id ? 'bg-indigo-50 text-indigo-600' : 'text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    <BarChart3 className="w-4 h-4" />
                    {id === 'all' ? '所有標的' : id === 'overbought' ? '賣出 Call 訊號' : '賣出 Put 訊號'}
                  </button>
                ))}
              </div>
            </div>
          </aside>

          <section className="flex-1">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {filteredList.map(stock => (
                <div key={stock.symbol} className="bg-white rounded-[2.5rem] border border-slate-100 shadow-sm p-8 hover:shadow-md transition-all group">
                  <div className="flex justify-between items-start mb-6">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-slate-900 rounded-xl flex items-center justify-center text-white font-black">{stock.symbol[0]}</div>
                      <h4 className="text-2xl font-black">{stock.symbol}</h4>
                    </div>
                    <button 
                      onClick={() => setWatchlist(watchlist.filter(s => s.symbol !== stock.symbol))}
                      className="text-slate-200 hover:text-rose-500 transition-colors"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </div>
                  <div className="bg-slate-50 rounded-3xl p-6 mb-4 flex justify-between items-end">
                    <div>
                      <p className="text-[10px] font-bold text-slate-400 mb-1 uppercase tracking-widest">實時收盤價</p>
                      <p className="text-3xl font-black text-slate-900">${stock.price?.toFixed(2) || '---'}</p>
                    </div>
                    <div className={`px-4 py-2 rounded-xl text-[10px] font-black text-white uppercase shadow-sm ${
                      stock.status === 'overbought' ? 'bg-rose-500' : stock.status === 'oversold' ? 'bg-emerald-500' : 'bg-slate-300'
                    }`}>
                      {stock.status === 'overbought' ? '賣出 Call' : stock.status === 'oversold' ? '賣出 Put' : '觀望'}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-4 bg-white border border-slate-100 rounded-2xl">
                      <p className="text-[9px] font-bold text-slate-400 uppercase mb-1">布林上軌</p>
                      <p className="font-black text-slate-700">${stock.upper?.toFixed(2)}</p>
                    </div>
                    <div className="p-4 bg-white border border-slate-100 rounded-2xl">
                      <p className="text-[9px] font-bold text-slate-400 uppercase mb-1">布林下軌</p>
                      <p className="font-black text-slate-700">${stock.lower?.toFixed(2)}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {filteredList.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20 bg-white rounded-[3rem] border border-dashed border-slate-200">
                <LayoutGrid className="w-12 h-12 text-slate-200 mb-4" />
                <p className="text-slate-400 font-bold">目前沒有標的，請新增或匯入 Excel</p>
              </div>
            )}
          </section>
        </div>

        {/* 匯出彈窗 */}
        {isModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-slate-900/60 backdrop-blur-md">
            <div className="bg-white w-full max-w-lg rounded-[3rem] shadow-2xl p-10 animate-in zoom-in-95 duration-200 relative">
              <button 
                onClick={() => setIsModalOpen(false)}
                className="absolute top-8 right-8 text-slate-300 hover:text-slate-500"
              >
                <X className="w-8 h-8" />
              </button>
              
              <div className="mb-8">
                <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center text-indigo-600 mb-6">
                  <Mail className="w-8 h-8" />
                </div>
                <h3 className="text-3xl font-black text-slate-800 mb-2">匯出分析報告</h3>
                <p className="text-slate-500 font-medium">我們將整理目前 {watchlist.length} 隻標的的策略建議並發送至您的信箱。</p>
              </div>

              <div className="space-y-4 mb-8">
                <input 
                  type="email"
                  placeholder="your-email@example.com"
                  className="w-full p-5 bg-slate-50 border-2 border-transparent focus:border-indigo-600 focus:bg-white rounded-2xl transition-all font-bold text-lg outline-none"
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                />
              </div>

              <button 
                onClick={handleExport}
                disabled={!emailInput || isExporting}
                className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white py-6 rounded-3xl font-black text-xl flex items-center justify-center gap-3 transition-all shadow-xl shadow-indigo-200"
              >
                {isExporting ? <RefreshCw className="animate-spin w-6 h-6" /> : <Mail className="w-6 h-6" />}
                {isExporting ? '發送中...' : '發送報告'}
              </button>
              
              <p className="mt-6 text-center text-[10px] text-slate-400 font-bold uppercase tracking-widest">
                PDF & CSV format included
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default Screener;
