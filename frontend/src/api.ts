export interface User {
  id: number
  email: string
  role: 'customer' | 'merchant' | 'admin'
  display_name: string | null
  avatar_url: string | null
  is_suspended: boolean
}

export interface MerchantStore {
  id: number
  name: string
  address: string
  description: string
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
  image_url: string | null
  seller_id: number | null
  store_name: string | null
  store_address: string | null
}

export interface ProductReview {
  id: number
  product_id: number
  rating: number
  content: string
  author_name: string
  created_at: string
  updated_at: string
  can_edit: boolean
}

export interface ProductReviewSummary {
  total: number
  average_rating: number | null
}

export interface AdminMerchant {
  id: number
  email: string
  role: 'merchant'
  display_name: string | null
  avatar_url: string | null
  is_suspended: boolean
  store_name: string | null
  store_address: string | null
}

export interface AdminReviewReport {
  id: number
  review_id: number
  product_id: number
  product_name: string
  reporter_name: string
  reason: string
  status: 'open' | 'resolved' | 'dismissed'
  review_content: string
  created_at: string
}

export interface AdminReviewReportPage {
  items: AdminReviewReport[]
  total: number
  limit: number
  offset: number
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
  expires_at: string | null
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
  fulfillments: MerchantFulfillment[]
}

export interface MerchantFulfillment {
  id: number
  seller_id: number | null
  store_name: string
  status: string
  shipping_carrier: string | null
  tracking_number: string | null
  shipped_at: string | null
  delivered_at: string | null
  items: OrderItem[]
}

export interface MerchantOrder {
  fulfillment_id: number
  order_id: number
  status: string
  created_at: string
  customer_email: string
  recipient_name: string | null
  recipient_phone: string | null
  shipping_region: string | null
  shipping_address: string | null
  postal_code: string | null
  subtotal: string
  items: OrderItem[]
}

export interface AdminOrder extends Order {
  customer_email: string
}

export interface AdminOrderPage {
  items: AdminOrder[]
  total: number
  limit: number
  offset: number
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

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const isFormData = options.body instanceof FormData
  const body: BodyInit | undefined =
    options.body === undefined
      ? undefined
      : options.body instanceof FormData
        ? options.body
        : JSON.stringify(options.body)
  const response = await fetch(`${API_BASE_URL}/api${path}`, {
    method: options.method ?? 'GET',
    headers: {
      ...(options.body === undefined || isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    ...(body === undefined ? {} : { body }),
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
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
