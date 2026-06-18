<script setup>
defineProps({
  text: { type: String, default: '加载中...' }
})
</script>

<template>
  <div class="loading-state">
    <div class="loading-spinner"></div>
    <span>{{ text }}</span>
  </div>
</template>
