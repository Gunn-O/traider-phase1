import { useState, useEffect, useRef, useCallback } from 'react'

export function useWebSocket() {
  const [data, setData] = useState(null)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectRef = useRef(null)
  const mountedRef = useRef(true)

  const getWsUrl = () => {
    // ใช้ relative URL เสมอ
    // → Vite proxy จัดการ port ให้อัตโนมัติ
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    return `${protocol}//${host}/ws`
  }

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    try {
      const url = getWsUrl()
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) return
        setIsConnected(true)
        console.log('✅ WebSocket connected:', url)
        if (reconnectRef.current) {
          clearTimeout(reconnectRef.current)
          reconnectRef.current = null
        }
      }

      ws.onmessage = (e) => {
        if (!mountedRef.current) return
        try {
          setData(JSON.parse(e.data))
        } catch (err) {
          console.warn('WS parse error:', err)
        }
      }

      ws.onclose = (e) => {
        if (!mountedRef.current) return
        setIsConnected(false)
        console.log('⚠️ WebSocket closed, reconnecting in 3s...')
        reconnectRef.current = setTimeout(connect, 3000)
      }

      ws.onerror = (err) => {
        console.warn('⚠️ WebSocket error — backend running?')
        ws.close()
      }

    } catch (err) {
      console.error('WS connect error:', err)
      if (mountedRef.current) {
        reconnectRef.current = setTimeout(connect, 3000)
      }
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current)
      }
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  return { data, isConnected }
}
