<script setup>
defineProps({
  icon: { type: [String, Object, Function], default: '暂无' },
  title: { type: String, default: '暂无数据' },
  desc: { type: String, default: '' }
})

defineEmits(['action'])
</script>

<template>
  <div class="empty-state">
    <div class="empty-state-icon" :class="{ 'empty-state-icon-svg': typeof icon !== 'string' }">
      <span v-if="typeof icon === 'string'">{{ icon }}</span>
      <component v-else :is="icon" :size="40" :stroke-width="1.75" />
    </div>
    <div class="empty-state-title">{{ title }}</div>
    <p v-if="desc" class="empty-state-desc">{{ desc }}</p>
    <slot name="action" />
  </div>
</template>
