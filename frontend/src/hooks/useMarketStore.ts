// frontend/src/hooks/useMarketStore.ts
// Zustand store for centralized, reactive market data state.
// Fed by WebSocket TICK + MARKET_STATUS messages from the backend.

import { create } from 'zustand'

export type ConnectionStatus = 'connected' | 'disconnected' | 'reconnecting' | 'connecting'
export type FeedSource = 'dnse_websocket' | 'dnse_rest' | 'mock' | 'unknown'

export type MarketSessionStatus = 'OPEN' | 'CLOSED' | 'UNKNOWN'

export interface MarketTick {
  symbol: string
  price: number
  prevPrice: number
  change: number
  changePct: number
  volume: number
  high: number
  low: number
  sessionVolume: number
  source: FeedSource
  lastUpdated: string        // ISO timestamp
}

export interface MarketStore {
  // Market data
  ticks: Record<string, MarketTick>

  // Feed status
  connectionStatus: ConnectionStatus
  feedSource: FeedSource
  isStale: boolean
  marketSession: MarketSessionStatus
  lastTickAt: string | null
  reconnectCount: number
  lastError: string | null

  // Actions
  updateFromTick: (data: any) => void
  updateFeedStatus: (data: any) => void
  reset: () => void
}


export const useMarketStore = create<MarketStore>((set, get) => ({
  ticks: {},

  connectionStatus: 'disconnected',
  feedSource: 'unknown',
  isStale: true,
  marketSession: 'UNKNOWN',
  lastTickAt: null,
  reconnectCount: 0,
  lastError: null,

  updateFromTick: (data: any) => {
    if (!data || !data.symbol) return

    const symbol = data.symbol
    const prev = get().ticks[symbol]
    const prevPrice = prev?.price || data.price

    const tick: MarketTick = {
      symbol,
      price: data.price ?? 0,
      prevPrice,
      change: data.change ?? (data.price - prevPrice),
      changePct: data.change_pct ?? 0,
      volume: data.volume ?? 0,
      high: data.high ?? prev?.high ?? data.price,
      low: data.low ?? prev?.low ?? data.price,
      sessionVolume: data.session_volume ?? data.volume ?? 0,
      source: (data.source as FeedSource) ?? 'unknown',
      lastUpdated: data.timestamp ?? new Date().toISOString(),
    }

    set((state) => ({
      ticks: { ...state.ticks, [symbol]: tick },
      isStale: false,
      lastTickAt: tick.lastUpdated,
    }))
  },

  updateFeedStatus: (data: any) => {
    if (!data) return
    set({
      connectionStatus: (data.connection_status as ConnectionStatus) ?? 'disconnected',
      feedSource: (data.source as FeedSource) ?? 'unknown',
      isStale: data.is_stale ?? true,
      marketSession: (data.market_session as MarketSessionStatus) ?? 'UNKNOWN',
      lastTickAt: data.last_tick_at ?? null,
      reconnectCount: data.reconnect_count ?? 0,
      lastError: data.last_error ?? null,
    })
  },

  reset: () => set({
    ticks: {},
    connectionStatus: 'disconnected',
    feedSource: 'unknown',
    isStale: true,
    marketSession: 'UNKNOWN',
    lastTickAt: null,
    reconnectCount: 0,
    lastError: null,
  }),
}))
