<script setup>
import { ref, onMounted } from 'vue'

const props = defineProps({
  type: { type: String, default: 'info' },
  title: { type: String, default: '' },
  message: { type: String, default: '' },
  duration: { type: Number, default: 3000 }
})

const visible = ref(true)

onMounted(() => {
  if (props.duration > 0) {
    setTimeout(() => {
      visible.value = false
    }, props.duration)
  }
})
</script>

<template>
  <div v-if="visible" class="toast" :class="`toast-${type}`">
    <div class="toast-content">
      <div v-if="title" class="toast-title">{{ title }}</div>
      <div class="toast-message">{{ message }}</div>
    </div>
    <button class="toast-close" @click="visible = false">✕</button>
  </div>
</template>
