import { lazy, Suspense, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import FadeIn from '../components/FadeIn'
import AnimatedHeading from '../components/AnimatedHeading'
import Logo from '../components/Logo'
import LanguageSwitcher from '../components/LanguageSwitcher'
import HistoryDatabase from '../components/HistoryDatabase'
import ReportHistory from '../components/ReportHistory'
import PeepsCrowd from '../components/PeepsCrowd'
import CapabilityCarousel from '../components/CapabilityCarousel'
// 巨型品牌字位于首屏之外且依赖 three.js，故按需懒加载，避免阻塞首屏交互
const GiantWordmark = lazy(() => import('../components/GiantWordmark'))
import { useUpload } from '../store/UploadContext'
import { generateOntology } from '../api/graph'
import { GITHUB_URL, ICON_GITHUB } from '../constants'

// 注册 GSAP 插件：useGSAP 负责组件卸载时自动清理，ScrollTrigger 负责滚动进入视口时触发动效
gsap.registerPlugin(useGSAP, ScrollTrigger)

// 能力卡片配置：标题/描述使用 i18n key，图标来自 icons8
const CAPABILITIES = [
    { key: 'graph', icon: 'https://img.icons8.com/ios/100/ffffff/mind-map.png' },
    { key: 'env', icon: 'https://img.icons8.com/ios/100/ffffff/settings--v1.png' },
    { key: 'simulation', icon: 'https://img.icons8.com/ios/100/ffffff/conference-call.png' },
    { key: 'report', icon: 'https://img.icons8.com/ios/100/ffffff/document--v1.png' },
    { key: 'interaction', icon: 'https://img.icons8.com/ios/100/ffffff/chat--v1.png' },
]

// 工作流程步骤（完整 5 步：图谱构建 / 环境搭建 / 模拟运行 / 报告生成 / 深度互动）
const WORKFLOW_STEPS = ['step1', 'step2', 'step3', 'step4', 'step5']

/**
 * Home —— 首页
 * 结构：全屏视频 Hero + 能力介绍 + 工作流程 + 上传区 + 历史项目 + 页脚。
 * Hero 部分严格参考设计稿：视频背景、液态玻璃导航栏、逐字入场标题、错落淡入。
 */
export default function Home() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const { files, setFiles, requirement, setRequirement } = useUpload()
    const fileInputRef = useRef(null)
    const rootRef = useRef(null)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState('')
    const [dragOver, setDragOver] = useState(false)
    const [mobileOpen, setMobileOpen] = useState(false)

    // 平滑滚动到页面内的指定区块
    const scrollTo = (id) => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    }

    // 追加文件（去重：同名同大小视为重复）
    const addFiles = (list) => {
        const incoming = Array.from(list || [])
        if (!incoming.length) return
        setFiles((prev) => {
            const merged = [...prev]
            for (const f of incoming) {
                if (!merged.some((x) => x.name === f.name && x.size === f.size)) merged.push(f)
            }
            return merged
        })
    }

    // 处理文件选择 / 拖放 / 移除
    const onSelectFile = (e) => addFiles(e.target.files)
    const removeFile = (idx) => setFiles((prev) => prev.filter((_, i) => i !== idx))
    const onDrop = (e) => {
        e.preventDefault()
        setDragOver(false)
        addFiles(e.dataTransfer?.files)
    }

    // 提交：上传文件（支持多个） + 预测需求 -> 生成本体 -> 进入处理流程页
    const handleBuild = async () => {
        if (!files.length || submitting) return
        setSubmitting(true)
        setError('')
        try {
            const formData = new FormData()
            files.forEach((f) => formData.append('file', f))
            formData.append('requirement', requirement)
            const res = await generateOntology(formData)
            const projectId = res.data?.project_id || res.data?.id
            if (projectId) {
                navigate(`/process/${projectId}`)
            }
        } catch (err) {
            // 后端不可用或出错时给出提示（不阻塞页面）
            setError(t('common.error'))
        } finally {
            setSubmitting(false)
        }
    }

    // ===== GSAP 滚动入场动效（能力介绍 / 工作流程两个区块）=====
    // 使用 useGSAP：组件卸载或依赖变化时自动 revert，避免动画泄漏到已卸载节点；
    // 通过 matchMedia 尊重系统「减少动画」偏好；卡片错落浮现 + 悬停轻微上浮，营造舒适的层次感。
    useGSAP(() => {
        const mm = gsap.matchMedia()

        mm.add(
            {
                reduce: '(prefers-reduced-motion: reduce)',
                motionOk: '(prefers-reduced-motion: no-preference)',
            },
            (context) => {
                // 尊重「减少动画」偏好：保持元素默认可见，不做位移 / 缩放动效
                if (context.conditions.reduce) return

                // —— 能力介绍：标题与副标题淡入上浮 ——
                gsap.from(['.caps-title', '.caps-subtitle'], {
                    y: 32,
                    autoAlpha: 0,
                    duration: 0.9,
                    ease: 'power3.out',
                    stagger: 0.12,
                    scrollTrigger: { trigger: '#capabilities', start: 'top 78%', once: true },
                })

                // 能力卡片改为「3D 覆盖流轮播」，其入场与切换动效由 CapabilityCarousel 自行管理

                // —— 工作流程：标题 + 五步卡片 + 大序号 ——
                gsap.from('.flow-title', {
                    y: 32,
                    autoAlpha: 0,
                    duration: 0.9,
                    ease: 'power3.out',
                    scrollTrigger: { trigger: '#workflow', start: 'top 80%', once: true },
                })

                gsap.from('.flow-card', {
                    y: 60,
                    autoAlpha: 0,
                    duration: 0.8,
                    ease: 'power3.out',
                    stagger: 0.12,
                    clearProps: 'transform',
                    scrollTrigger: { trigger: '.flow-grid', start: 'top 82%', once: true },
                })

                // 大序号：在卡片浮现后再缓缓升起，形成前后层次
                gsap.from('.flow-num', {
                    yPercent: 45,
                    autoAlpha: 0,
                    duration: 0.9,
                    ease: 'power2.out',
                    stagger: 0.12,
                    delay: 0.15,
                    scrollTrigger: { trigger: '.flow-grid', start: 'top 82%', once: true },
                })

                // —— 工作流程卡片悬停微交互：轻微上浮 + 投影；移出时平滑回落 ——
                const cards = gsap.utils.toArray('.flow-card', rootRef.current)
                const shadowRest = 'inset 0 1px 1px rgba(255,255,255,0.1)'
                const shadowHover =
                    'inset 0 1px 1px rgba(255,255,255,0.1), 0 18px 40px -14px rgba(0,0,0,0.65)'
                const bound = []
                cards.forEach((card) => {
                    const onEnter = () =>
                        gsap.to(card, { y: -8, boxShadow: shadowHover, duration: 0.35, ease: 'power2.out', overwrite: 'auto' })
                    const onLeave = () =>
                        gsap.to(card, { y: 0, boxShadow: shadowRest, duration: 0.45, ease: 'power2.out', overwrite: 'auto' })
                    card.addEventListener('mouseenter', onEnter)
                    card.addEventListener('mouseleave', onLeave)
                    bound.push([card, onEnter, onLeave])
                })

                // 媒体条件失配 / 组件卸载时：移除监听并杀掉悬停补间，避免泄漏
                return () => {
                    bound.forEach(([card, onEnter, onLeave]) => {
                        card.removeEventListener('mouseenter', onEnter)
                        card.removeEventListener('mouseleave', onLeave)
                    })
                    gsap.killTweensOf(cards)
                }
            },
            rootRef.current,
        )

        return () => mm.revert()
    }, { scope: rootRef })

    return (
        <>
            {/* 底层固定巨字：置于视口最底层，被上层不透明内容遮挡，向下滚动到页面底部时逐渐显露 */}
            <div className="fixed inset-x-0 bottom-0 z-0">
                {/* 懒加载时以同尺寸白色占位块占位，避免布局抖动 */}
                <Suspense
                    fallback={<div className="w-full" style={{ height: 'clamp(120px, 20vw, 320px)', backgroundColor: '#ffffff' }} />}
                >
                    <GiantWordmark word="MUYU" color="#ffffff" />
                </Suspense>
            </div>

            {/* 上层内容：不透明黑底 + 更高层级，滚动时遮住下方的底层巨字 */}
            <div ref={rootRef} className="relative z-10 w-full bg-black text-white">
                {/* ============ Hero 区（全屏视频背景） ============ */}
                <section className="relative h-screen w-full overflow-hidden">
                    {/* 背景视频：铺满视口，object-cover，自动播放/循环/静音/内联播放，无任何遮罩层 */}
                    <video
                        className="absolute inset-0 h-full w-full object-cover"
                        src="/home.mp4"
                        autoPlay
                        loop
                        muted
                        playsInline
                        preload="auto"
                    />

                    {/* 底部行走的人群（下滑时淡出消失） */}
                    <PeepsCrowd />

                    {/* 前景内容：导航栏 + Hero 文案，位于视频之上 */}
                    <div className="relative z-10 flex h-full flex-col">
                        {/* ---- 导航栏 ---- */}
                        <div className="px-6 pt-6 md:px-12 lg:px-16">
                            <nav className="liquid-glass flex items-center justify-between overflow-visible rounded-xl px-4 py-2">
                                {/* 左：Logo */}
                                <button
                                    type="button"
                                    onClick={() => scrollTo('top')}
                                    className="flex items-center gap-2 text-xl font-semibold tracking-tight md:text-2xl"
                                >
                                    <Logo className="h-7 w-7 shrink-0" />
                                    SimulMirror
                                </button>

                                {/* 中：导航链接 → 能力 / 流程 / 理念 / 文档 四个独立页面（移动端隐藏） */}
                                <div className="hidden items-center gap-8 text-sm md:flex">
                                    <Link to="/capabilities" className="transition hover:text-gray-300">
                                        {t('nav.capabilities')}
                                    </Link>
                                    <Link to="/workflow" className="transition hover:text-gray-300">
                                        {t('nav.workflow')}
                                    </Link>
                                    <Link to="/vision" className="transition hover:text-gray-300">
                                        {t('nav.vision')}
                                    </Link>
                                    <Link to="/docs" className="transition hover:text-gray-300">
                                        {t('nav.docs')}
                                    </Link>
                                </div>

                                {/* 右：语言切换 + GitHub 入口 + 主按钮 */}
                                <div className="flex items-center gap-3">
                                    {/* 移动端菜单按钮 */}
                                    <button
                                        type="button"
                                        onClick={() => setMobileOpen((v) => !v)}
                                        aria-label="Menu"
                                        className="flex h-9 w-9 items-center justify-center rounded-lg text-white transition hover:bg-white/10 md:hidden"
                                    >
                                        <span className="text-xl leading-none">☰</span>
                                    </button>
                                    <LanguageSwitcher className="hidden sm:block" />
                                    {/* GitHub 入口（图标来自 icons8） */}
                                    <a
                                        href={GITHUB_URL}
                                        target="_blank"
                                        rel="noreferrer"
                                        aria-label="GitHub"
                                        className="flex h-9 w-9 items-center justify-center rounded-lg transition hover:bg-white/10"
                                    >
                                        <img
                                            src={ICON_GITHUB}
                                            alt="GitHub"
                                            className="h-5 w-5"
                                            loading="lazy"
                                        />
                                    </a>
                                    <button
                                        type="button"
                                        onClick={() => scrollTo('start')}
                                        className="rounded-lg bg-white px-6 py-2 text-sm font-medium text-black transition hover:bg-gray-100"
                                    >
                                        {t('nav.start')}
                                    </button>
                                </div>
                            </nav>

                            {/* 移动端下拉菜单 */}
                            {mobileOpen && (
                                <div className="liquid-glass mt-2 flex flex-col gap-1 rounded-xl p-2 text-sm md:hidden">
                                    {[
                                        ['/capabilities', 'nav.capabilities'],
                                        ['/workflow', 'nav.workflow'],
                                        ['/vision', 'nav.vision'],
                                        ['/docs', 'nav.docs'],
                                    ].map(([to, key]) => (
                                        <Link
                                            key={key}
                                            to={to}
                                            onClick={() => setMobileOpen(false)}
                                            className="rounded-lg px-4 py-2 text-left text-white transition hover:bg-white/10"
                                        >
                                            {t(key)}
                                        </Link>
                                    ))}
                                    <div className="px-2 py-1">
                                        <LanguageSwitcher />
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* ---- Hero 文案（贴视口底部） ---- */}
                        <div className="flex flex-1 flex-col justify-end px-6 pb-[40vh] md:px-12 lg:px-16">
                            <div className="lg:grid lg:grid-cols-2 lg:items-end">
                                {/* 左列：主标题 + 副标题 + 按钮 */}
                                <div>
                                    <AnimatedHeading
                                        text={t('hero.heading')}
                                        className="mb-4 text-4xl font-normal md:text-5xl lg:text-6xl xl:text-7xl"
                                        style={{ letterSpacing: '-0.04em', textShadow: '0 2px 24px rgba(0,0,0,0.25)' }}
                                    />

                                    <FadeIn delay={800} duration={1000}>
                                        <p
                                            className="mb-5 max-w-xl text-base text-gray-300 md:text-lg"
                                            style={{ textShadow: '0 1px 12px rgba(0,0,0,0.3)' }}
                                        >
                                            {t('hero.subheading')}
                                        </p>
                                    </FadeIn>

                                    <FadeIn delay={1200} duration={1000}>
                                        <div className="flex flex-wrap gap-4">
                                            <button
                                                type="button"
                                                onClick={() => scrollTo('start')}
                                                className="rounded-lg bg-white px-8 py-3 font-medium text-black transition hover:bg-gray-100"
                                            >
                                                {t('hero.start')}
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => scrollTo('capabilities')}
                                                className="liquid-glass rounded-lg border border-white/20 px-8 py-3 font-medium text-white transition hover:bg-white hover:text-black"
                                            >
                                                {t('hero.explore')}
                                            </button>
                                        </div>
                                    </FadeIn>
                                </div>

                                {/* 右列：标语玻璃卡片（大屏靠右下对齐） */}
                                <div className="mt-8 flex items-end justify-start lg:mt-0 lg:justify-end">
                                    <FadeIn delay={1400} duration={1000}>
                                        <div className="liquid-glass rounded-xl border border-white/20 px-6 py-3">
                                            <span className="text-lg font-light md:text-xl lg:text-2xl">
                                                {t('hero.tag')}
                                            </span>
                                        </div>
                                    </FadeIn>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* 页面顶部锚点 */}
                <span id="top" className="sr-only" />

                {/* ============ 能力介绍 ============ */}
                <section id="capabilities" className="mx-auto max-w-7xl px-6 py-24 md:px-12 lg:px-16">
                    <h2 className="caps-title mb-3 text-3xl font-normal md:text-4xl" style={{ letterSpacing: '-0.03em' }}>
                        {t('capabilities.title')}
                    </h2>
                    <p className="caps-subtitle mb-12 max-w-2xl text-gray-400">{t('capabilities.subtitle')}</p>

                    <CapabilityCarousel items={CAPABILITIES} />
                </section>

                {/* ============ 工作流程 ============ */}
                <section id="workflow" className="mx-auto max-w-7xl px-6 py-24 md:px-12 lg:px-16">
                    <h2 className="flow-title mb-12 text-3xl font-normal md:text-4xl" style={{ letterSpacing: '-0.03em' }}>
                        {t('workflow.title')}
                    </h2>
                    <div className="flow-grid grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-5">
                        {WORKFLOW_STEPS.map((step, idx) => (
                            <div key={step} className="flow-card liquid-glass rounded-xl p-6">
                                <div className="flow-num mb-4 text-3xl font-light text-white/60">
                                    {String(idx + 1).padStart(2, '0')}
                                </div>
                                <h3 className="mb-2 text-lg font-medium">
                                    {t(`workflow.${step}.title`, { defaultValue: t('steps.step5') })}
                                </h3>
                                <p className="text-sm leading-relaxed text-gray-400">
                                    {t(`workflow.${step}.desc`, { defaultValue: t('capabilities.interaction.desc') })}
                                </p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* ============ 上传区 + 历史项目 ============ */}
                <section id="start" className="mx-auto max-w-7xl px-6 py-24 md:px-12 lg:px-16">
                    <h2 className="mb-3 text-3xl font-normal md:text-4xl" style={{ letterSpacing: '-0.03em' }}>
                        {t('start.title')}
                    </h2>
                    <p className="mb-10 max-w-2xl text-gray-400">{t('start.subtitle')}</p>

                    <div className="liquid-glass rounded-2xl p-6 md:p-8">
                        {/* 文件拖放 / 选择区（支持多文件 + 拖放） */}
                        <div
                            onClick={() => fileInputRef.current?.click()}
                            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                            onDragLeave={() => setDragOver(false)}
                            onDrop={onDrop}
                            className={`flex w-full cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-6 py-12 text-center transition ${dragOver ? 'border-white/60 bg-white/5' : 'border-white/20 hover:border-white/40'
                                }`}
                        >
                            <img
                                src="https://img.icons8.com/ios/100/ffffff/upload-to-cloud--v1.png"
                                alt=""
                                className="mb-4 h-10 w-10 opacity-80"
                                loading="lazy"
                            />
                            <span className="text-white">{t('start.dropHint')}</span>
                            <span className="mt-2 text-xs text-gray-500">{t('start.fileTypes')}</span>
                        </div>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf,.txt,.md"
                            multiple
                            className="hidden"
                            onChange={onSelectFile}
                        />

                        {/* 已选择文件列表 */}
                        {files.length > 0 && (
                            <div className="mt-4 space-y-2">
                                <div className="text-xs text-gray-400">
                                    {t('start.selectedFile')} ({files.length})
                                </div>
                                {files.map((f, i) => (
                                    <div
                                        key={`${f.name}-${i}`}
                                        className="flex items-center justify-between rounded-lg border border-white/10 bg-black/30 px-4 py-2 text-sm"
                                    >
                                        <span className="truncate text-gray-200">{f.name}</span>
                                        <button
                                            type="button"
                                            onClick={() => removeFile(i)}
                                            className="ml-3 shrink-0 text-gray-500 transition hover:text-white"
                                            aria-label="remove"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* 预测需求 */}
                        <label className="mb-2 mt-6 block text-sm text-gray-300">
                            {t('start.requirementLabel')}
                        </label>
                        <textarea
                            value={requirement}
                            onChange={(e) => setRequirement(e.target.value)}
                            rows={3}
                            placeholder={t('start.requirementPlaceholder')}
                            className="w-full resize-none rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-white outline-none transition placeholder:text-gray-500 focus:border-white/40"
                        />

                        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

                        {/* 提交按钮 */}
                        <div className="mt-6">
                            <button
                                type="button"
                                onClick={handleBuild}
                                disabled={!files.length || submitting}
                                className="rounded-lg bg-white px-8 py-3 font-medium text-black transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                {submitting ? t('start.building') : t('start.button')}
                            </button>
                        </div>
                    </div>

                    {/* 历史项目 */}
                    <div className="mt-16">
                        <h3 className="mb-2 text-2xl font-normal">{t('history.title')}</h3>
                        <p className="mb-8 text-gray-400">{t('history.subtitle')}</p>
                        <HistoryDatabase />
                    </div>

                    {/* 历史报告 */}
                    <div className="mt-16">
                        <h3 className="mb-2 text-2xl font-normal">{t('reports.title')}</h3>
                        <p className="mb-8 text-gray-400">{t('reports.subtitle')}</p>
                        <ReportHistory />
                    </div>
                </section>

                {/* ============ 页脚 ============ */}
                <footer className="border-t border-white/10 px-6 py-10 md:px-12 lg:px-16">
                    <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 sm:flex-row">
                        <div>
                            <div className="text-lg font-semibold tracking-tight">SimulMirror</div>
                            <div className="text-sm text-gray-500">{t('footer.tagline')}</div>
                        </div>
                        <div className="flex items-center gap-4">
                            <a
                                href={GITHUB_URL}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-2 text-sm text-gray-400 transition hover:text-white"
                            >
                                <img
                                    src={ICON_GITHUB}
                                    alt="GitHub"
                                    className="h-5 w-5"
                                    loading="lazy"
                                />
                                {t('footer.github')}
                            </a>
                        </div>
                    </div>
                    <div className="mx-auto mt-6 max-w-7xl text-center text-xs text-gray-600 sm:text-left">
                        © {new Date().getFullYear()} {t('footer.rights')}
                    </div>
                </footer>
            </div>

            {/* 底部间隙：与巨字等高，向下滚动至此逐渐显露被遮挡的底层巨字 */}
            <div aria-hidden="true" className="w-full" style={{ height: 'clamp(120px, 20vw, 320px)' }} />
        </>
    )
}
