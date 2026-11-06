<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type AdminOrder,
  type Cart,
  type Category,
  type Coupon,
  type Order,
  type Product,
  type User,
} from './api'

type View = 'shop' | 'orders' | 'admin'
type AuthMode = 'login' | 'register'

const products = ref<Product[]>([])
const inventoryProducts = ref<Product[]>([])
const categories = ref<Category[]>([])
const cart = ref<Cart>({ items: [], subtotal: '0.00' })
const orders = ref<Order[]>([])
const adminOrders = ref<AdminOrder[]>([])
const orderFilter = ref<'all' | 'pending_payment' | 'paid' | 'processing' | 'shipped' | 'delivered' | 'cancelled'>('all')
const shipmentForms = ref<Record<number, { shipping_carrier: string; tracking_number: string }>>({})
const coupons = ref<Coupon[]>([])
const user = ref<User | null>(null)
const token = ref(localStorage.getItem('shop-token') ?? '')
const currentView = ref<View>('shop')
const activeCategory = ref<number | null>(null)
const search = ref('')
const loading = ref(false)
const busy = ref(false)
const cartOpen = ref(false)
const authOpen = ref(false)
const authMode = ref<AuthMode>('login')
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

const authForm = ref({ email: '', password: '' })
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
const filteredProducts = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  return products.value.filter((product) => {
    const matchesCategory = activeCategory.value === null || product.category_id === activeCategory.value
    const matchesSearch =
      !term ||
      product.name.toLocaleLowerCase().includes(term) ||
      product.description.toLocaleLowerCase().includes(term) ||
      product.sku.toLocaleLowerCase().includes(term)
    return matchesCategory && matchesSearch
  })
})
const isAdmin = computed(() => user.value?.role === 'admin')
const filteredAdminOrders = computed(() =>
  orderFilter.value === 'all'
    ? adminOrders.value
    : adminOrders.value.filter((order) => order.status === orderFilter.value),
)

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
  }
  return labels[status] ?? status
}

function money(value: string | number) {
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value))
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

async function loadStore() {
  loading.value = true
  try {
    const [productList, categoryList] = await Promise.all([
      api<Product[]>('/products'),
      api<Category[]>('/categories'),
    ])
    products.value = productList
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

async function loadOrders() {
  orders.value = await api<Order[]>('/orders', { token: token.value })
}

async function loadCoupons() {
  if (isAdmin.value) coupons.value = await api<Coupon[]>('/coupons', { token: token.value })
}

async function loadInventory() {
  if (isAdmin.value) {
    inventoryProducts.value = await api<Product[]>('/admin/products', { token: token.value })
  }
}

async function loadAdminOrders() {
  if (isAdmin.value) {
    adminOrders.value = await api<AdminOrder[]>('/admin/orders?limit=100', { token: token.value })
  }
}

async function submitShipment(order: AdminOrder) {
  const shipment = shipmentForm(order.id)
  try {
    const updated = await api<AdminOrder>(`/admin/orders/${order.id}/shipment`, {
      method: 'POST',
      token: token.value,
      body: shipment,
    })
    adminOrders.value = adminOrders.value.map((item) => (item.id === order.id ? updated : item))
    notify(`订单 #${order.id} 已登记发货`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '物流信息登记失败')
  }
}

async function confirmDelivery(order: AdminOrder) {
  try {
    const updated = await api<AdminOrder>(`/admin/orders/${order.id}/delivery`, {
      method: 'POST',
      token: token.value,
    })
    adminOrders.value = adminOrders.value.map((item) => (item.id === order.id ? updated : item))
    notify(`订单 #${order.id} 已标记送达`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '订单状态更新失败')
  }
}

function scrollToCollection() {
  document.getElementById('collection')?.scrollIntoView({ behavior: 'smooth' })
}

function openAuth(mode: AuthMode = 'login') {
  authMode.value = mode
  authOpen.value = true
}

async function submitAuth() {
  busy.value = true
  try {
    if (authMode.value === 'register') {
      await api<User>('/auth/register', {
        method: 'POST',
        body: { email: authForm.value.email, password: authForm.value.password },
      })
    }
    const result = await api<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: { email: authForm.value.email, password: authForm.value.password },
    })
    token.value = result.access_token
    localStorage.setItem('shop-token', token.value)
    user.value = await api<User>('/auth/me', { token: token.value })
    authOpen.value = false
    authForm.value.password = ''
    await loadCart()
    if (isAdmin.value) await Promise.all([loadCoupons(), loadInventory(), loadAdminOrders()])
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
    await loadCart()
    if (isAdmin.value) await Promise.all([loadCoupons(), loadInventory(), loadAdminOrders()])
  } catch {
    token.value = ''
    user.value = null
    localStorage.removeItem('shop-token')
  }
}

function signOut() {
  token.value = ''
  user.value = null
  cart.value = { items: [], subtotal: '0.00' }
  orders.value = []
  coupons.value = []
  adminOrders.value = []
  localStorage.removeItem('shop-token')
  currentView.value = 'shop'
  notify('已安全退出')
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
    await loadOrders()
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
    await Promise.all([loadOrders(), loadStore()])
    notify(`订单 #${order.id} 已取消，库存已释放`)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '订单暂时无法取消')
  }
}

async function startPayment(order: Order) {
  try {
    const payment = await api<{ provider: string; provider_reference: string }>(
      `/orders/${order.id}/payment`,
      { method: 'POST', token: token.value },
    )
    paymentMessage.value = `演示支付已就绪 · ${payment.provider_reference}`
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '无法创建支付')
  }
}

async function createProduct() {
  busy.value = true
  try {
    await api<Product>('/products', {
      method: 'POST',
      token: token.value,
      body: {
        ...productForm.value,
        price: Number(productForm.value.price),
        stock: Number(productForm.value.stock),
        category_id: productForm.value.category_id ? Number(productForm.value.category_id) : null,
      },
    })
    productForm.value = { sku: '', name: '', description: '', price: '', stock: '', category_id: '' }
    await Promise.all([loadStore(), loadInventory()])
    notify('商品已发布')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '商品创建失败')
  } finally {
    busy.value = false
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
  if (view === 'orders' && user.value) {
    try {
      await loadOrders()
    } catch (reason) {
      showError(reason instanceof Error ? reason.message : '订单加载失败')
    }
  }
  if (view === 'admin' && !isAdmin.value) {
    currentView.value = 'shop'
    showError('该区域仅管理员可访问')
  } else if (view === 'admin') {
    try {
      await Promise.all([loadInventory(), loadCoupons(), loadAdminOrders()])
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

onMounted(async () => {
  await Promise.all([loadStore(), restoreSession()])
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
        <button v-if="user" :class="{ selected: currentView === 'orders' }" @click="changeView('orders')">
          我的订单
        </button>
        <button v-if="isAdmin" :class="{ selected: currentView === 'admin' }" @click="changeView('admin')">
          店铺管理
        </button>
      </nav>
      <div class="header-actions">
        <label class="search-box">
          <span aria-hidden="true">⌕</span>
          <input v-model="search" placeholder="搜索好物" aria-label="搜索商品" @focus="changeView('shop')" />
          <kbd>⌘ K</kbd>
        </label>
        <button class="icon-button account-button" :aria-label="user ? '退出登录' : '登录'" @click="user ? signOut() : openAuth()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5" /><path d="M4.5 20c.7-3.5 3.2-5.3 7.5-5.3s6.8 1.8 7.5 5.3" /></svg>
          <span v-if="user" class="user-initial">{{ user.email[0]?.toUpperCase() }}</span>
        </button>
        <button class="icon-button bag-button" aria-label="打开购物袋" @click="user ? (cartOpen = true) : openAuth()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8h14l1 12H4L5 8Z" /><path d="M9 9V6a3 3 0 0 1 6 0v3" /></svg>
          <span class="bag-count">{{ cartCount }}</span>
        </button>
      </div>
    </header>

    <main>
      <section v-if="currentView === 'shop'" class="storefront">
        <section class="hero">
          <div class="hero-copy">
            <div class="eyebrow"><span class="eyebrow-line"></span> SLOW LIVING, WELL MADE</div>
            <h1>把日常过成<br /><em>喜欢的样子。</em></h1>
            <p>从一杯好茶到一盏暖灯，<br />每一件，都值得被认真挑选。</p>
            <button class="button button-dark hero-cta" @click="scrollToCollection">
              探索精选 <span>↗</span>
            </button>
            <div class="hero-footnote"><span>01 — 06</span><span class="hero-dash"></span> THE EVERYDAY EDIT</div>
          </div>
          <div class="hero-art" aria-label="自然色调的家居器物插画">
            <div class="art-sun"></div>
            <div class="art-window"><span></span><i></i></div>
            <div class="art-shelf"></div>
            <div class="art-vase"><span></span></div>
            <div class="art-book book-one"></div>
            <div class="art-book book-two"></div>
            <div class="art-plant"><i></i><i></i><i></i><b></b></div>
            <div class="art-note">OBJECTS WITH<br />A LITTLE SOUL</div>
            <span class="art-stamp">好物 · 慢选</span>
          </div>
          <div class="hero-index">精选生活 · 第 01 期</div>
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
            <span class="product-count">{{ filteredProducts.length.toString().padStart(2, '0') }} 件好物</span>
          </div>

          <div v-if="loading" class="empty-state"><span class="loading-mark"></span><p>正在为你准备好物…</p></div>
          <div v-else-if="filteredProducts.length" class="product-grid">
            <article v-for="(product, index) in filteredProducts" :key="product.id" class="product-card">
              <div class="product-visual" :class="productTone(index)">
                <span class="product-category">{{ categoryNameOf(product.category_id) }}</span>
                <div class="product-object" aria-hidden="true">
                  <span class="object-shadow"></span>
                  <span class="object-shape" :class="`object-${index % 6}`"></span>
                  <span class="object-detail"></span>
                </div>
                <span class="product-number">NO. {{ (index + 1).toString().padStart(2, '0') }}</span>
                <span v-if="product.stock <= 3" class="stock-badge">{{ product.stock ? '少量现货' : '暂时售罄' }}</span>
                <button
                  class="quick-add"
                  :disabled="product.stock <= 0"
                  :aria-label="`将${product.name}加入购物袋`"
                  @click="addToCart(product)"
                >
                  <span>+</span>
                </button>
              </div>
              <div class="product-info">
                <div><h3>{{ product.name }}</h3><span class="product-sku">NO. {{ product.sku }}</span></div>
                <span class="product-price">{{ money(product.price) }}</span>
                <p>{{ product.description || '为日常而选，简约而不简单。' }}</p>
              </div>
            </article>
          </div>
          <div v-else class="empty-state">
            <span class="empty-flower">✳</span>
            <h3>{{ search || activeCategory ? '没有找到合适的好物' : '新一批好物，正在路上。' }}</h3>
            <p>{{ isAdmin ? '先到店铺管理发布商品，精选好物就会出现在这里。' : '店铺正在认真准备第一批精选，稍后再来看看吧。' }}</p>
            <button v-if="isAdmin" class="button button-outline" @click="changeView('admin')">去发布商品 <span>↗</span></button>
            <button v-else-if="search || activeCategory" class="text-button" @click="search = ''; activeCategory = null">查看全部好物 ↗</button>
          </div>
        </section>

        <section class="editor-note">
          <span class="editor-icon">“</span>
          <div><p>喜欢的东西，不需要很多。</p><span>THE LITTLE THINGS MAKE A LIFE.</span></div>
          <span class="editor-aside">拾集 · 好好生活研究所</span>
        </section>
      </section>

      <section v-if="currentView === 'orders'" class="page-section">
        <div class="page-kicker">YOUR ACCOUNT &nbsp; / &nbsp; 01</div>
        <div class="page-title-row"><div><div class="eyebrow"><span class="eyebrow-line"></span> ORDER HISTORY</div><h1>我的订单<span class="title-period">.</span></h1></div><p>每一次喜欢，都有迹可循。</p></div>
        <div v-if="!orders.length" class="empty-state order-empty"><span class="empty-flower">✳</span><h3>还没有订单记录</h3><p>选一件喜欢的好物，开始你的拾集。</p><button class="button button-dark" @click="changeView('shop')">继续逛逛 <span>↗</span></button></div>
        <div v-else class="order-list">
          <article v-for="order in orders" :key="order.id" class="order-card">
            <div class="order-top"><div><span class="order-label">ORDER</span><strong>#{{ order.id.toString().padStart(5, '0') }}</strong></div><span class="order-status" :class="`status-${order.status}`">{{ orderStatusLabel(order.status) }}</span></div>
            <div class="order-items"><div v-for="item in order.items" :key="item.product_id" class="order-line"><span>{{ item.product_name }} <small>× {{ item.quantity }}</small></span><span>{{ money(Number(item.unit_price) * item.quantity) }}</span></div></div>
            <div v-if="order.recipient_name" class="order-shipping"><b>收货信息</b><span>{{ order.recipient_name }} · {{ order.recipient_phone }}</span><span>{{ order.shipping_region }} {{ order.shipping_address }}<template v-if="order.postal_code"> · {{ order.postal_code }}</template></span></div>
            <div v-if="order.shipping_carrier && order.tracking_number" class="order-tracking"><b>物流信息</b><span>{{ order.shipping_carrier }} · 运单号 {{ order.tracking_number }}</span><small v-if="order.shipped_at">发货时间：{{ new Date(order.shipped_at).toLocaleString('zh-CN') }}</small><small v-if="order.delivered_at">签收时间：{{ new Date(order.delivered_at).toLocaleString('zh-CN') }}</small></div>
            <div class="order-bottom"><div><span v-if="order.coupon_code" class="order-coupon">优惠码 {{ order.coupon_code }} · 已优惠 {{ money(order.discount) }}</span><span>合计 <b>{{ money(order.total) }}</b></span></div><div v-if="order.status === 'pending_payment'" class="order-actions"><button class="text-button" @click="cancelOrder(order)">取消订单</button><button class="button button-dark" @click="startPayment(order)">继续支付 <span>↗</span></button></div></div>
          </article>
        </div>
        <p v-if="paymentMessage" class="payment-note">{{ paymentMessage }}<br /><small>这是演示支付，不会扣款。正式支付服务尚未接入。</small></p>
      </section>

      <section v-if="currentView === 'admin'" class="page-section admin-page">
        <div class="page-kicker">STUDIO DESK &nbsp; / &nbsp; 01</div>
        <div class="page-title-row"><div><div class="eyebrow"><span class="eyebrow-line"></span> STORE MANAGEMENT</div><h1>店铺管理<span class="title-period">.</span></h1></div><p>把好物，一件件认真呈现。</p></div>
        <div class="admin-stats">        <div><span>在售商品</span><b>{{ inventoryProducts.filter((product) => product.is_active).length.toString().padStart(2, '0') }}</b></div><div><span>商品分类</span><b>{{ categories.length.toString().padStart(2, '0') }}</b></div><div><span>优惠码</span><b>{{ coupons.length.toString().padStart(2, '0') }}</b></div></div>
        <div class="admin-grid">
          <form class="admin-card product-form" @submit.prevent="createProduct">
            <div class="admin-card-head"><div><span class="eyebrow">01 / CATALOG</span><h2>上架新商品</h2></div><span class="admin-card-icon">＋</span></div>
            <label>商品名称<input v-model="productForm.name" required maxlength="200" placeholder="比如：手作陶土花瓶" /></label>
            <div class="form-pair"><label>商品编号<input v-model="productForm.sku" required maxlength="64" placeholder="SH-001" /></label><label>分类<select v-model="productForm.category_id"><option value="">未分类</option><option v-for="category in categories" :key="category.id" :value="String(category.id)">{{ category.name }}</option></select></label></div>
            <div class="form-pair"><label>售价（元）<input v-model="productForm.price" type="number" min="0.01" step="0.01" required placeholder="128.00" /></label><label>库存<input v-model="productForm.stock" type="number" min="0" step="1" required placeholder="20" /></label></div>
            <label>一句介绍<textarea v-model="productForm.description" maxlength="2000" rows="3" placeholder="写下这件好物的特别之处…" /></label>
            <button class="button button-dark form-submit" :disabled="busy">发布商品 <span>↗</span></button>
          </form>

          <div class="admin-side">
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
          <div class="inventory-heading"><div><span class="eyebrow">04 / CURRENT SELECTION</span><h2>商品库存</h2></div><span>{{ inventoryProducts.length }} ITEMS</span></div>
          <div v-if="!inventoryProducts.length" class="inventory-empty">还没有商品。上架第一件好物吧。</div>
          <div v-else class="inventory-table">
            <div class="inventory-row inventory-labels"><span>商品</span><span>分类</span><span>价格</span><span>库存</span><span>状态</span><span>管理</span></div>
            <div v-for="product in inventoryProducts" :key="product.id" class="inventory-row">
              <span class="inventory-product"><i>{{ product.name[0] }}</i><b>{{ product.name }}<small>{{ product.sku }}</small></b></span>
              <span>{{ categoryNameOf(product.category_id) }}</span><span>{{ money(product.price) }}</span><span>{{ product.stock }} 件</span>
              <span><i class="live-dot" :class="{ offline: !product.is_active }"></i>{{ product.is_active ? '在售' : '已下架' }}</span>
              <button class="text-button" @click="toggleProduct(product)">{{ product.is_active ? '下架' : '重新上架' }}</button>
            </div>
          </div>
          <div class="coupon-list">
            <div class="inventory-heading"><div><span class="eyebrow">05 / COUPON BOOK</span><h2>正在使用的优惠码</h2></div></div>
            <div v-if="!coupons.length" class="inventory-empty">还没有优惠码。</div>
            <div v-else class="coupon-list-grid"><div v-for="coupon in coupons" :key="coupon.id" class="coupon-chip"><span>{{ coupon.code }}</span><b>{{ coupon.discount_type === 'percent' ? `${coupon.value}% OFF` : `${money(coupon.value)} OFF` }}</b><small>已使用 {{ coupon.uses_count }}{{ coupon.max_uses ? ` / ${coupon.max_uses}` : '' }}</small></div></div>
          </div>
          <div class="admin-orders">
            <div class="inventory-heading">
              <div><span class="eyebrow">06 / CUSTOMER ORDERS</span><h2>顾客订单</h2></div>
              <div class="order-filters" aria-label="筛选订单">
                <button :class="{ active: orderFilter === 'all' }" @click="orderFilter = 'all'">全部</button>
                <button :class="{ active: orderFilter === 'pending_payment' }" @click="orderFilter = 'pending_payment'">待付款</button>
                <button :class="{ active: orderFilter === 'paid' }" @click="orderFilter = 'paid'">已付款</button>
                <button :class="{ active: orderFilter === 'processing' }" @click="orderFilter = 'processing'">待发货</button>
                <button :class="{ active: orderFilter === 'shipped' }" @click="orderFilter = 'shipped'">运输中</button>
                <button :class="{ active: orderFilter === 'delivered' }" @click="orderFilter = 'delivered'">已送达</button>
                <button :class="{ active: orderFilter === 'cancelled' }" @click="orderFilter = 'cancelled'">已取消</button>
              </div>
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
            <p v-if="adminOrders.length >= 100" class="admin-order-limit">仅展示最近 100 笔订单。</p>
            <p class="admin-order-note">目前使用模拟支付，尚无付款确认渠道，因此待付款订单不能登记发货。真实支付接入并确认收款后，可手动填写承运商和单号，再标记已送达；物流轨迹暂不自动同步。</p>
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
        <section class="auth-card" aria-label="账户登录">
          <button class="close-button auth-close" aria-label="关闭登录窗口" @click="authOpen = false">×</button>
          <div class="auth-mark">拾</div><div class="eyebrow"><span class="eyebrow-line"></span> A PLACE FOR YOUR FINDS</div>
          <h2>{{ authMode === 'login' ? '欢迎回来。' : '加入拾集。' }}</h2><p>{{ authMode === 'login' ? '登录后继续收藏喜欢的日常。' : '创建账户，开启你的拾集日常。' }}</p>
          <form @submit.prevent="submitAuth"><label>邮箱地址<input v-model="authForm.email" type="email" autocomplete="email" required placeholder="hello@example.com" /></label><label>密码<input v-model="authForm.password" :type="'password'" :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'" minlength="8" maxlength="128" required placeholder="至少 8 位" /></label><button class="button button-dark auth-submit" :disabled="busy">{{ authMode === 'login' ? '登录' : '创建账户' }} <span>↗</span></button></form>
          <p class="auth-switch">{{ authMode === 'login' ? '还没有账户？' : '已经加入拾集？' }} <button @click="authMode = authMode === 'login' ? 'register' : 'login'">{{ authMode === 'login' ? '注册一个' : '直接登录' }}</button></p>
          <p class="auth-admin-note">管理员账号请先通过后端 seed_admin 命令创建</p>
        </section>
      </div>
    </Transition>

    <Transition name="toast"><div v-if="toast" class="toast-message">✳ &nbsp; {{ toast }}</div></Transition>
    <Transition name="toast"><button v-if="error" class="error-message" @click="error = ''">! &nbsp; {{ error }} <span>×</span></button></Transition>
  </div>
</template>
