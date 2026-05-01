import React from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, Zap, BarChart3, ArrowRight } from 'lucide-react';

const Home = () => {
  const menuOptions = [
    {
      id: 'signals',
      title: '🚀 Trading Signals',
      description: 'Real-time technical analysis & credit spread strategies based on RSI & Bollinger Bands',
      link: '/signals',
      icon: TrendingUp,
      color: 'from-blue-600 to-cyan-500',
      accentBg: 'bg-blue-900/20',
      accentBorder: 'border-blue-700/50',
    },
    {
      id: 'leap',
      title: '⚡ LEAP Calls',
      description: 'Find high-growth stocks with deep ITM LEAP call opportunities (2027-2028 expiry)',
      link: '/leap-calls',
      icon: Zap,
      color: 'from-purple-600 to-pink-500',
      accentBg: 'bg-purple-900/20',
      accentBorder: 'border-purple-700/50',
    },
    {
      id: 'screener',
      title: '📊 Stock Screener',
      description: 'Monitor your watchlist with technical indicators & Bollinger Bands analysis',
      link: '/screener',
      icon: BarChart3,
      color: 'from-emerald-600 to-teal-500',
      accentBg: 'bg-emerald-900/20',
      accentBorder: 'border-emerald-700/50',
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      {/* Header */}
      <nav className="bg-slate-900/95 backdrop-blur-md border-b border-slate-700 shadow-xl">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 p-3 rounded-xl shadow-lg">
              <TrendingUp className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-3xl font-black text-white">Trading Hub</h1>
          </div>
          <p className="text-slate-400 text-sm font-semibold">Advanced trading strategies & market analysis</p>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-16">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-black text-white mb-4">Choose Your Strategy</h2>
          <p className="text-slate-400 text-lg font-semibold">
            Select a trading tool to get started
          </p>
        </div>

        {/* Menu Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
          {menuOptions.map((option) => {
            const Icon = option.icon;
            return (
              <Link
                key={option.id}
                to={option.link}
                className="group"
              >
                <div className="h-full bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl overflow-hidden hover:border-slate-600 hover:bg-slate-800/70 transition-all shadow-xl hover:shadow-2xl hover:scale-105 cursor-pointer"
                >
                  {/* Card Header with Gradient */}
                  <div className={`h-32 bg-gradient-to-br ${option.color} relative overflow-hidden`}>
                    <div className="absolute inset-0 opacity-20">
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_50%,rgba(255,255,255,0.1),transparent)]"></div>
                    </div>
                    <div className="h-full flex items-end justify-end p-6">
                      <Icon className="w-16 h-16 text-white/80 group-hover:scale-110 transition-transform" />
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="p-6">
                    <h3 className="text-2xl font-black text-white mb-2">{option.title}</h3>
                    <p className="text-slate-400 font-medium mb-6 line-clamp-3">
                      {option.description}
                    </p>

                    {/* Features/Stats */}
                    <div className={`${option.accentBg} border ${option.accentBorder} rounded-lg p-4 mb-6`}>
                      <ul className="space-y-2 text-sm font-semibold text-slate-300">
                        {option.id === 'signals' && (
                          <>
                            <li>✓ Real-time RSI & Bollinger Bands</li>
                            <li>✓ Credit spread recommendations</li>
                            <li>✓ Options pricing (Black-Scholes)</li>
                          </>
                        )}
                        {option.id === 'leap' && (
                          <>
                            <li>✓ Fundamental screening (growth >15%)</li>
                            <li>✓ Deep ITM LEAP sweet spots</li>
                            <li>✓ Daily after-market scans</li>
                          </>
                        )}
                        {option.id === 'screener' && (
                          <>
                            <li>✓ Custom watchlist management</li>
                            <li>✓ Technical analysis tools</li>
                            <li>✓ Excel import/export</li>
                          </>
                        )}
                      </ul>
                    </div>

                    {/* CTA Button */}
                    <button className="w-full py-3 bg-white text-slate-900 font-bold rounded-lg hover:bg-slate-100 transition-all flex items-center justify-center gap-2 group/btn">
                      Launch
                      <ArrowRight className="w-4 h-4 group-hover/btn:translate-x-1 transition-transform" />
                    </button>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>

        {/* Info Box */}
        <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl p-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div>
              <h4 className="font-black text-white mb-2 text-lg">🎯 Signals</h4>
              <p className="text-slate-400 text-sm">
                Automated technical analysis generating credit spread signals when RSI hits extremes combined with Bollinger Band touch points.
              </p>
            </div>
            <div>
              <h4 className="font-black text-white mb-2 text-lg">⚡ LEAP Calls</h4>
              <p className="text-slate-400 text-sm">
                Identify high-growth stocks with attractive deep ITM LEAP options, scanned daily after market close.
              </p>
            </div>
            <div>
              <h4 className="font-black text-white mb-2 text-lg">📊 Screener</h4>
              <p className="text-slate-400 text-sm">
                Build custom watchlists, monitor technical levels, and export analysis reports for your trading desk.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Home;
