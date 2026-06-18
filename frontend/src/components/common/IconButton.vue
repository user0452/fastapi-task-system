<script setup>
defineProps({
  icon: { type: String, required: true },
  title: { type: String, required: true },
  variant: { type: String, default: 'ghost' },
  size: { type: String, default: 'sm' },
  disabled: { type: Boolean, default: false }
})

defineEmits(['click'])
</script>

<template>
  <button
    type="button"
    class="btn btn-icon"
    :class="[`btn-${variant}`, `btn-${size}`]"
    :title="title"
    :aria-label="title"
    :disabled="disabled"
    @click="$emit('click')"
  >
    <slot />
  </button>
</template>
