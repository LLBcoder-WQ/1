<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  ApiError,
  api,
  type AdminOrder,
  type AdminMerchant,
  type AdminOrderPage,
  type AdminReviewReport,
  type AdminReviewReportPage,
  type Cart,
  type Category,
  type Coupon,
  type MerchantStore,
  type MerchantOrder,
  type Order,
  type Product,
  type ProductReview,
  type ProductReviewSummary,
  type User,
} from './api'

type View = 'shop' | 'favorites' | 'orders' | 'admin'
type AccountRole = 'customer' | 'merchant'
const heroSlides = [
  {
    eyebrow: 'SLOW LIVING, WELL MADE',
    title: '把日常过成',
    accent: '喜欢的样子。',
    description: '从一只手作花瓶开始，让平凡日子也有温柔光景。',
    note: 'THE EVERYDAY EDIT',
    stamp: '好物 · 慢选',
    scene: 'ceramics',
  },
  {
    eyebrow: 'A MOMENT TO UNWIND',
    title: '为一盏暖灯',
    accent: '留住好时光。',
    description: '一杯茶，一段闲暇，把生活调成喜欢的节奏。',
    note: 'A LITTLE PAUSE',
    stamp: '一盏 · 一刻',
    scene: 'tea',
  },
  {
    eyebrow: 'GROW AT YOUR OWN PACE',
    title: '让每一天',
    accent: '都有小确幸。',
    description: '自然的气息与恰好的陪伴，点亮日常每个角落。',
    note: 'A SOFTER EVERYDAY',
    stamp: '自然 · 相伴',
    scene: 'botanical',
  },
] as const
const heroSlideIndex = ref(0)
const heroPaused = ref(false)
let heroRotationTimer = 0
const currentHeroSlide = computed(() => heroSlides[heroSlideIndex.value]!)
const products = ref<Product[]>([])
const favoriteProducts = ref<Product[]>([])
const inventoryProducts = ref<Product[]>([])
const categories = ref<Category[]>([])
const cart = ref<Cart>({ items: [], subtotal: '0.00' })
const orders = ref<Order[]>([])
const adminOrders = ref<AdminOrder[]>([])
const merchantOrders = ref<MerchantOrder[]>([])
const adminMerchants = ref<AdminMerchant[]>([])
const reviewReports = ref<AdminReviewReport[]>([])
const reviewReportStatus = ref<'all' | 'open' | 'resolved' | 'dismissed'>('open')
const reviewReportOffset = ref(0)
const reviewReportTotal = ref(0)
const reviewReportLimit = 20
const merchantShipmentForms = ref<Record<number, { shipping_carrier: string; tracking_number: string }>>({})
const orderFilter = ref<'all' | 'pending_payment' | 'paid' | 'processing' | 'shipped' | 'delivered' | 'cancelled' | 'expired'>('all')
const adminOrderSearch = ref('')
const adminOrderOffset = ref(0)
const adminOrderTotal = ref(0)
const adminOrderLimit = 20
const shipmentForms = ref<Record<number, { shipping_carrier: string; tracking_number: string }>>({})
const coupons = ref<Coupon[]>([])
const user = ref<User | null>(null)
const merchantStore = ref<MerchantStore | null>(null)
const token = ref(localStorage.getItem('shop-token') ?? '')
const currentView = ref<View>('shop')
const selectedProduct = ref<Product | null>(null)
const productReviews = ref<ProductReview[]>([])
const reviewSummary = ref<ProductReviewSummary>({ total: 0, average_rating: null })
const reviewOffset = ref(0)
const hasMoreReviews = ref(false)
const reviewsLoading = ref(false)
const reviewSubmitting = ref(false)
const reviewDraft = ref({ rating: 5, content: '' })
const favoriteLoading = ref(false)
const activeCategory = ref<number | null>(null)
const search = ref('')
const inventorySearch = ref('')
const inventoryFilter = ref<'all' | 'active' | 'inactive' | 'low' | 'out'>('all')
const productOffset = ref(0)
const hasMoreProducts = ref(false)
const favoriteOffset = ref(0)
const hasMoreFavorites = ref(false)
const loading = ref(false)
const busy = ref(false)
const cartOpen = ref(false)
const authOpen = ref(false)
const accountOpen = ref(false)
const authMode = ref<'login' | 'register'>('login')
const authRole = ref<AccountRole>('customer')
const toast = ref('')
const error = ref('')
const couponCode = ref('')
const paymentMessage = ref('')
const shippingForm = ref({
  recipient_name: '',
  recipient_phone: '',
  shipping_region: '',
  shipping_address: '',
  postal_code: '',
})

const authForm = ref({ email: '', password: '', store_name: '' })
const profileForm = ref({ display_name: '' })
const passwordForm = ref({ current_password: '', new_password: '' })
const deletePassword = ref('')
const productImage = ref<File | null>(null)
const editingProductId = ref<number | null>(null)
const storeForm = ref({ name: '', address: '', description: '' })
const productForm = ref({
  sku: '',
  name: '',
  description: '',
  price: '',
  stock: '',
  category_id: '',
})
const categoryName = ref('')
const couponForm = ref({
  code: '',
  discount_type: 'percent' as 'percent' | 'fixed',
  value: '',
  min_subtotal: '0',
  max_uses: '',
})

const cartCount = computed(() => cart.value.items.reduce((sum, item) => sum + item.quantity, 0))
const favoriteProductIds = computed(() => new Set(favoriteProducts.value.map((product) => product.id)))
const averageRating = computed(() => {
  return reviewSummary.value.average_rating === null ? '暂无评分' : reviewSummary.value.average_rating.toFixed(1)
})
const averageRatingStars = computed(() => {
  if (reviewSummary.value.average_rating === null) return '☆☆☆☆☆'
  const roundedRating = Math.round(reviewSummary.value.average_rating)
  return '★'.repeat(roundedRating) + '☆'.repeat(5 - roundedRating)
})
const filteredProducts = computed(() => products.value)
const filteredInventoryProducts = computed(() => {
  const term = inventorySearch.value.trim().toLocaleLowerCase()
  return inventoryProducts.value.filter((product) => {
    const matchesSearch = !term || product.name.toLocaleLowerCase().includes(term) || product.sku.toLocaleLowerCase().includes(term)
    const matchesFilter = inventoryFilter.value === 'all'
      || (inventoryFilter.value === 'active' && product.is_active)
      || (inventoryFilter.value === 'inactive' && !product.is_active)
      || (inventoryFilter.value === 'low' && product.stock > 0 && product.stock <= 3)
      || (inventoryFilter.value === 'out' && product.stock === 0)
    return matchesSearch && matchesFilter
  })
})
const isAdmin = computed(() => user.value?.role === 'admin')
const isMerchant = computed(() => user.value?.role === 'merchant')
const canManageShop = computed(() => isAdmin.value || isMerchant.value)
const filteredAdminOrders = computed(() => adminOrders.value)

function shipmentForm(orderId: number) {
  shipmentForms.value[orderId] ??= { shipping_carrier: '', tracking_number: '' }
  return shipmentForms.value[orderId]
}

function orderStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending_payment: '待付款',
    paid: '已付款',
    processing: '待发货',
    shipped: '运输中',
    delivered: '已送达',
    cancelled: '已取消',
    expired: '已超时',
  }
  return labels[status] ?? status
}

function money(value: string | number) {
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value))
}

function formatUtcDateTime(value: string) {
  const isoValue = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`
  return new Date(isoValue).toLocaleString('zh-CN')
}

function notify(message: string) {
  toast.value = message
  window.setTimeout(() => {
    if (toast.value === message) toast.value = ''
  }, 2800)
}

function showError(message: string) {
  error.value = message
  window.setTimeout(() => {
    if (error.value === message) error.value = ''
  }, 4200)
}

async function loadStore(reset = true) {
  if (reset) productOffset.value = 0
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '24', offset: String(productOffset.value) })
    if (activeCategory.value !== null) params.set('category_id', String(activeCategory.value))
    if (search.value.trim()) params.set('search', search.value.trim())
    const [productList, categoryList] = await Promise.all([
      api<Product[]>(`/products?${params}`),
      categories.value.length ? Promise.resolve(categories.value) : api<Category[]>('/categories'),
    ])
    products.value = reset ? productList : [...products.value, ...productList]
    productOffset.value = products.value.length
    hasMoreProducts.value = productList.length === 24
    categories.value = categoryList
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '暂时无法连接商品服务')
  } finally {
    loading.value = false
  }
}

async function loadCart() {
  if (!token.value) {
    cart.value = { items: [], subtotal: '0.00' }
    return
  }
  cart.value = await api<Cart>('/cart', { token: token.value })
}

async function loadOrders(announceStatusChanges = true) {
  const updatedOrders = await api<Order[]>('/orders', { token: token.value })
  const previousStatuses = new Map(orders.value.map((order) => [order.id, order.status]))
  const changedOrders = updatedOrders.filter((order) => {
    const previousStatus = previousStatuses.get(order.id)
    return previousStatus !== undefined && previousStatus !== order.status
  })
  orders.value = updatedOrders
  if (announceStatusChanges && changedOrders.length) {
    notify(`${changedOrders.length} 笔订单状态有更新，请查看订单列表`)
  }
}

async function loadFavorites(reset = true) {
  if (!token.value) {
    favoriteProducts.value = []
    return
  }
  if (reset) favoriteOffset.value = 0
  const result = await api<Product[]>(`/favorites?limit=24&offset=${favoriteOffset.value}`, { token: token.value })
  favoriteProducts.value = reset ? result : [...favoriteProducts.value, ...result]
  favoriteOffset.value = favoriteProducts.value.length
  hasMoreFavorites.value = result.length === 24
}

async function loadProductReviews(productId: number, reset = true) {
  reviewsLoading.value = true
  try {
    if (reset) reviewOffset.value = 0
    const [reviews, summary] = await Promise.all([
      api<ProductReview[]>(`/products/${productId}/reviews?limit=20&offset=${reviewOffset.value}`, {
        token: token.value || undefined,
      }),
      reset
        ? api<ProductReviewSummary>(`/products/${productId}/reviews/summary`)
        : Promise.resolve(reviewSummary.value),
    ])
    if (selectedProduct.value?.id === productId) {
      productReviews.value = reset ? reviews : [...productReviews.value, ...reviews]
      reviewOffset.value = productReviews.value.length
      hasMoreReviews.value = reviews.length === 20
      reviewSummary.value = summary
    }
  } catch (reason) {
    if (selectedProduct.value?.id === productId) {
      showError(reason instanceof Error ? reason.message : '评论加载失败')
    }
  } finally {
    if (selectedProduct.value?.id === productId) reviewsLoading.value = false
  }
}

function loadMoreReviews() {
  if (selectedProduct.value) void loadProductReviews(selectedProduct.value.id, false)
}

async function openProductDetails(product: Product) {
  selectedProduct.value = product
  reviewDraft.value = { rating: 5, content: '' }
  productReviews.value = []
  void loadProductReviews(product.id)
  try {
    selectedProduct.value = await api<Product>(`/products/${product.id}`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '商品详情加载失败')
    selectedProduct.value = null
  }
}

function closeProductDetails() {
  selectedProduct.value = null
  productReviews.value = []
}

async function toggleFavorite(product: Product) {
  if (!user.value) {
    openAuth()
    return
  }
  if (favoriteLoading.value) return
  favoriteLoading.value = true
  try {
    const isFavorited = favoriteProductIds.value.has(product.id)
    await api<{ is_favorited: boolean }>(`/products/${product.id}/favorite`, {
      method: isFavorited ? 'DELETE' : 'PUT',
      token: token.value,
    })
    await loadFavorites()
    notify(isFavorited ? '已从收藏中移除' : '已收藏这件好物')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '收藏操作失败')
  } finally {
    favoriteLoading.value = false
  }
}

async function submitProductReview() {
  if (!user.value) {
    openAuth()
    return
  }
  if (!selectedProduct.value || !reviewDraft.value.content.trim()) return
  reviewSubmitting.value = true
  try {
    await api<ProductReview>(`/products/${selectedProduct.value.id}/reviews`, {
      method: 'POST',
      token: token.value,
      body: { rating: reviewDraft.value.rating, content: reviewDraft.value.content.trim() },
    })
    reviewDraft.value.content = ''
    await loadProductReviews(selectedProduct.value.id)
    notify('评论已发布')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '评论发布失败')
  } finally {
    reviewSubmitting.value = false
  }
}

async function deleteProductReview(review: ProductReview) {
  if (!selectedProduct.value || !window.confirm('确定删除这条评价吗？')) return
  try {
    await api<void>(`/products/${selectedProduct.value.id}/reviews/${review.id}`, {
      method: 'DELETE',
      token: token.value,
    })
    await loadProductReviews(selectedProduct.value.id)
    notify('评价已删除')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '评价删除失败')
  }
}

async function reportProductReview(review: ProductReview) {
  if (!selectedProduct.value) return
  const reason = window.prompt('请简要说明举报原因')
  if (!reason?.trim()) return
  try {
    await api<AdminReviewReport>(`/products/${selectedProduct.value.id}/reviews/${review.id}/reports`, {
      method: 'POST',
      token: token.value,
      body: { reason: reason.trim() },
    })
    notify('举报已提交，平台将进行审核')
  } catch (reasonError) {
    showError(reasonError instanceof Error ? reasonError.message : '举报提交失败')
  }
}

async function loadCoupons() {
  if (isAdmin.value) coupons.value = await api<Coupon[]>('/coupons', { token: token.value })
}

async function loadInventory() {
  if (canManageShop.value) {
    inventoryProducts.value = await api<Product[]>('/merchant/products', { token: token.value })
  }
}

async function loadMerchantStore() {
  if (isMerchant.value) {
    merchantStore.value = await api<MerchantStore>('/merchant/store', { token: token.value })
    storeForm.value = {
      name: merchantStore.value.name,
      address: merchantStore.value.address,
      description: merchantStore.value.description,
    }
  }
}

async function loadAdminOrders(reset = true) {
  if (isAdmin.value) {
    if (reset) adminOrderOffset.value = 0
    const params = new URLSearchParams({
      limit: String(adminOrderLimit),
      offset: String(adminOrderOffset.value),
    })
    if (orderFilter.value !== 'all') params.set('status', orderFilter.value)
    if (adminOrderSearch.value.trim()) params.set('search', adminOrderSearch.value.trim())
    const page = await api<AdminOrderPage>(`/admin/orders?${params}`, { token: token.value })
    adminOrders.value = page.items
    adminOrderTotal.value = page.total
  }
}

async function changeAdminOrderPage(direction: -1 | 1) {
  const nextOffset = adminOrderOffset.value + direction * adminOrderLimit
  if (nextOffset < 0 || nextOffset >= adminOrderTotal.value) return
  adminOrderOffset.value = nextOffset
  await loadAdminOrders()
}

async function loadMerchantOrders(announceStatusChanges = true) {
  if (!isMerchant.value) return
  const updatedOrders = await api<MerchantOrder[]>('/merchant/orders?limit=100', { token: token.value })
  const previousStatuses = new Map(merchantOrders.value.map((order) => [order.fulfillment_id, order.status]))
  const changedOrders = updatedOrders.filter((order) => {
    const previousStatus = previousStatuses.get(order.fulfillment_id)
    return previousStatus !== undefined && previousStatus !== order.status
  })
  merchantOrders.value = updatedOrders
  if (announceStatusChanges && changedOrders.length) {
    notify(`${changedOrders.length} 笔店铺订单状态有更新，请查看店铺订单`)
  }
}

async function loadAdminModeration() {
  if (!isAdmin.value) return
  const [merchants] = await Promise.all([
    api<AdminMerchant[]>('/admin/merchants', { token: token.value }),
  ])
  adminMerchants.value = merchants
  await loadAdminReports()
}

async function loadAdminReports(reset = true) {
  if (!isAdmin.value) return
  if (reset) reviewReportOffset.value = 0
  const params = new URLSearchParams({
    limit: String(reviewReportLimit),
    offset: String(reviewReportOffset.value),
  })
  if (reviewReportStatus.value !== 'all') params.set('status', reviewReportStatus.value)
  let page = await api<AdminReviewReportPage>(`/admin/review-reports?${params}`, { token: token.value })
  if (page.total > 0 && reviewReportOffset.value >= page.total) {
    reviewReportOffset.value = Math.floor((page.total - 1) / reviewReportLimit) * reviewReportLimit
    params.set('offset', String(reviewReportOffset.value))
    page = await api<AdminReviewReportPage>(`/admin/review-reports?${params}`, { token: token.value })
  }
  reviewReports.value = page.items
  reviewReportTotal.value = page.total
}

async function changeReviewReportPage(direction: -1 | 1) {
  const nextOffset = reviewReportOffset.value + direction * reviewReportLimit
  if (nextOffset < 0 || nextOffset >= reviewReportTotal.value) return
  reviewReportOffset.value = nextOffset
  await loadAdminReports(false)
}

function merchantShipmentForm(fulfillmentId: number) {
  merchantShipmentForms.value[fulfillmentId] ??= { shipping_carrier: '', tracking_number: '' }
  return merchantShipmentForms.value[fulfillmentId]
}

async function submitMerchantShipment(order: MerchantOrder) {
  try {
    await api<MerchantOrder>(`/merchant/orders/${order.order_id}/shipment`, {
      method: 'POST',
      token: token.value,
      body: merchantShipmentForm(order.fulfillment_id),
    })
    await loadMerchantOrders(false)
    notify(`订单 #${order.order_id} 已发货`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '登记发货失败')
  }
}

async function toggleMerchantStatus(merchant: AdminMerchant) {
  const is_suspended = !merchant.is_suspended
  try {
    const updated = await api<AdminMerchant>(`/admin/merchants/${merchant.id}/status`, {
      method: 'PATCH',
      token: token.value,
      body: { is_suspended },
    })
    adminMerchants.value = adminMerchants.value.map((item) => item.id === merchant.id ? updated : item)
    notify(is_suspended ? '商家账号已暂停' : '商家账号已恢复')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '商家状态更新失败')
  }
}

async function processReviewReport(report: AdminReviewReport, status: 'resolved' | 'dismissed') {
  try {
    const updated = await api<AdminReviewReport>(`/admin/review-reports/${report.id}`, {
      method: 'PATCH',
      token: token.value,
      body: { status },
    })
    if (reviewReportStatus.value === 'all') {
      reviewReports.value = reviewReports.value.map((item) => item.id === report.id ? updated : item)
    } else {
      await loadAdminReports(false)
    }
    notify(status === 'resolved' ? '已隐藏违规评论' : '举报已驳回')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '举报处理失败')
  }
}

async function exportAccountData() {
  try {
    const data = await api<Record<string, unknown>>('/account/export', { token: token.value })
    const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = `shiji-account-data-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    notify('个人数据已导出为 JSON 文件')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '个人数据导出失败')
  }
}

async function loadMoreProducts() {
  await loadStore(false)
}

async function loadMoreFavorites() {
  await loadFavorites(false)
}

async function submitShipment(order: AdminOrder) {
  const shipment = shipmentForm(order.id)
  try {
    await api<AdminOrder>(`/admin/orders/${order.id}/shipment`, {
      method: 'POST',
      token: token.value,
      body: shipment,
    })
    await loadAdminOrders()
    notify(`订单 #${order.id} 已登记发货`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '物流信息登记失败')
  }
}

async function confirmDelivery(order: AdminOrder) {
  try {
    await api<AdminOrder>(`/admin/orders/${order.id}/delivery`, {
      method: 'POST',
      token: token.value,
    })
    await loadAdminOrders(false)
    notify(`订单 #${order.id} 已标记送达`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '订单状态更新失败')
  }
}

function scrollToCollection() {
  document.getElementById('collection')?.scrollIntoView({ behavior: 'smooth' })
}

function showHeroSlide(index: number) {
  heroSlideIndex.value = (index + heroSlides.length) % heroSlides.length
}

function nextHeroSlide() {
  showHeroSlide(heroSlideIndex.value + 1)
}

function toggleHeroRotation() {
  heroPaused.value = !heroPaused.value
  startHeroRotation()
}

function startHeroRotation() {
  window.clearInterval(heroRotationTimer)
  if (currentView.value === 'shop' && !heroPaused.value && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    heroRotationTimer = window.setInterval(nextHeroSlide, 6000)
  }
}

function openAuth(mode: 'login' | 'register' = 'login') {
  authMode.value = mode
  authOpen.value = true
}

function openAccount() {
  if (!user.value) {
    openAuth()
    return
  }
  profileForm.value.display_name = user.value.display_name ?? ''
  passwordForm.value = { current_password: '', new_password: '' }
  deletePassword.value = ''
  accountOpen.value = true
}

async function submitAuth() {
  busy.value = true
  try {
    authForm.value.email = authForm.value.email.trim().toLowerCase()
    if (authMode.value === 'register') {
      await api<User>('/auth/register', {
        method: 'POST',
        body: {
          email: authForm.value.email,
          password: authForm.value.password,
          role: authRole.value,
          ...(authRole.value === 'merchant' ? { store_name: authForm.value.store_name.trim() } : {}),
        },
      })
    }
    const result = await api<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: {
        email: authForm.value.email,
        password: authForm.value.password,
        role: authRole.value,
      },
    })
    token.value = result.access_token
    localStorage.setItem('shop-token', token.value)
    user.value = await api<User>('/auth/me', { token: token.value })
    authOpen.value = false
    authForm.value.password = ''
    await Promise.all([loadCart(), loadFavorites(), loadOrders(false)])
    if (canManageShop.value) await Promise.all([loadInventory(), loadMerchantStore()])
    if (isAdmin.value) await Promise.all([loadCoupons(), loadAdminOrders(), loadAdminModeration()])
    if (isMerchant.value) await loadMerchantOrders()
    notify(`欢迎回来，${user.value.email}`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '登录失败，请稍后重试')
  } finally {
    busy.value = false
  }
}

async function restoreSession() {
  if (!token.value) return
  try {
    user.value = await api<User>('/auth/me', { token: token.value })
    await Promise.all([loadCart(), loadFavorites(), loadOrders(false)])
    if (canManageShop.value) await Promise.all([loadInventory(), loadMerchantStore()])
    if (isAdmin.value) await Promise.all([loadCoupons(), loadAdminOrders(), loadAdminModeration()])
    if (isMerchant.value) await loadMerchantOrders()
  } catch (reason) {
    if (reason instanceof ApiError && reason.status === 401) {
      token.value = ''
      user.value = null
      localStorage.removeItem('shop-token')
      return
    }
    showError(reason instanceof Error ? reason.message : '无法恢复登录状态，请稍后重试')
  }
}

function signOut() {
  token.value = ''
  user.value = null
  cart.value = { items: [], subtotal: '0.00' }
  favoriteProducts.value = []
  orders.value = []
  merchantStore.value = null
  coupons.value = []
  adminOrders.value = []
  merchantOrders.value = []
  adminMerchants.value = []
  reviewReports.value = []
  localStorage.removeItem('shop-token')
  currentView.value = 'shop'
  notify('已安全退出')
}

async function saveProfile() {
  try {
    user.value = await api<User>('/account/profile', {
      method: 'PATCH',
      token: token.value,
      body: { display_name: profileForm.value.display_name },
    })
    notify('账户资料已保存')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '资料保存失败')
  }
}

async function uploadAvatar(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    showError('图片不能超过 5 MB')
    ;(event.target as HTMLInputElement).value = ''
    return
  }
  const form = new FormData()
  form.append('image', file)
  try {
    user.value = await api<User>('/account/avatar', {
      method: 'POST',
      token: token.value,
      body: form,
    })
    notify('头像已更新')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '头像上传失败')
  } finally {
    ;(event.target as HTMLInputElement).value = ''
  }
}

async function changePassword() {
  try {
    await api<void>('/account/password', {
      method: 'PATCH',
      token: token.value,
      body: passwordForm.value,
    })
    passwordForm.value = { current_password: '', new_password: '' }
    signOut()
    notify('密码已修改，请使用新密码重新登录')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '密码修改失败')
  }
}

async function deleteAccount() {
  if (!window.confirm('确定注销账户吗？订单将保留并匿名化，商家商品会下架。此操作不能撤销。')) return
  try {
    await api<void>('/account', {
      method: 'DELETE',
      token: token.value,
      body: { password: deletePassword.value },
    })
    accountOpen.value = false
    signOut()
    notify('账户已注销，历史订单已匿名保留')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '账户注销失败')
  }
}

function selectProductImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (file && file.size > 5 * 1024 * 1024) {
    showError('图片不能超过 5 MB')
    input.value = ''
    productImage.value = null
    return
  }
  productImage.value = file
}

async function addToCart(product: Product) {
  if (!user.value) {
    openAuth()
    return
  }
  const existing = cart.value.items.find((item) => item.product_id === product.id)
  const quantity = (existing?.quantity ?? 0) + 1
  if (quantity > 99 || quantity > product.stock) {
    showError(quantity > 99 ? '单件商品最多购买 99 件' : '已达到这件商品的当前库存')
    return
  }
  try {
    cart.value = await api<Cart>('/cart/items', {
      method: 'POST',
      token: token.value,
      body: { product_id: product.id, quantity },
    })
    notify(`${product.name} 已加入购物袋`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '添加失败')
  }
}

async function updateCartItem(productId: number, quantity: number) {
  try {
    const product = products.value.find((item) => item.id === productId)
    if (quantity > 99 || (product && quantity > product.stock)) {
      showError(quantity > 99 ? '单件商品最多购买 99 件' : '已达到这件商品的当前库存')
      return
    }
    if (quantity <= 0) {
      await api<void>(`/cart/items/${productId}`, { method: 'DELETE', token: token.value })
    } else {
      await api<Cart>('/cart/items', {
        method: 'POST',
        token: token.value,
        body: { product_id: productId, quantity },
      })
    }
    await loadCart()
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '购物袋更新失败')
  }
}

async function checkout() {
  if (!cart.value.items.length) return
  busy.value = true
  try {
    const order = await api<Order>('/orders', {
      method: 'POST',
      token: token.value,
      body: {
        ...shippingForm.value,
        coupon_code: couponCode.value.trim() || null,
        postal_code: shippingForm.value.postal_code.trim() || null,
      },
    })
    cart.value = { items: [], subtotal: '0.00' }
    couponCode.value = ''
    shippingForm.value = {
      recipient_name: '',
      recipient_phone: '',
      shipping_region: '',
      shipping_address: '',
      postal_code: '',
    }
    cartOpen.value = false
    currentView.value = 'orders'
    await loadOrders(false)
    notify(`订单 #${order.id} 已创建`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '结账失败，请检查库存和优惠码')
  } finally {
    busy.value = false
  }
}

async function cancelOrder(order: Order) {
  try {
    await api<Order>(`/orders/${order.id}/cancel`, { method: 'POST', token: token.value })
    await Promise.all([loadOrders(false), loadStore()])
    notify(`订单 #${order.id} 已取消，库存已释放`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '订单暂时无法取消')
  }
}

async function startPayment(order: Order) {
  try {
    await api<Order>(`/orders/${order.id}/demo-payment`, { method: 'POST', token: token.value })
    paymentMessage.value = `订单 #${order.id} 已通过演示流程确认付款（没有真实收款）`
    await loadOrders(false)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '无法创建支付')
  }
}

async function confirmFulfillmentDelivery(order: Order, fulfillmentId: number) {
  try {
    await api<Order>(`/orders/${order.id}/fulfillments/${fulfillmentId}/delivery`, {
      method: 'POST',
      token: token.value,
    })
    await loadOrders(false)
    notify(`订单 #${order.id} 的店铺商品已确认收货`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '确认收货失败')
  }
}

function editReview(review: ProductReview) {
  reviewDraft.value = { rating: review.rating, content: review.content }
}

async function createProduct() {
  busy.value = true
  try {
    const body = {
      ...productForm.value,
      price: Number(productForm.value.price),
      stock: Number(productForm.value.stock),
      category_id: productForm.value.category_id ? Number(productForm.value.category_id) : null,
    }
    const created = await api<Product>(
      editingProductId.value ? `/products/${editingProductId.value}` : '/products',
      {
      method: editingProductId.value ? 'PATCH' : 'POST',
      token: token.value,
      body,
      },
    )
    const image = productImage.value
    productForm.value = { sku: '', name: '', description: '', price: '', stock: '', category_id: '' }
    productImage.value = null
    editingProductId.value = null
    const imageInput = document.getElementById('product-image') as HTMLInputElement | null
    if (imageInput) imageInput.value = ''
    if (image) {
      const form = new FormData()
      form.append('image', image)
      await api<Product>(`/products/${created.id}/image`, {
        method: 'POST',
        token: token.value,
        body: form,
      })
    }
    await Promise.all([loadStore(), loadInventory()])
    notify(image ? '商品和图片已保存' : '商品信息已保存')
  } catch (reason) {
    await loadInventory()
    showError(reason instanceof Error ? `商品保存或图片上传失败：${reason.message}` : '商品保存失败')
  } finally {
    busy.value = false
  }
}

function editProduct(product: Product) {
  editingProductId.value = product.id
  productForm.value = {
    sku: product.sku,
    name: product.name,
    description: product.description,
    price: product.price,
    stock: String(product.stock),
    category_id: product.category_id === null ? '' : String(product.category_id),
  }
  productImage.value = null
  document.getElementById('product-image')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function cancelProductEdit() {
  editingProductId.value = null
  productForm.value = { sku: '', name: '', description: '', price: '', stock: '', category_id: '' }
  productImage.value = null
  const imageInput = document.getElementById('product-image') as HTMLInputElement | null
  if (imageInput) imageInput.value = ''
}

async function saveMerchantStore() {
  try {
    merchantStore.value = await api<MerchantStore>('/merchant/store', {
      method: 'PATCH',
      token: token.value,
      body: storeForm.value,
    })
    notify('店铺资料已保存')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '店铺资料保存失败')
  }
}

async function createCategory() {
  const name = categoryName.value.trim()
  if (!name) return
  try {
    await api<Category>('/categories', { method: 'POST', token: token.value, body: { name } })
    categoryName.value = ''
    categories.value = await api<Category[]>('/categories')
    notify('分类已创建')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '分类创建失败')
  }
}

async function createCoupon() {
  busy.value = true
  try {
    await api<Coupon>('/coupons', {
      method: 'POST',
      token: token.value,
      body: {
        ...couponForm.value,
        value: Number(couponForm.value.value),
        min_subtotal: Number(couponForm.value.min_subtotal),
        max_uses: couponForm.value.max_uses ? Number(couponForm.value.max_uses) : null,
      },
    })
    couponForm.value = {
      code: '',
      discount_type: 'percent',
      value: '',
      min_subtotal: '0',
      max_uses: '',
    }
    await loadCoupons()
    notify('优惠码已创建')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '优惠码创建失败')
  } finally {
    busy.value = false
  }
}

async function toggleProduct(product: Product) {
  try {
    await api<Product>(`/products/${product.id}`, {
      method: 'PATCH',
      token: token.value,
      body: { is_active: !product.is_active },
    })
    await Promise.all([loadStore(), loadInventory()])
    notify(product.is_active ? '商品已下架' : '商品已重新上架')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '商品状态更新失败')
  }
}

async function changeView(view: View) {
  currentView.value = view
  if (view === 'favorites' && !user.value) {
    currentView.value = 'shop'
    openAuth()
    return
  }
  if (view === 'favorites' && user.value) {
    try {
      await loadFavorites()
    } catch (reason) {
      showError(reason instanceof Error ? reason.message : '收藏列表加载失败')
    }
  }
  if (view === 'orders' && user.value) {
    try {
      await loadOrders()
    } catch (reason) {
      showError(reason instanceof Error ? reason.message : '订单加载失败')
    }
  }
  if (view === 'admin' && !canManageShop.value) {
    currentView.value = 'shop'
    showError('该区域仅商家或管理员可访问')
  } else if (view === 'admin') {
    try {
      await Promise.all([loadInventory(), loadMerchantStore()])
      if (isAdmin.value) await Promise.all([loadCoupons(), loadAdminOrders(), loadAdminModeration()])
      if (isMerchant.value) await loadMerchantOrders()
    } catch (reason) {
      showError(reason instanceof Error ? reason.message : '管理数据加载失败')
    }
  }
}

function productTone(index: number) {
  return `tone-${index % 6}`
}

function categoryNameOf(id: number | null) {
  return categories.value.find((category) => category.id === id)?.name ?? '精选好物'
}

watch(currentView, startHeroRotation)

onMounted(async () => {
  startHeroRotation()
  await Promise.all([loadStore(), restoreSession()])
})

onUnmounted(() => {
  window.clearInterval(heroRotationTimer)
})

let searchTimer = 0
watch([activeCategory, search], () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => void loadStore(), 250)
})

let adminOrderSearchTimer = 0
watch([orderFilter, adminOrderSearch], () => {
  if (!isAdmin.value || currentView.value !== 'admin') return
  window.clearTimeout(adminOrderSearchTimer)
  adminOrderSearchTimer = window.setTimeout(() => void loadAdminOrders(), 250)
})

watch(reviewReportStatus, () => {
  if (isAdmin.value && currentView.value === 'admin') void loadAdminReports()
})
</script>

<template>
  <div class="app-shell">
    <div class="announcement">
      <span>为日常精选好物</span>
      <span class="announcement-note">满 ¥299 享免费配送 · 用心挑选，安心送达</span>
      <span class="announcement-right">自然 · 简单 · 持久</span>
    </div>

    <header class="site-header">
      <a class="wordmark" href="#" aria-label="拾集首页" @click.prevent="changeView('shop')">
        <span class="brand-mark">拾</span>
        <span>拾集 <small>SHIJI STUDIO</small></span>
      </a>
      <nav class="main-nav" aria-label="主导航">
        <button :class="{ selected: currentView === 'shop' }" @click="changeView('shop')">逛逛</button>
        <button v-if="user" :class="{ selected: currentView === 'favorites' }" @click="changeView('favorites')">
          我的收藏
        </button>
        <button v-if="user" :class="{ selected: currentView === 'orders' }" @click="changeView('orders')">
          我的订单
        </button>
        <button v-if="canManageShop" :class="{ selected: currentView === 'admin' }" @click="changeView('admin')">
          {{ isAdmin ? '平台管理' : '店铺管理' }}
        </button>
      </nav>
      <div class="header-actions">
        <label class="search-box">
          <span aria-hidden="true">⌕</span>
          <input v-model="search" placeholder="搜索好物" aria-label="搜索商品" @focus="changeView('shop')" />
          <kbd>⌘ K</kbd>
        </label>
        <button class="icon-button account-button" :aria-label="user ? '账户管理' : '登录'" @click="user ? openAccount() : openAuth()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5" /><path d="M4.5 20c.7-3.5 3.2-5.3 7.5-5.3s6.8 1.8 7.5 5.3" /></svg>
          <img v-if="user?.avatar_url" class="user-initial-avatar" :src="user.avatar_url" alt="" />
          <span v-else-if="user" class="user-initial">{{ (user.display_name || user.email)[0]?.toUpperCase() }}</span>
        </button>
        <button class="icon-button bag-button" aria-label="打开购物袋" @click="user ? (cartOpen = true) : openAuth()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8h14l1 12H4L5 8Z" /><path d="M9 9V6a3 3 0 0 1 6 0v3" /></svg>
          <span class="bag-count">{{ cartCount }}</span>
        </button>
      </div>
    </header>

    <main>
      <section v-if="currentView === 'shop'" class="storefront">
        <section class="hero" role="region" aria-label="首页主题封面" aria-roledescription="轮播">
          <div class="hero-copy">
            <div class="eyebrow"><span class="eyebrow-line"></span> {{ currentHeroSlide.eyebrow }}</div>
            <h1>{{ currentHeroSlide.title }}<br /><em>{{ currentHeroSlide.accent }}</em></h1>
            <p>{{ currentHeroSlide.description }}</p>
            <button class="button button-dark hero-cta" @click="scrollToCollection">
              探索精选 <span>↗</span>
            </button>
            <div class="hero-footnote"><span>{{ String(heroSlideIndex + 1).padStart(2, '0') }} — {{ String(heroSlides.length).padStart(2, '0') }}</span><span class="hero-dash"></span> {{ currentHeroSlide.note }}</div>
          </div>
          <Transition name="hero-scene" mode="out-in">
            <div :key="currentHeroSlide.scene" class="hero-art" :class="`scene-${currentHeroSlide.scene}`" role="img" :aria-label="`${currentHeroSlide.stamp}主题插画`">
              <div class="art-sun"></div>
              <div class="art-window"><span></span><i></i></div>
              <div class="art-shelf"></div>
              <div class="art-vase"><span></span></div>
              <div class="art-book book-one"></div>
              <div class="art-book book-two"></div>
              <div class="art-plant"><i></i><i></i><i></i><b></b></div>
              <div class="art-note">{{ currentHeroSlide.note }}</div>
              <span class="art-stamp">{{ currentHeroSlide.stamp }}</span>
            </div>
          </Transition>
          <div class="hero-index">精选生活 · 第 {{ String(heroSlideIndex + 1).padStart(2, '0') }} 期</div>
          <div class="hero-controls" aria-label="封面轮播控制">
            <button type="button" aria-label="上一张封面" @click="showHeroSlide(heroSlideIndex - 1)">‹</button>
            <div class="hero-dots" role="group" aria-label="选择封面">
              <button
                v-for="(_, index) in heroSlides"
                :key="index"
                type="button"
                :aria-label="`第 ${index + 1} 张封面`"
                :aria-current="heroSlideIndex === index ? 'true' : undefined"
                :class="{ active: heroSlideIndex === index }"
                @click="showHeroSlide(index)"
              ></button>
            </div>
            <button type="button" aria-label="下一张封面" @click="nextHeroSlide">›</button>
            <button type="button" :aria-label="heroPaused ? '继续自动轮播' : '暂停自动轮播'" @click="toggleHeroRotation">{{ heroPaused ? '▶' : 'Ⅱ' }}</button>
          </div>
        </section>

        <section class="value-strip" aria-label="店铺服务">
          <div><span class="value-icon">✳</span><span><b>认真挑选</b><small>品质优先，好物不将就</small></span></div>
          <div><span class="value-icon">⌂</span><span><b>自然材质</b><small>触手可及的温暖与质感</small></span></div>
          <div><span class="value-icon">↗</span><span><b>安心送达</b><small>妥善包装，准时抵达</small></span></div>
          <div class="strip-number">STUDIO NOTES &nbsp; / &nbsp; 2026</div>
        </section>

        <section id="collection" class="collection-section">
          <div class="section-heading">
            <div>
              <div class="eyebrow"><span class="eyebrow-line"></span> THE COLLECTION</div>
              <h2>为生活，选一点喜欢。</h2>
            </div>
            <p>实用之外，也留一点心意。<br />让每天都值得期待。</p>
          </div>
          <div class="collection-toolbar">
            <div class="category-tabs" aria-label="商品分类">
              <button :class="{ active: activeCategory === null }" @click="activeCategory = null">全部好物</button>
              <button
                v-for="category in categories"
                :key="category.id"
                :class="{ active: activeCategory === category.id }"
                @click="activeCategory = category.id"
              >
                {{ category.name }}
              </button>
            </div>
            <span class="product-count">已加载 {{ filteredProducts.length }} 件好物</span>
          </div>

          <div v-if="loading" class="empty-state"><span class="loading-mark"></span><p>正在为你准备好物…</p></div>
          <div v-else-if="filteredProducts.length" class="product-grid">
            <article
              v-for="(product, index) in filteredProducts"
              :key="product.id"
              class="product-card"
              @click="openProductDetails(product)"
            >
              <div class="product-visual" :class="productTone(index)">
                <span class="product-category">{{ categoryNameOf(product.category_id) }}</span>
                <img v-if="product.image_url" class="product-image" :src="product.image_url" :alt="product.name" />
                <div v-else class="product-object" aria-hidden="true">
                  <span class="object-shadow"></span>
                  <span class="object-shape" :class="`object-${index % 6}`"></span>
                  <span class="object-detail"></span>
                </div>
                <span class="product-number">NO. {{ (index + 1).toString().padStart(2, '0') }}</span>
                <span v-if="product.stock <= 3" class="stock-badge">{{ product.stock ? '少量现货' : '暂时售罄' }}</span>
                <button
                  v-if="user"
                  class="favorite-toggle"
                  :class="{ favorited: favoriteProductIds.has(product.id) }"
                  :aria-label="favoriteProductIds.has(product.id) ? '取消收藏' : '收藏商品'"
                  @click.stop="toggleFavorite(product)"
                >{{ favoriteProductIds.has(product.id) ? '♥' : '♡' }}</button>
                <button
                  class="quick-add"
                  :disabled="product.stock <= 0"
                  :aria-label="`将${product.name}加入购物袋`"
                  @click.stop="addToCart(product)"
                >
                  <span>+</span>
                </button>
              </div>
              <div class="product-info">
                <div><button class="product-title" @click.stop="openProductDetails(product)">{{ product.name }}</button><span class="product-sku">NO. {{ product.sku }}</span></div>
                <span class="product-price">{{ money(product.price) }}</span>
                <p>{{ product.description || '为日常而选，简约而不简单。' }}</p>
                <small v-if="product.store_name" class="product-store">{{ product.store_name }}<template v-if="product.store_address"> · {{ product.store_address }}</template></small>
              </div>
            </article>
          </div>
          <div v-else-if="!filteredProducts.length" class="empty-state">
            <span class="empty-flower">✳</span>
            <h3>{{ search || activeCategory ? '没有找到合适的好物' : '新一批好物，正在路上。' }}</h3>
            <p>{{ canManageShop ? '先到店铺管理发布商品，精选好物就会出现在这里。' : '店铺正在认真准备第一批精选，稍后再来看看吧。' }}</p>
            <button v-if="canManageShop" class="button button-outline" @click="changeView('admin')">去发布商品 <span>↗</span></button>
            <button v-else-if="search || activeCategory" class="text-button" @click="search = ''; activeCategory = null">查看全部好物 ↗</button>
          </div>
          <div v-if="hasMoreProducts && !loading" class="pagination-actions">
            <button class="button button-outline" @click="loadMoreProducts">加载更多好物</button>
          </div>
        </section>

        <section class="editor-note">
          <span class="editor-icon">“</span>
          <div><p>喜欢的东西，不需要很多。</p><span>THE LITTLE THINGS MAKE A LIFE.</span></div>
          <span class="editor-aside">拾集 · 好好生活研究所</span>
        </section>
      </section>

      <section v-if="currentView === 'favorites'" class="page-section favorites-page">
        <div class="page-kicker">YOUR ACCOUNT &nbsp; / &nbsp; 02</div>
        <div class="page-title-row"><div><div class="eyebrow"><span class="eyebrow-line"></span> SAVED FINDS</div><h1>我的收藏<span class="title-period">.</span></h1></div><p>喜欢的好物，先替你收好。</p></div>
        <div v-if="!favoriteProducts.length" class="empty-state order-empty">
          <span class="empty-flower">♡</span><h3>收藏夹还是空的</h3><p>打开商品详情，点击收藏就能在这里找到它。</p>
          <button class="button button-dark" @click="changeView('shop')">去逛逛 <span>↗</span></button>
        </div>
        <div v-else class="favorite-list">
          <article v-for="product in favoriteProducts" :key="product.id" class="favorite-card">
            <button class="favorite-card-main" @click="openProductDetails(product)">
              <img v-if="product.image_url" :src="product.image_url" :alt="product.name" />
              <span v-else class="favorite-card-placeholder">拾</span>
              <span class="favorite-card-info"><b>{{ product.name }}</b><small>{{ product.description || '为日常而选，简约而不简单。' }}</small><strong>{{ money(product.price) }}</strong></span>
            </button>
            <button class="favorite-remove" :aria-label="`取消收藏${product.name}`" @click="toggleFavorite(product)">移出收藏</button>
          </article>
        </div>
        <div v-if="hasMoreFavorites" class="pagination-actions">
          <button class="button button-outline" @click="loadMoreFavorites">加载更多收藏</button>
        </div>
      </section>

      <section v-if="currentView === 'orders'" class="page-section">
        <div class="page-kicker">YOUR ACCOUNT &nbsp; / &nbsp; 01</div>
        <div class="page-title-row"><div><div class="eyebrow"><span class="eyebrow-line"></span> ORDER HISTORY</div><h1>我的订单<span class="title-period">.</span></h1></div><p>每一次喜欢，都有迹可循。</p></div>
        <div v-if="!orders.length" class="empty-state order-empty"><span class="empty-flower">✳</span><h3>还没有订单记录</h3><p>选一件喜欢的好物，开始你的拾集。</p><button class="button button-dark" @click="changeView('shop')">继续逛逛 <span>↗</span></button></div>
        <div v-else class="order-list">
          <article v-for="order in orders" :key="order.id" class="order-card">
            <div class="order-top"><div><span class="order-label">ORDER</span><strong>#{{ order.id.toString().padStart(5, '0') }}</strong></div><span class="order-status" :class="`status-${order.status}`">{{ orderStatusLabel(order.status) }}</span></div>
            <p v-if="order.status === 'pending_payment' && order.expires_at" class="order-expiration">请在 {{ formatUtcDateTime(order.expires_at) }} 前完成演示付款，超时后会自动取消并释放库存。</p>
            <div class="order-items"><div v-for="item in order.items" :key="item.product_id" class="order-line"><span>{{ item.product_name }} <small>× {{ item.quantity }}</small></span><span>{{ money(Number(item.unit_price) * item.quantity) }}</span></div></div>
            <div v-if="order.recipient_name" class="order-shipping"><b>收货信息</b><span>{{ order.recipient_name }} · {{ order.recipient_phone }}</span><span>{{ order.shipping_region }} {{ order.shipping_address }}<template v-if="order.postal_code"> · {{ order.postal_code }}</template></span></div>
            <div v-if="order.shipping_carrier && order.tracking_number" class="order-tracking"><b>物流信息</b><span>{{ order.shipping_carrier }} · 运单号 {{ order.tracking_number }}</span><small v-if="order.shipped_at">发货时间：{{ new Date(order.shipped_at).toLocaleString('zh-CN') }}</small><small v-if="order.delivered_at">签收时间：{{ new Date(order.delivered_at).toLocaleString('zh-CN') }}</small></div>
            <div v-for="fulfillment in order.fulfillments" :key="fulfillment.id" class="order-tracking">
              <b>{{ fulfillment.store_name }} · {{ orderStatusLabel(fulfillment.status) }}</b>
              <span>{{ fulfillment.items.map((item) => `${item.product_name} × ${item.quantity}`).join('、') }}</span>
              <span v-if="fulfillment.shipping_carrier && fulfillment.tracking_number">{{ fulfillment.shipping_carrier }} · 运单号 {{ fulfillment.tracking_number }}</span>
              <small v-if="fulfillment.shipped_at">发货时间：{{ new Date(fulfillment.shipped_at).toLocaleString('zh-CN') }}</small>
              <button v-if="fulfillment.status === 'shipped'" class="text-button" @click="confirmFulfillmentDelivery(order, fulfillment.id)">确认收货</button>
            </div>
            <div class="order-bottom"><div><span v-if="order.coupon_code" class="order-coupon">优惠码 {{ order.coupon_code }} · 已优惠 {{ money(order.discount) }}</span><span>合计 <b>{{ money(order.total) }}</b></span></div><div v-if="order.status === 'pending_payment'" class="order-actions"><button class="text-button" @click="cancelOrder(order)">取消订单</button><button class="button button-dark" @click="startPayment(order)">演示确认付款 <span>↗</span></button></div></div>
          </article>
        </div>
        <p v-if="paymentMessage" class="payment-note">{{ paymentMessage }}<br /><small>这是用于学习的演示流程，不会产生真实支付或收款。</small></p>
      </section>

      <section v-if="currentView === 'admin'" class="page-section admin-page">
        <div class="page-kicker">STUDIO DESK &nbsp; / &nbsp; 01</div>
        <div class="page-title-row"><div><div class="eyebrow"><span class="eyebrow-line"></span> STORE MANAGEMENT</div><h1>{{ isAdmin ? '平台管理' : '店铺管理' }}<span class="title-period">.</span></h1></div><p>把好物，一件件认真呈现。</p></div>
        <div v-if="isMerchant" class="merchant-store-card">
          <div class="inventory-heading"><div><span class="eyebrow">YOUR STORE</span><h2>店铺资料</h2></div></div>
          <form class="store-profile-form" @submit.prevent="saveMerchantStore">
            <label>店铺名称<input v-model="storeForm.name" required maxlength="120" /></label>
            <label>店铺地址<input v-model="storeForm.address" maxlength="300" placeholder="填写城市和详细地址" /></label>
            <label>店铺介绍<textarea v-model="storeForm.description" maxlength="1000" rows="2" placeholder="介绍一下你的店铺…" /></label>
            <button class="button button-outline" type="submit">保存店铺资料</button>
          </form>
        </div>
        <div class="admin-stats" :class="{ 'merchant-stats': !isAdmin }">
          <div><span>在售商品</span><b>{{ inventoryProducts.filter((product) => product.is_active).length.toString().padStart(2, '0') }}</b></div>
          <div v-if="isAdmin"><span>商品分类</span><b>{{ categories.length.toString().padStart(2, '0') }}</b></div>
          <div v-if="isAdmin"><span>优惠码</span><b>{{ coupons.length.toString().padStart(2, '0') }}</b></div>
          <div v-else><span>账号身份</span><b>商家</b></div>
        </div>
        <div class="admin-grid" :class="{ 'merchant-grid': !isAdmin }">
          <form class="admin-card product-form" @submit.prevent="createProduct">
            <div class="admin-card-head"><div><span class="eyebrow">01 / CATALOG</span><h2>{{ editingProductId ? '编辑商品' : '上架新商品' }}</h2></div><span class="admin-card-icon">＋</span></div>
            <label>商品名称<input v-model="productForm.name" required maxlength="200" placeholder="比如：手作陶土花瓶" /></label>
            <div class="form-pair"><label>商品编号<input v-model="productForm.sku" required maxlength="64" placeholder="SH-001" /></label><label>分类<select v-model="productForm.category_id"><option value="">未分类</option><option v-for="category in categories" :key="category.id" :value="String(category.id)">{{ category.name }}</option></select></label></div>
            <div class="form-pair"><label>售价（元）<input v-model="productForm.price" type="number" min="0.01" step="0.01" required placeholder="128.00" /></label><label>库存<input v-model="productForm.stock" type="number" min="0" step="1" required placeholder="20" /></label></div>
            <label>一句介绍<textarea v-model="productForm.description" maxlength="2000" rows="3" placeholder="写下这件好物的特别之处…" /></label>
            <label>商品图片（JPG、PNG、WebP，最大 5 MB）<input id="product-image" type="file" accept="image/jpeg,image/png,image/webp" @change="selectProductImage" /></label>
            <button class="button button-dark form-submit" :disabled="busy">{{ editingProductId ? '保存商品修改' : '发布商品' }} <span>↗</span></button>
            <button v-if="editingProductId" class="button button-outline form-submit" type="button" @click="cancelProductEdit">取消编辑</button>
          </form>

          <div v-if="isAdmin" class="admin-side">
            <form class="admin-card compact-form" @submit.prevent="createCategory">
              <div class="admin-card-head"><div><span class="eyebrow">02 / ORGANIZE</span><h2>商品分类</h2></div><span class="admin-card-icon">⌘</span></div>
              <div class="inline-form"><input v-model="categoryName" required maxlength="100" placeholder="新增一个分类…" /><button class="button button-dark" aria-label="创建分类">+</button></div>
              <div class="tag-list"><span v-for="category in categories" :key="category.id">{{ category.name }} <small>↗</small></span><i v-if="!categories.length">还没有分类</i></div>
            </form>

            <form class="admin-card compact-form coupon-form" @submit.prevent="createCoupon">
              <div class="admin-card-head"><div><span class="eyebrow">03 / A LITTLE THANK YOU</span><h2>创建优惠码</h2></div><span class="admin-card-icon">%</span></div>
              <label>优惠码<input v-model="couponForm.code" required minlength="3" maxlength="40" placeholder="WELCOME10" /></label>
              <div class="form-pair"><label>优惠方式<select v-model="couponForm.discount_type"><option value="percent">折扣百分比</option><option value="fixed">固定金额</option></select></label><label>优惠数值<input v-model="couponForm.value" type="number" min="0.01" step="0.01" required placeholder="10" /></label></div>
              <div class="form-pair"><label>最低消费<input v-model="couponForm.min_subtotal" type="number" min="0" step="0.01" /></label><label>可用次数<input v-model="couponForm.max_uses" type="number" min="1" step="1" placeholder="不限次数" /></label></div>
              <button class="button button-outline form-submit" :disabled="busy">保存优惠码 <span>↗</span></button>
            </form>
          </div>
        </div>

        <div class="inventory-section">
          <div class="inventory-heading"><div><span class="eyebrow">04 / CURRENT SELECTION</span><h2>商品库存</h2></div><span>{{ filteredInventoryProducts.length }} / {{ inventoryProducts.length }} ITEMS</span></div>
          <div class="inventory-filters">
            <input v-model="inventorySearch" type="search" aria-label="搜索商品名称或 SKU" placeholder="搜索商品名称或 SKU" />
            <select v-model="inventoryFilter" aria-label="筛选商品库存和上架状态">
              <option value="all">全部商品</option>
              <option value="active">仅在售</option>
              <option value="inactive">仅已下架</option>
              <option value="low">库存偏低（1–3 件）</option>
              <option value="out">已售罄</option>
            </select>
          </div>
          <div v-if="!inventoryProducts.length" class="inventory-empty">还没有商品。上架第一件好物吧。</div>
          <div v-else-if="!filteredInventoryProducts.length" class="inventory-empty">没有符合条件的商品，请调整搜索或筛选条件。</div>
          <div v-else class="inventory-table">
            <div class="inventory-row inventory-labels"><span>商品</span><span>分类</span><span>价格</span><span>库存</span><span>状态</span><span>管理</span></div>
            <div v-for="product in filteredInventoryProducts" :key="product.id" class="inventory-row">
              <span class="inventory-product"><img v-if="product.image_url" :src="product.image_url" :alt="product.name" /><i v-else>{{ product.name[0] }}</i><b>{{ product.name }}<small>{{ product.sku }}</small></b></span>
              <span>{{ categoryNameOf(product.category_id) }}</span><span>{{ money(product.price) }}</span><span>{{ product.stock }} 件</span>
              <span><i class="live-dot" :class="{ offline: !product.is_active }"></i>{{ product.is_active ? '在售' : '已下架' }}</span>
              <span class="inventory-actions"><button class="text-button" @click="editProduct(product)">编辑</button><button class="text-button" @click="toggleProduct(product)">{{ product.is_active ? '下架' : '重新上架' }}</button></span>
            </div>
          </div>
          <div v-if="isAdmin" class="coupon-list">
            <div class="inventory-heading"><div><span class="eyebrow">05 / COUPON BOOK</span><h2>正在使用的优惠码</h2></div></div>
            <div v-if="!coupons.length" class="inventory-empty">还没有优惠码。</div>
            <div v-else class="coupon-list-grid"><div v-for="coupon in coupons" :key="coupon.id" class="coupon-chip"><span>{{ coupon.code }}</span><b>{{ coupon.discount_type === 'percent' ? `${coupon.value}% OFF` : `${money(coupon.value)} OFF` }}</b><small>已使用 {{ coupon.uses_count }}{{ coupon.max_uses ? ` / ${coupon.max_uses}` : '' }}</small></div></div>
          </div>
          <div v-if="isMerchant" class="admin-orders">
            <div class="inventory-heading"><div><span class="eyebrow">05 / FULFILLMENT</span><h2>店铺订单</h2></div></div>
            <div v-if="!merchantOrders.length" class="inventory-empty">还没有需要处理的店铺订单。</div>
            <div v-else class="admin-order-list">
              <article v-for="order in merchantOrders" :key="order.fulfillment_id" class="admin-order-card">
                <div class="admin-order-top">
                  <div class="admin-order-customer"><span class="admin-customer-mark">#</span><span><b>订单 #{{ order.order_id }}</b><small>{{ order.customer_email }} · {{ new Date(order.created_at).toLocaleString('zh-CN') }}</small></span></div>
                  <span class="order-status" :class="`status-${order.status}`">{{ orderStatusLabel(order.status) }}</span>
                </div>
                <div class="admin-order-summary"><span>{{ order.items.map((item) => `${item.product_name} × ${item.quantity}`).join('、') }}</span><b>{{ money(order.subtotal) }}</b></div>
                <div class="admin-shipping" v-if="order.recipient_name">
                  <span><b>收件人</b>{{ order.recipient_name }} · {{ order.recipient_phone }}</span>
                  <span><b>配送地址</b>{{ order.shipping_region }} {{ order.shipping_address }}</span>
                </div>
                <form v-if="order.status === 'processing'" class="shipment-form" @submit.prevent="submitMerchantShipment(order)">
                  <label>承运商<input v-model="merchantShipmentForm(order.fulfillment_id).shipping_carrier" required maxlength="80" placeholder="例如：顺丰速运" /></label>
                  <label>物流单号<input v-model="merchantShipmentForm(order.fulfillment_id).tracking_number" required maxlength="100" placeholder="填写快递单号" /></label>
                  <button class="button button-dark" type="submit">登记发货 <span>↗</span></button>
                </form>
              </article>
            </div>
            <p v-if="merchantOrders.length >= 100" class="admin-order-limit">仅展示最近 100 笔店铺订单。</p>
            <p class="admin-order-note">只能查看和处理本店商品对应的履约订单；订单须先由顾客进行演示确认付款。</p>
          </div>
          <div v-if="isAdmin" class="admin-orders">
            <div class="inventory-heading"><div><span class="eyebrow">06 / MERCHANT ACCOUNTS</span><h2>商家账号管理</h2></div></div>
            <div v-if="!adminMerchants.length" class="inventory-empty">还没有注册商家。</div>
            <div v-else class="admin-order-list">
              <article v-for="merchant in adminMerchants" :key="merchant.id" class="admin-order-card">
                <div class="admin-order-top">
                  <div class="admin-order-customer"><span class="admin-customer-mark">{{ merchant.email[0]?.toUpperCase() }}</span><span><b>{{ merchant.store_name || '未命名店铺' }}</b><small>{{ merchant.email }}<template v-if="merchant.store_address"> · {{ merchant.store_address }}</template></small></span></div>
                  <button class="button" :class="merchant.is_suspended ? 'button-outline' : 'button-dark'" @click="toggleMerchantStatus(merchant)">{{ merchant.is_suspended ? '恢复账号' : '暂停账号' }}</button>
                </div>
              </article>
            </div>
          </div>
          <div v-if="isAdmin" class="admin-orders">
            <div class="inventory-heading">
              <div><span class="eyebrow">07 / REVIEW MODERATION</span><h2>评论举报审核</h2></div>
              <label class="admin-filter-control">处理状态
                <select v-model="reviewReportStatus" aria-label="筛选举报处理状态">
                  <option value="open">待审核</option>
                  <option value="resolved">已隐藏</option>
                  <option value="dismissed">已驳回</option>
                  <option value="all">全部状态</option>
                </select>
              </label>
            </div>
            <div class="admin-order-search">
              <span>共 {{ reviewReportTotal }} 条 · 当前第 {{ reviewReportTotal ? Math.floor(reviewReportOffset / reviewReportLimit) + 1 : 0 }} / {{ Math.ceil(reviewReportTotal / reviewReportLimit) }} 页</span>
              <div class="admin-pagination">
                <button class="text-button" :disabled="reviewReportOffset === 0" @click="changeReviewReportPage(-1)">上一页</button>
                <button class="text-button" :disabled="reviewReportOffset + reviewReportLimit >= reviewReportTotal" @click="changeReviewReportPage(1)">下一页</button>
              </div>
            </div>
            <div v-if="!reviewReports.length" class="inventory-empty">暂无评论举报。</div>
            <div v-else class="admin-order-list">
              <article v-for="report in reviewReports" :key="report.id" class="admin-order-card">
                <div class="admin-order-top"><b>{{ report.product_name }} · {{ report.reporter_name }}</b><span class="order-status">{{ report.status === 'open' ? '待审核' : report.status === 'resolved' ? '已隐藏' : '已驳回' }}</span></div>
                <p><b>举报原因：</b>{{ report.reason }}</p>
                <p><b>评论内容：</b>{{ report.review_content }}</p>
                <div v-if="report.status === 'open'" class="order-actions">
                  <button class="button button-dark" @click="processReviewReport(report, 'resolved')">隐藏评论并处理</button>
                  <button class="button button-outline" @click="processReviewReport(report, 'dismissed')">驳回举报</button>
                </div>
              </article>
            </div>
          </div>
          <div v-if="isAdmin" class="admin-orders">
            <div class="inventory-heading">
              <div><span class="eyebrow">08 / CUSTOMER ORDERS</span><h2>顾客订单</h2></div>
              <div class="order-filters" aria-label="筛选订单">
                <button :class="{ active: orderFilter === 'all' }" @click="orderFilter = 'all'">全部</button>
                <button :class="{ active: orderFilter === 'pending_payment' }" @click="orderFilter = 'pending_payment'">待付款</button>
                <button :class="{ active: orderFilter === 'paid' }" @click="orderFilter = 'paid'">已付款</button>
                <button :class="{ active: orderFilter === 'processing' }" @click="orderFilter = 'processing'">待发货</button>
                <button :class="{ active: orderFilter === 'shipped' }" @click="orderFilter = 'shipped'">运输中</button>
                <button :class="{ active: orderFilter === 'delivered' }" @click="orderFilter = 'delivered'">已送达</button>
                <button :class="{ active: orderFilter === 'cancelled' }" @click="orderFilter = 'cancelled'">已取消</button>
                <button :class="{ active: orderFilter === 'expired' }" @click="orderFilter = 'expired'">已超时</button>
              </div>
            </div>
            <div class="admin-order-search">
              <input v-model="adminOrderSearch" type="search" maxlength="120" placeholder="搜索订单编号或顾客邮箱" aria-label="搜索订单编号或顾客邮箱" />
              <span>共 {{ adminOrderTotal }} 笔</span>
            </div>
            <div v-if="!filteredAdminOrders.length" class="inventory-empty">这个分类下暂时没有订单。</div>
            <div v-else class="admin-order-list">
              <article v-for="order in filteredAdminOrders" :key="order.id" class="admin-order-card">
                <div class="admin-order-top">
                  <div class="admin-order-customer"><span class="admin-customer-mark">{{ order.customer_email[0]?.toUpperCase() }}</span><span><b>{{ order.customer_email }}</b><small>订单 #{{ order.id.toString().padStart(5, '0') }} · {{ new Date(order.created_at).toLocaleString('zh-CN') }}</small></span></div>
                  <span class="order-status" :class="`status-${order.status}`">{{ orderStatusLabel(order.status) }}</span>
                </div>
                <div class="admin-order-summary">
                  <span>{{ order.items.map((item) => `${item.product_name} × ${item.quantity}`).join('、') }}</span>
                  <b>{{ money(order.total) }}</b>
                </div>
                <div v-if="order.recipient_name" class="admin-shipping">
                  <span><b>收件人</b>{{ order.recipient_name }} · {{ order.recipient_phone }}</span>
                  <span><b>配送地址</b>{{ order.shipping_region }} {{ order.shipping_address }}<template v-if="order.postal_code"> · {{ order.postal_code }}</template></span>
                </div>
                <form v-if="order.status === 'paid' || order.status === 'processing'" class="shipment-form" @submit.prevent="submitShipment(order)">
                  <label>承运商<input v-model="shipmentForm(order.id).shipping_carrier" required maxlength="80" placeholder="例如：顺丰速运" /></label>
                  <label>物流单号<input v-model="shipmentForm(order.id).tracking_number" required maxlength="100" placeholder="填写快递单号" /></label>
                  <button class="button button-dark" type="submit">登记发货 <span>↗</span></button>
                </form>
                <div v-if="order.shipping_carrier && order.tracking_number" class="admin-shipment-record">
                  <span><b>{{ order.shipping_carrier }}</b> · {{ order.tracking_number }}<small v-if="order.shipped_at">发货于 {{ new Date(order.shipped_at).toLocaleString('zh-CN') }}</small><small v-if="order.delivered_at">签收于 {{ new Date(order.delivered_at).toLocaleString('zh-CN') }}</small></span>
                  <button v-if="order.status === 'shipped'" class="text-button" @click="confirmDelivery(order)">标记已送达</button>
                  <span v-else-if="order.status === 'delivered'" class="delivered-label">已签收</span>
                </div>
                <div v-if="order.coupon_code" class="admin-order-coupon">优惠码 {{ order.coupon_code }} · 优惠 {{ money(order.discount) }}</div>
              </article>
            </div>
            <div v-if="adminOrderTotal > adminOrderLimit" class="pagination-actions admin-order-pagination">
              <button class="button button-outline" :disabled="adminOrderOffset === 0" @click="changeAdminOrderPage(-1)">上一页</button>
              <span>第 {{ Math.floor(adminOrderOffset / adminOrderLimit) + 1 }} / {{ Math.ceil(adminOrderTotal / adminOrderLimit) }} 页</span>
              <button class="button button-outline" :disabled="adminOrderOffset + adminOrderLimit >= adminOrderTotal" @click="changeAdminOrderPage(1)">下一页</button>
            </div>
            <p class="admin-order-note">管理员可以协助处理整笔订单；商家仅能管理自己店铺的商品履约。演示支付不会收款，物流状态由人工维护。</p>
          </div>
        </div>
      </section>
    </main>

    <footer class="site-footer">
      <a class="wordmark footer-brand" href="#" @click.prevent="changeView('shop')"><span class="brand-mark">拾</span><span>拾集 <small>SHIJI STUDIO</small></span></a>
      <p>把日子，过成喜欢的样子。</p>
      <span>© SHIJI STUDIO · 2026</span>
    </footer>

    <Transition name="fade">
      <div v-if="selectedProduct" class="overlay product-detail-overlay" @click.self="closeProductDetails">
        <section class="product-detail-panel" role="dialog" aria-modal="true" aria-label="商品详情">
          <header class="detail-header">
            <span class="eyebrow"><span class="eyebrow-line"></span> PRODUCT DETAILS</span>
            <button class="close-button" aria-label="关闭商品详情" @click="closeProductDetails">×</button>
          </header>
          <div class="detail-scroll">
            <div class="product-detail-layout">
              <div class="detail-image">
                <img v-if="selectedProduct.image_url" :src="selectedProduct.image_url" :alt="selectedProduct.name" />
                <div v-else class="detail-image-placeholder"><span>拾</span></div>
              </div>
              <div class="detail-summary">
                <span class="detail-category">{{ categoryNameOf(selectedProduct.category_id) }} · NO. {{ selectedProduct.sku }}</span>
                <h1>{{ selectedProduct.name }}</h1>
                <p class="detail-price">{{ money(selectedProduct.price) }}</p>
                <div class="detail-rating"><span>{{ averageRatingStars }}</span>{{ averageRating }} · {{ reviewSummary.total }} 条评价</div>
                <p class="detail-description">{{ selectedProduct.description || '为日常而选，简约而不简单。' }}</p>
                <div v-if="selectedProduct.store_name" class="detail-store">
                  <b>{{ selectedProduct.store_name }}</b>
                  <span v-if="selectedProduct.store_address">{{ selectedProduct.store_address }}</span>
                </div>
                <p class="detail-stock">{{ selectedProduct.stock > 0 ? `库存 ${selectedProduct.stock} 件` : '暂时售罄' }}</p>
                <div class="detail-actions">
                  <button class="button button-dark" :disabled="selectedProduct.stock < 1" @click="addToCart(selectedProduct)">加入购物袋 <span>↗</span></button>
                  <button class="button button-outline" @click="toggleFavorite(selectedProduct)">{{ favoriteProductIds.has(selectedProduct.id) ? '♥ 已收藏' : '♡ 收藏商品' }}</button>
                </div>
              </div>
            </div>
            <section class="review-section">
              <div class="review-heading"><div><span class="eyebrow">CUSTOMER NOTES</span><h2>评论与评价</h2></div><span>{{ reviewSummary.total }} 条评论</span></div>
              <form class="review-form" @submit.prevent="submitProductReview">
                <label>你的评分</label>
                <div class="rating-picker" role="radiogroup" aria-label="选择评分">
                  <button v-for="rating in 5" :key="rating" type="button" :class="{ active: rating <= reviewDraft.rating }" :aria-label="`${rating} 星`" @click="reviewDraft.rating = rating">★</button>
                  <span>{{ reviewDraft.rating }} / 5</span>
                </div>
                <p class="review-guidance">仅购买并完成演示付款后可评价；每个账号对同一商品只保留一条评价，重复发布会更新原评价。</p>
                <label class="review-content-label">写下你的使用感受
                  <textarea v-model="reviewDraft.content" required maxlength="1000" rows="3" placeholder="分享真实体验，帮助其他人挑选…" />
                </label>
                <button class="button button-dark" type="submit" :disabled="reviewSubmitting || !reviewDraft.content.trim()">{{ reviewSubmitting ? '正在发布…' : '发布评论' }}</button>
              </form>
              <div v-if="reviewsLoading" class="review-empty">正在加载评论…</div>
              <div v-else-if="!productReviews.length" class="review-empty">还没有评论，来留下第一条评价吧。</div>
              <div v-else class="review-list">
                <article v-for="review in productReviews" :key="review.id" class="review-card">
                  <div class="review-author"><b>{{ review.author_name }}</b><span>{{ '★'.repeat(review.rating) }}{{ '☆'.repeat(5 - review.rating) }}</span></div>
                  <p>{{ review.content }}</p>
                  <time :datetime="review.created_at">{{ new Date(review.updated_at).toLocaleString('zh-CN') }}</time>
                  <div class="review-actions">
                    <button v-if="review.can_edit" class="text-button" @click="editReview(review)">编辑</button>
                    <button v-if="review.can_edit" class="text-button danger-button" @click="deleteProductReview(review)">删除</button>
                    <button v-else-if="user" class="text-button" @click="reportProductReview(review)">举报</button>
                  </div>
                </article>
              </div>
              <div v-if="hasMoreReviews" class="pagination-actions">
                <button class="button button-outline" :disabled="reviewsLoading" @click="loadMoreReviews">加载更多评论</button>
              </div>
            </section>
          </div>
        </section>
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="cartOpen" class="overlay" @click.self="cartOpen = false">
        <aside class="cart-drawer" aria-label="购物袋">
          <div class="drawer-header"><div><span class="eyebrow">YOUR LITTLE FINDS</span><h2>购物袋 <small>({{ cartCount }})</small></h2></div><button class="close-button" aria-label="关闭购物袋" @click="cartOpen = false">×</button></div>
          <div v-if="!cart.items.length" class="cart-empty"><span>✳</span><h3>购物袋还是空的</h3><p>去看看，有没有喜欢的东西。</p><button class="button button-dark" @click="cartOpen = false">去逛逛 <span>↗</span></button></div>
          <div v-else class="cart-content">
            <div class="cart-lines">
              <article v-for="item in cart.items" :key="item.product_id" class="cart-line">
                <div class="cart-thumb"><span>拾</span></div>
                <div class="cart-line-info"><h3>{{ item.product_name }}</h3><span>{{ money(item.unit_price) }}</span><div class="quantity-control"><button :aria-label="`减少${item.product_name}数量`" @click="updateCartItem(item.product_id, item.quantity - 1)">−</button><span>{{ item.quantity }}</span><button :aria-label="`增加${item.product_name}数量`" @click="updateCartItem(item.product_id, item.quantity + 1)">+</button></div></div>
                <button class="remove-line" aria-label="移除商品" @click="updateCartItem(item.product_id, 0)">×</button>
              </article>
            </div>
            <form class="checkout-box" @submit.prevent="checkout">
              <div class="shipping-form-heading"><span class="eyebrow"><span class="eyebrow-line"></span> DELIVERY DETAILS</span><b>收货信息</b></div>
              <div class="shipping-form-grid">
                <label>收件人<input v-model="shippingForm.recipient_name" required maxlength="80" autocomplete="name" placeholder="怎么称呼你" /></label>
                <label>联系电话<input v-model="shippingForm.recipient_phone" required type="tel" minlength="7" maxlength="30" autocomplete="tel" placeholder="用于配送联系" /></label>
                <label class="shipping-wide">省 / 市 / 区<input v-model="shippingForm.shipping_region" required maxlength="120" autocomplete="address-level1" placeholder="例如：浙江省 杭州市 西湖区" /></label>
                <label class="shipping-wide">详细地址<textarea v-model="shippingForm.shipping_address" required minlength="5" maxlength="300" autocomplete="street-address" rows="2" placeholder="街道、门牌号、小区或楼层…" /></label>
                <label class="shipping-wide">邮政编码 <small>选填</small><input v-model="shippingForm.postal_code" maxlength="20" autocomplete="postal-code" placeholder="可选" /></label>
              </div>
              <label class="coupon-input"><span>优惠码</span><input v-model="couponCode" maxlength="40" placeholder="输入优惠码（可选）" /></label>
              <div class="checkout-total"><span>商品小计</span><b>{{ money(cart.subtotal) }}</b></div>
              <p>优惠金额将在下单时核算</p>
              <button class="button button-dark checkout-button" type="submit" :disabled="busy">确认下单 <span>↗</span></button>
              <div class="secure-note">✳ &nbsp; 下单后可在「我的订单」查看收货信息</div>
            </form>
          </div>
        </aside>
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="authOpen" class="overlay auth-overlay" @click.self="authOpen = false">
        <section class="auth-card" aria-label="账户登录注册">
          <button class="close-button auth-close" aria-label="关闭登录窗口" @click="authOpen = false">×</button>
          <div class="auth-mark">拾</div><div class="eyebrow"><span class="eyebrow-line"></span> A PLACE FOR YOUR FINDS</div>
          <h2>{{ authMode === 'login' ? (authRole === 'merchant' ? '商家登录。' : '欢迎回来。') : '创建账户。' }}</h2>
          <p>{{ authMode === 'login' ? '使用邮箱和密码登录拾集。' : '选择账户身份，开始使用拾集。' }}</p>
          <div class="auth-role-tabs">
            <button type="button" :class="{ active: authRole === 'customer' }" @click="authRole = 'customer'">顾客</button>
            <button type="button" :class="{ active: authRole === 'merchant' }" @click="authRole = 'merchant'">商家</button>
          </div>
          <form @submit.prevent="submitAuth">
            <label>邮箱地址<input v-model="authForm.email" type="email" autocomplete="email" required maxlength="255" placeholder="hello@example.com" /></label>
            <label>密码<input v-model="authForm.password" type="password" :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'" minlength="8" maxlength="128" required placeholder="至少 8 位" /></label>
            <label v-if="authMode === 'register' && authRole === 'merchant'">店铺名称<input v-model="authForm.store_name" required maxlength="120" placeholder="输入你的店铺名称" /></label>
            <button class="button button-dark auth-submit" :disabled="busy">{{ authMode === 'login' ? '登录' : '注册并登录' }} <span>↗</span></button>
          </form>
          <p class="auth-switch">{{ authMode === 'login' ? '还没有账户？' : '已有账户？' }} <button type="button" @click="authMode = authMode === 'login' ? 'register' : 'login'">{{ authMode === 'login' ? '注册' : '返回登录' }}</button></p>
          <p class="auth-admin-note">管理员账号由店铺管理员创建，请使用顾客入口登录</p>
        </section>
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="accountOpen && user" class="overlay auth-overlay" @click.self="accountOpen = false">
        <section class="auth-card account-card" aria-label="账户管理">
          <button class="close-button auth-close" aria-label="关闭账户管理" @click="accountOpen = false">×</button>
          <div class="auth-mark">拾</div><div class="eyebrow"><span class="eyebrow-line"></span> ACCOUNT SETTINGS</div>
          <h2>账户管理。</h2><p>{{ user.email }} · {{ user.role === 'merchant' ? '商家' : user.role === 'admin' ? '管理员' : '顾客' }}</p>
          <button class="button button-outline auth-submit" type="button" @click="exportAccountData">导出我的个人数据 JSON</button>
          <p class="account-data-note">文件可能包含账户资料、订单地址{{ isMerchant ? '及本店履约订单的顾客信息' : '' }}，请妥善保管。</p>
          <label>头像<input type="file" accept="image/jpeg,image/png,image/webp" @change="uploadAvatar" /></label>
          <div v-if="user.avatar_url" class="account-avatar-preview"><img :src="user.avatar_url" alt="当前头像" /></div>
          <form @submit.prevent="saveProfile">
            <label>显示名称<input v-model="profileForm.display_name" maxlength="100" placeholder="设置你的昵称" /></label>
            <button class="button button-outline auth-submit" type="submit">保存资料</button>
          </form>
          <form class="account-password-form" @submit.prevent="changePassword">
            <label>当前密码<input v-model="passwordForm.current_password" type="password" autocomplete="current-password" required /></label>
            <label>新密码<input v-model="passwordForm.new_password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required /></label>
            <button class="button button-dark auth-submit" type="submit">修改密码</button>
          </form>
          <form v-if="user.role !== 'admin'" class="account-delete-form" @submit.prevent="deleteAccount">
            <label>输入密码以注销账户<input v-model="deletePassword" type="password" autocomplete="current-password" required /></label>
            <button class="text-button danger-button" type="submit">注销账户</button>
          </form>
          <button class="button button-outline auth-submit" type="button" @click="accountOpen = false; signOut()">退出登录</button>
        </section>
      </div>
    </Transition>

    <Transition name="toast"><div v-if="toast" class="toast-message">✳ &nbsp; {{ toast }}</div></Transition>
    <Transition name="toast"><button v-if="error" class="error-message" @click="error = ''">! &nbsp; {{ error }} <span>×</span></button></Transition>
  </div>
</template>
