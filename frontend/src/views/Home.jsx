import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import FadeIn from '../components/FadeIn'
import AnimatedHeading from '../components/AnimatedHeading'
import LanguageSwitcher from '../components/LanguageSwitcher'
import HistoryDatabase from '../components/HistoryDatabase'
import PeepsCrowd from '../components/PeepsCrowd'
import { useUpload } from '../store/UploadContext'
import { generateOntology } from '../api/graph'

// GitHub 仓库入口地址
const GITHUB_URL = 'https://github.com/3muyuxu3/muyuxu'

// 能力卡片配置：标题/描述使用 i18n key，图标来自 icons8
const CAPABILITIES = [
    { key: 'graph', icon: 'https://img.icons8.com/ios/100/ffffff/mind-map.png' },
    { key: 'env', icon: 'https://img.icons8.com/ios/100/ffffff/settings--v1.png' },
    { key: 'simulation', icon: 'https://img.icons8.com/ios/100/ffffff/conference-call.png' },
    { key: 'report', icon: 'https://img.icons8.com/ios/100/ffffff/document--v1.png' },
    { key: 'interaction', icon: 'https://img.icons8.com/ios/100/ffffff/chat--v1.png' },
]

// 工作流程步骤
const WORKFLOW_STEPS = ['step1', 'step2', 'step3', 'step4']

/**
 * Home —— 首页
 * 结构：全屏视频 Hero + 能力介绍 + 工作流程 + 上传区 + 历史项目 + 页脚。
 * Hero 部分严格参考设计稿：视频背景、液态玻璃导航栏、逐字入场标题、错落淡入。
 */
export default function Home() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const { file, setFile, requirement, setRequirement } = useUpload()
    const fileInputRef = useRef(null)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState('')

    // 平滑滚动到页面内的指定区块
    const scrollTo = (id) => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    }

    // 处理文件选择
    const onSelectFile = (e) => {
        const f = e.target.files?.[0]
        if (f) setFile(f)
    }

    // 提交：上传文件 + 预测需求 -> 生成本体 -> 进入处理流程页
    const handleBuild = async () => {
        if (!file || submitting) return
        setSubmitting(true)
        setError('')
        try {
            const formData = new FormData()
            formData.append('file', file)
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

    return (
        <div className="relative w-full bg-black text-white">
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
                        <nav className="liquid-glass flex items-center justify-between rounded-xl px-4 py-2">
                            {/* 左：Logo */}
                            <button
                                type="button"
                                onClick={() => scrollTo('top')}
                                className="text-xl font-semibold tracking-tight md:text-2xl"
                            >
                                SimulMirror
                            </button>

                            {/* 中：导航链接（移动端隐藏） */}
                            <div className="hidden items-center gap-8 text-sm md:flex">
                                <button
                                    type="button"
                                    onClick={() => scrollTo('capabilities')}
                                    className="transition hover:text-gray-300"
                                >
                                    {t('nav.capabilities')}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => scrollTo('workflow')}
                                    className="transition hover:text-gray-300"
                                >
                                    {t('nav.workflow')}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => scrollTo('start')}
                                    className="transition hover:text-gray-300"
                                >
                                    {t('nav.vision')}
                                </button>
                                <a
                                    href={GITHUB_URL}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="transition hover:text-gray-300"
                                >
                                    {t('nav.docs')}
                                </a>
                            </div>

                            {/* 右：语言切换 + GitHub 入口 + 主按钮 */}
                            <div className="flex items-center gap-3">
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
                                        src="https://img.icons8.com/ios-glyphs/90/ffffff/github.png"
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
                <h2 className="mb-3 text-3xl font-normal md:text-4xl" style={{ letterSpacing: '-0.03em' }}>
                    {t('capabilities.title')}
                </h2>
                <p className="mb-12 max-w-2xl text-gray-400">{t('capabilities.subtitle')}</p>

                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {CAPABILITIES.map((cap) => (
                        <div key={cap.key} className="liquid-glass rounded-xl p-6">
                            <img src={cap.icon} alt="" className="mb-4 h-9 w-9 opacity-90" loading="lazy" />
                            <h3 className="mb-2 text-lg font-medium">
                                {t(`capabilities.${cap.key}.title`)}
                            </h3>
                            <p className="text-sm leading-relaxed text-gray-400">
                                {t(`capabilities.${cap.key}.desc`)}
                            </p>
                        </div>
                    ))}
                </div>
            </section>

            {/* ============ 工作流程 ============ */}
            <section id="workflow" className="mx-auto max-w-7xl px-6 py-24 md:px-12 lg:px-16">
                <h2 className="mb-12 text-3xl font-normal md:text-4xl" style={{ letterSpacing: '-0.03em' }}>
                    {t('workflow.title')}
                </h2>
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                    {WORKFLOW_STEPS.map((step, idx) => (
                        <div key={step} className="liquid-glass rounded-xl p-6">
                            <div className="mb-4 text-3xl font-light text-white/60">
                                {String(idx + 1).padStart(2, '0')}
                            </div>
                            <h3 className="mb-2 text-lg font-medium">{t(`workflow.${step}.title`)}</h3>
                            <p className="text-sm leading-relaxed text-gray-400">
                                {t(`workflow.${step}.desc`)}
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
                    {/* 文件拖放/选择区 */}
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="flex w-full flex-col items-center justify-center rounded-xl border border-dashed border-white/20 px-6 py-12 text-center transition hover:border-white/40"
                    >
                        <img
                            src="https://img.icons8.com/ios/100/ffffff/upload-to-cloud--v1.png"
                            alt=""
                            className="mb-4 h-10 w-10 opacity-80"
                            loading="lazy"
                        />
                        <span className="text-white">
                            {file ? `${t('start.selectedFile')}: ${file.name}` : t('start.dropHint')}
                        </span>
                        <span className="mt-2 text-xs text-gray-500">{t('start.fileTypes')}</span>
                    </button>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.txt,.md"
                        className="hidden"
                        onChange={onSelectFile}
                    />

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
                            disabled={!file || submitting}
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
                                src="https://img.icons8.com/ios-glyphs/90/ffffff/github.png"
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
    )
}
