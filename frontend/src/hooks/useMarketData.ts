// frontend/src/hooks/useMarketData.ts
import { useQuery } from '@tanstack/react-query'

export interface MarketData {
  symbol: string
  price: number
  change_pct: number
  volume: number
  last_updated: number // unix timestamp
}

export function useMarketData(symbol: string = 'VN30F1M') {
  const { data, isLoading, error, dataUpdatedAt } = useQuery<MarketData>({
    queryKey: ['market-data', symbol],
    queryFn: async () => {
      const resp = await fetch(`http://localhost:8000/v1/market/overview?symbol=${symbol}`)
      if (!resp.ok) {
        throw new Error('Network response was not ok')
      }
      return resp.json()
    },
    refetchInterval: 10000, // Poll every 10s
    refetchOnWindowFocus: true,
  })

  // Detect stale data: if API fails or last update was over 60 seconds ago
  // Note: For daily resolution, the last_updated from DNSE might just be the start of the day.
  // We'll consider it stale if the query itself hasn't updated successfully in 30 seconds.
  const isStale = !data || (Date.now() - dataUpdatedAt > 30000)

  return {
    data,
    isLoading,
    error,
    isStale
  }
}
