import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import Home from './pages/Home';
import Signals from './pages/Signals';
import LeapCalls from './pages/LeapCalls';
import DayTrading from './pages/DayTrading';
import Screener from './pages/Screener';
import Settings from './pages/Settings';

const Navigation = () => {
  const location = useLocation();
  
  const isActive = (path) => location.pathname === path;
  
  // Don't show nav on home page
  if (location.pathname === '/') {
    return null;
  }
  
  return (
    <nav className="sticky top-0 z-50 bg-slate-900/95 backdrop-blur-md border-b border-slate-700 shadow-xl">
      <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
          <h1 className="text-xl font-black text-white">Trading Hub</h1>
        </Link>
        <div className="flex gap-2">
          <Link
            to="/signals"
            className={`px-4 py-2 rounded-lg font-semibold transition-all ${
              isActive('/signals') 
                ? 'bg-blue-600 text-white' 
                : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            Signals
          </Link>
          <Link
            to="/leap-calls"
            className={`px-4 py-2 rounded-lg font-semibold transition-all ${
              isActive('/leap-calls') 
                ? 'bg-purple-600 text-white' 
                : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            LEAP Calls
          </Link>
          <Link
            to="/day-trading"
            className={`px-4 py-2 rounded-lg font-semibold transition-all ${
              isActive('/day-trading') 
                ? 'bg-amber-600 text-white' 
                : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            Day Trading
          </Link>
          <Link
            to="/settings"
            className={`px-4 py-2 rounded-lg font-semibold transition-all ${
              isActive('/settings') 
                ? 'bg-pink-600 text-white' 
                : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            Settings
          </Link>
        </div>
      </div>
    </nav>
  );
};

const App = () => {
  return (
    <Router basename="/screener">
      <Navigation />
      <Routes>
        {/* Home/Menu - homepage */}
        <Route path="/" element={<Home />} />

        {/* Trading Signals */}
        <Route path="/signals" element={<Signals />} />

        {/* LEAP Calls */}
        <Route path="/leap-calls" element={<LeapCalls />} />

        {/* Day Trading */}
        <Route path="/day-trading" element={<DayTrading />} />

        {/* Settings for symbol management */}
        <Route path="/settings" element={<Settings />} />

        {/* Hidden Screener page (accessible but not in navigation) */}
        <Route path="/screener" element={<Screener />} />

        {/* Catch-all redirect to homepage */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
};

export default App;
