<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-brand">
        <div class="brand-mark">研</div>
        <div>
          <h1>科研雷达</h1>
          <p>ResearcherRadar · 请登录后继续使用</p>
        </div>
      </div>

      <el-form class="login-form" :model="form" @submit.prevent>
        <el-form-item>
          <el-input
            v-model="form.username"
            size="large"
            placeholder="用户名"
            autocomplete="username"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            size="large"
            placeholder="密码"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
        <el-button class="login-button" type="primary" size="large" :loading="loading" @click="submit">
          登录
        </el-button>
      </el-form>
    </section>

    <footer class="login-footer">
      <span>Copyright © All Rights Reserved.</span>
      <a v-if="icpNumber" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">{{ icpNumber }}</a>
    </footer>
  </main>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '' })
const icpNumber = String(import.meta.env.VITE_ICP_NUMBER || '').trim()

async function submit() {
  if (!form.username || !form.password) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await login(form.username, form.password)
    router.replace(String(route.query.redirect || '/'))
  } catch (err) {
    error.value = err?.response?.data?.message || err?.response?.data?.detail || err?.message || '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 28px 28px 76px;
  position: relative;
  background:
    radial-gradient(circle at 20% 10%, rgba(47, 140, 255, 0.18), transparent 28%),
    radial-gradient(circle at 78% 18%, rgba(37, 214, 200, 0.18), transparent 26%),
    linear-gradient(135deg, #eef8ff 0%, #f8fcff 48%, #edf7ff 100%);
}

.login-footer {
  position: absolute;
  bottom: 22px;
  left: 20px;
  right: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
  text-align: center;
}

.login-footer a {
  color: #3b82f6;
  text-decoration: none;
  transition: color 0.16s ease;
}

.login-footer a:hover {
  color: #0f766e;
}

.login-card {
  width: min(430px, 100%);
  padding: 34px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(255, 255, 255, 0.72);
  box-shadow: 0 28px 80px rgba(47, 140, 255, 0.18);
  backdrop-filter: blur(18px);
}

.login-brand {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 28px;
}

.brand-mark {
  width: 54px;
  height: 54px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: white;
  font-size: 24px;
  font-weight: 900;
  background: linear-gradient(135deg, #2f8cff, #25d6c8);
  box-shadow: 0 14px 32px rgba(47, 140, 255, 0.25);
}

h1 {
  margin: 0;
  color: #0b1f33;
  font-size: 25px;
  font-weight: 900;
}

p {
  margin: 6px 0 0;
  color: #64748b;
  font-weight: 700;
}

.login-form {
  display: grid;
  gap: 4px;
}

.login-button {
  width: 100%;
  margin-top: 10px;
  border: 0;
  font-weight: 900;
  background: linear-gradient(135deg, #2f8cff, #25d6c8);
}
</style>
