<script setup>
defineProps({
  title: { type: String, required: true },
  badge: { type: String, default: '' }
})
</script>

<template>
  <div class="page-header">
    <h1>{{ title }}</h1>
    <span v-if="badge" class="badge badge-primary">{{ badge }}</span>
    <div class="page-header-actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  font-size: var(--text-2xl);
  font-weight: 600;
}

.page-header-actions {
  margin-left: auto;
  display: flex;
  gap: 0.75rem;
}
</style>
