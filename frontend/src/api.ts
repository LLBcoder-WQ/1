export interface User {
  id: number
  email: string
  role: 'customer' | 'admin'
}

export interface Category {
  id: number
  name: string
}

export interface Product {
  id: number
  sku: string
  name: string
  description: string
  price: string
  stock: number
  is_active: boolean
  category_id: number | null
}

export interface CartLine {
  product_id: number
  product_name: string
  unit_price: string
  quantity: number
  line_total: string
}

export interface Cart {
  items: CartLine[]
  subtotal: string
}

export interface OrderItem {
  product_id: number
  product_name: string
  unit_price: string
  quantity: number
}

export interface Order {
  id: number
  status: string
  subtotal: string
  discount: string
  total: string
  coupon_code: string | null
  recipient_name: string | null
  recipient_phone: string | null
  shipping_region: string | null
  shipping_address: string | null
  postal_code: string | null
  shipping_carrier: string | null
  tracking_number: string | null
  shipped_at: string | null
  delivered_at: string | null
  created_at: string
  items: OrderItem[]
}

export interface AdminOrder extends Order {
  customer_email: string
}

export interface Coupon {
  id: number
  code: string
  discount_type: 'percent' | 'fixed'
  value: string
  min_subtotal: string
  max_uses: number | null
  uses_count: number
  is_active: boolean
}

interface ApiOptions {
  method?: string
  token?: string
  body?: unknown
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api${path}`, {
    method: options.method ?? 'GET',
    headers: {
      ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
  })

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload: { detail?: string | { msg?: string }[] } = await response.json()
      if (typeof payload.detail === 'string') message = payload.detail
      else if (Array.isArray(payload.detail)) {
        message = payload.detail.map((item) => item.msg ?? '请求参数无效').join('；')
      }
    } catch {
      // Keep the HTTP status message when the server response isn't JSON.
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
