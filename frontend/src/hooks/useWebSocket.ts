// frontend/src/hooks/useWebSocket.ts
// Custom React hook for WebSocket connection to the backend.

import { useEffect, useRef, useState, useCallback } from 'react'

export interface WSMessage {
  type: 'CONNECTION' | 'HEARTBEAT' | 'TICK' | 'SIGNAL' | 'DECISION' | 'POSITION' | 'POSITION_CLOSED' | 'SYSTEM_STATUS' | 'EXECUTION' | 'AI_INSIGHT' | 'RECOMMENDATION'
  timestamp: string
  [key: string]: any
}

interface UseWebSocketReturn {
  messages: WSMessage[]
  isConnected: boolean
  latestTick: any | null
  latestSignal: any | null
  latestStatus: any | null
  latestInsight: any | null
  latestRecommendation: any | null
  sendMessage: (data: object) => void
  clearMessages: () => void
}

const MAX_MESSAGES = 100

export function useWebSocket(url: string): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState<WSMessage[]>([])
  const [latestTick, setLatestTick] = useState<any | null>(null)
  const [latestSignal, setLatestSignal] = useState<any | null>(null)
  const [latestStatus, setLatestStatus] = useState<any | null>(null)
  const [latestInsight, setLatestInsight] = useState<any | null>(null)
  const [latestRecommendation, setLatestRecommendation] = useState<any | null>(null)

  const sendMessage = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const clearMessages = useCallback(() => setMessages([]), [])

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>

    const connect = () => {
      try {
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          setIsConnected(true)
          console.log('🔌 Connected to VN AI Trader WebSocket')
        }

        ws.onmessage = (event) => {
          try {
            const msg: WSMessage = JSON.parse(event.data)
            
            // Centralized message handling
            if (msg.type === 'TICK') {
              setLatestTick(msg.data)
            } else if (msg.type === 'SIGNAL') {
              setLatestSignal(msg.data)
            } else if (msg.type === 'SYSTEM_STATUS') {
              setLatestStatus(msg.data)
            } else if (msg.type === 'AI_INSIGHT') {
              setLatestInsight(msg.data)
            } else if (msg.type === 'RECOMMENDATION') {
              setLatestRecommendation(msg.data)
            }

            setMessages(prev => [msg, ...prev].slice(0, MAX_MESSAGES))
          } catch (err) {
            console.error('Failed to parse WS message:', err)
          }
        }

        ws.onclose = () => {
          setIsConnected(false)
          wsRef.current = null
          console.log('🔌 WebSocket disconnected. Reconnecting...')
          reconnectTimer = setTimeout(connect, 5000) // Changed reconnect interval to 5 seconds
        }

        ws.onerror = (err) => {
          console.error('WebSocket error:', err)
          ws.close()
        }
      } catch (err) {
        console.error('Failed to connect WebSocket:', err)
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [url])

  return { messages, isConnected, latestTick, latestSignal, latestStatus, latestInsight, latestRecommendation, sendMessage, clearMessages }
}

