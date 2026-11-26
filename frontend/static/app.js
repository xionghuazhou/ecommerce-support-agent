// frontend/static/app.js - Vue3 + Pinia 单页聊天应用
/* global Vue, Pinia */
const { createApp, ref, computed, onMounted, nextTick } = Vue;
const { createPinia, defineStore } = Pinia;

// ============ Pinia 状态管理 ============
const useChatStore = defineStore('chat', {
  state: () => ({
    sessionId: '',
    messages: [],
    currentSentiment: null,
    sentimentScore: 0,
    quickReplies: [],
    isConnected: false,
    isTyping: false,
    showRating: false,
    ratingScore: 0,
    ratingComment: '',
  }),

  actions: {
    async initSession() {
      this.isConnected = false;
      this.messages = [];
      this.currentSentiment = null;
      this.quickReplies = [];
      this.isTyping = false;
      try {
        const resp = await fetch('/api/v1/chat/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ channel: 'web' }),
        });
        const data = await resp.json();
        this.sessionId = data.session.session_id;
        this.isConnected = true;
        this.quickReplies = data.quick_replies || [];
        this.messages.push({
          id: 'welcome',
          isUser: false,
          content: data.welcome_message,
          time: formatTime(new Date()),
        });
      } catch (e) {
        console.error('初始化会话失败:', e);
      }
    },

    async sendMessage(content) {
      content = (content || '').trim();
      if (!content || this.isTyping || !this.sessionId) return;

      this.messages.push({
        id: `u${Date.now()}`,
        isUser: true,
        content,
        time: formatTime(new Date()),
      });
      this.isTyping = true;
      this.scrollToBottom();

      try {
        const resp = await fetch('/api/v1/chat/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: this.sessionId, content }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        this.messages.push({
          id: `b${data.message_id || Date.now()}`,
          isUser: false,
          content: data.response,
          time: formatTime(new Date()),
          intentName: data.intent && data.intent.intent_name,
          confidence: data.intent && data.intent.confidence,
          sentiment: data.sentiment,
          toolTrace: data.tool_trace || [],
        });
        this.currentSentiment = data.sentiment;
        this.sentimentScore = data.sentiment_score;
        this.quickReplies = data.quick_replies || [];
      } catch (e) {
        console.error('发送消息失败:', e);
        this.messages.push({
          id: `e${Date.now()}`,
          isUser: false,
          content: '抱歉，网络似乎开小差了，请稍后再试一次～',
          time: formatTime(new Date()),
        });
      } finally {
        this.isTyping = false;
        this.scrollToBottom();
      }
    },

    async submitRating() {
      try {
        await fetch('/api/v1/chat/rate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: this.sessionId,
            score: this.ratingScore,
            comment: this.ratingComment || null,
          }),
        });
        this.messages.push({
          id: `r${Date.now()}`,
          isUser: false,
          content: `收到您的 ${this.ratingScore} 星评价，感谢您的反馈！祝您生活愉快～ 😊`,
          time: formatTime(new Date()),
        });
        this.showRating = false;
        this.ratingScore = 0;
        this.ratingComment = '';
        this.scrollToBottom();
      } catch (e) {
        console.error('评价失败:', e);
      }
    },

    scrollToBottom() {
      nextTick(() => {
        const el = document.querySelector('.chat-messages');
        if (el) el.scrollTop = el.scrollHeight;
      });
    },
  },
});

// ============ 工具函数 ============
function formatTime(d) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ============ 根组件 ============
const app = createApp({
  setup() {
    const store = useChatStore();
    const inputText = ref('');
    const showDashboard = ref(false);
    const dashboard = ref(null);
    const dashboardLoading = ref(false);
    const messagesContainer = ref(null);

    const quickServices = [
      { icon: '📦', text: '查一下我的订单' },
      { icon: '🚚', text: '我的订单什么时候到' },
      { icon: '💰', text: '退换货政策是什么' },
      { icon: '🎁', text: '有什么优惠活动' },
      { icon: '🎧', text: '推荐一款耳机' },
      { icon: '👤', text: '转人工客服' },
    ];

    const sentimentEmoji = computed(() => ({
      positive: '😊', neutral: '😐', negative: '😔',
    }[store.currentSentiment] || '🤖'));

    const sentimentLabel = computed(() => ({
      positive: '您当前的情绪：积极', neutral: '您当前的情绪：中性', negative: '检测到消极情绪，我们将优先安抚处理',
    }[store.currentSentiment] || ''));

    function sentimentEmojiOf(s) { return { positive: '😊', neutral: '😐', negative: '😔' }[s] || ''; }
    function sentimentTextOf(s) { return { positive: '积极', neutral: '中性', negative: '消极' }[s] || ''; }

    function formatContent(content) {
      return escapeHtml(content)
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    }

    function send() {
      if (!inputText.value.trim() || store.isTyping) return;
      store.sendMessage(inputText.value);
      inputText.value = '';
    }

    async function reinitSession() {
      await store.initSession();
    }

    async function openDashboard() {
      showDashboard.value = true;
      dashboardLoading.value = true;
      dashboard.value = null;
      try {
        const resp = await fetch('/api/v1/analytics/overview');
        dashboard.value = await resp.json();
      } catch (e) {
        console.error('看板加载失败:', e);
      } finally {
        dashboardLoading.value = false;
      }
    }

    onMounted(() => store.initSession());

    return {
      store, inputText, showDashboard, dashboard, dashboardLoading, messagesContainer,
      quickServices, sentimentEmoji, sentimentLabel,
      sentimentEmojiOf, sentimentTextOf, formatContent, send, reinitSession, openDashboard,
    };
  },
});

app.use(createPinia());
app.mount('#app');
