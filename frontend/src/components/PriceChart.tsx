// frontend/src/components/PriceChart.tsx
// High-performance candlestick chart using Lightweight Charts.

import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickData, CandlestickSeries } from 'lightweight-charts';

interface PriceChartProps {
  data: CandlestickData[];
  latestTick?: { price: number; timestamp: string };
  symbol: string;
}

const PriceChart: React.FC<PriceChartProps> = ({ data, latestTick, symbol }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(45, 212, 191, 0.05)' },
        horzLines: { color: 'rgba(45, 212, 191, 0.05)' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: {
        borderColor: 'rgba(45, 212, 191, 0.1)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#2dd4bf',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#2dd4bf',
      wickDownColor: '#ef4444',
    });

    candlestickSeries.setData(data);
    
    chartRef.current = chart;
    seriesRef.current = candlestickSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data]);

  // Update chart with latest tick (simple implementation for now)
  useEffect(() => {
    if (seriesRef.current && latestTick) {
      // Logic to update the last candle or add a new one would go here
      // For this MVP, we rely on the parent providing periodic 'data' updates
      // every candle close.
    }
  }, [latestTick]);

  return (
    <div className="relative w-full">
      <div className="absolute top-2 left-4 z-10 flex items-center gap-2">
        <span className="text-teal-400 font-bold text-lg">{symbol}</span>
        {latestTick && (
          <span className="text-slate-300 font-mono">
            {latestTick.price.toLocaleString()}
          </span>
        )}
      </div>
      <div ref={chartContainerRef} className="w-full" />
    </div>
  );
};

export default PriceChart;
