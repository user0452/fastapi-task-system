<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' }
})
</script>

<template>
  <div class="section-panel">
    <div class="section-header">
      <h3>{{ title }}</h3>
      <span v-if="subtitle" class="section-subtitle">{{ subtitle }}</span>
      <div class="section-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="section-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.section-panel {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--color-line);
}

.section-header h3 {
  font-size: var(--text-base);
  font-weight: 600;
}

.section-subtitle {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.section-actions {
  margin-left: auto;
  display: flex;
  gap: 0.5rem;
}

.section-body {
  padding: 1rem;
}
</style>
