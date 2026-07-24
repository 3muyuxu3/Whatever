import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import SiteHeader from '../components/SiteHeader'
import SiteFooter from '../components/SiteFooter'
import AnimatedHeading from '../components/AnimatedHeading'
import { useThreeScene } from '../hooks/useThreeScene'

gsap.registerPlugin(useGSAP, ScrollTrigger)

// 五大能力（复用首页已完整翻译的 capabilities.* 文案 + pages.capabilities.detail.* 扩展文案）
const CAP_KEYS = ['graph', 'env', 'simulation', 'report', 'interaction']

/**
 * NetworkScene —— 3D 知识图谱网络
 * 节点在球体空间内漂浮，邻近节点以细线相连，整体缓慢自转并随鼠标视差，
 * 呼应「从文档中生长出的知识图谱」这一核心能力。
 */
function NetworkScene() {
    const hostRef = useRef(null)

    useThreeScene(
        hostRef,
        ({ THREE, scene, camera }) => {
            camera.position.z = 6
            const group = new THREE.Group()
            scene.add(group)

            // —— 生成节点 ——
            const N = 82
            const pts = []
            for (let i = 0; i < N; i++) {
                const r = 1.2 + Math.random() * 2.4
                const th = Math.random() * Math.PI * 2
                const ph = Math.acos(2 * Math.random() - 1)
                pts.push(new THREE.Vector3(
                    r * Math.sin(ph) * Math.cos(th),
                    r * Math.sin(ph) * Math.sin(th) * 0.72,
                    r * Math.cos(ph),
                ))
            }
            const nodePos = new Float32Array(N * 3)
            pts.forEach((p, i) => { nodePos[i * 3] = p.x; nodePos[i * 3 + 1] = p.y; nodePos[i * 3 + 2] = p.z })

            // 圆形光点纹理
            const dotCanvas = document.createElement('canvas')
            dotCanvas.width = dotCanvas.height = 64
            const dctx = dotCanvas.getContext('2d')
            const grad = dctx.createRadialGradient(32, 32, 0, 32, 32, 32)
            grad.addColorStop(0, 'rgba(255,255,255,1)')
            grad.addColorStop(0.45, 'rgba(255,255,255,0.6)')
            grad.addColorStop(1, 'rgba(255,255,255,0)')
            dctx.fillStyle = grad
            dctx.fillRect(0, 0, 64, 64)
            const dotTex = new THREE.CanvasTexture(dotCanvas)

            const nodeGeo = new THREE.BufferGeometry()
            nodeGeo.setAttribute('position', new THREE.BufferAttribute(nodePos, 3))
            const nodeMat = new THREE.PointsMaterial({
                map: dotTex, size: 0.17, transparent: true, depthWrite: false,
                opacity: 0.95, sizeAttenuation: true, color: 0xffffff,
            })
            group.add(new THREE.Points(nodeGeo, nodeMat))

            // —— 邻近节点连边 ——
            const segs = []
            const MAX_EDGES = 210
            for (let i = 0; i < N && segs.length < MAX_EDGES * 6; i++) {
                for (let j = i + 1; j < N; j++) {
                    if (pts[i].distanceTo(pts[j]) < 1.15) {
                        segs.push(pts[i].x, pts[i].y, pts[i].z, pts[j].x, pts[j].y, pts[j].z)
                    }
                }
            }
            const lineGeo = new THREE.BufferGeometry()
            lineGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(segs), 3))
            const lineMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.13 })
            group.add(new THREE.LineSegments(lineGeo, lineMat))

            // 鼠标视差
            const target = { x: 0, y: 0 }
            const ease = { x: 0, y: 0 }
            let spin = 0
            const onMove = (e) => {
                target.x = (e.clientX / window.innerWidth) * 2 - 1
                target.y = (e.clientY / window.innerHeight) * 2 - 1
            }
            window.addEventListener('pointermove', onMove, { passive: true })

            return {
                update(t, dt) {
                    spin += dt * 0.12
                    ease.x += (target.x * 0.5 - ease.x) * 0.05
                    ease.y += (target.y * 0.3 - ease.y) * 0.05
                    group.rotation.y = spin + ease.x
                    group.rotation.x = ease.y
                },
                dispose() {
                    window.removeEventListener('pointermove', onMove)
                    nodeGeo.dispose(); nodeMat.dispose(); lineGeo.dispose(); lineMat.dispose(); dotTex.dispose()
                },
            }
        },
        [],
    )

    return <div ref={hostRef} className="absolute inset-0" aria-hidden="true" />
}

/**
 * CapabilitiesView —— 「能力」页面
 * 3D 知识图谱主视觉 + 五大能力逐项详解 + 关键指标。
 */
export default function CapabilitiesView() {
    const { t } = useTranslation()
    const rootRef = useRef(null)
    const metrics = t('pages.capabilities.metrics', { returnObjects: true }) || []

    useGSAP(() => {
        const mm = gsap.matchMedia()
        mm.add('(prefers-reduced-motion: no-preference)', () => {
            gsap.utils.toArray('.c-reveal').forEach((el) => {
                gsap.from(el, {
                    y: 48, autoAlpha: 0, duration: 0.9, ease: 'power3.out',
                    scrollTrigger: { trigger: el, start: 'top 84%', once: true },
                })
            })
        })
        return () => mm.revert()
    }, { scope: rootRef })

    return (
        <div ref={rootRef} className="relative min-h-screen bg-black text-white">
            <SiteHeader />

            {/* ===== 3D 主视觉 ===== */}
            <section className="relative -mt-[72px] flex min-h-screen items-center overflow-hidden">
                <NetworkScene />
                <div className="relative z-10 w-full px-6 pt-[72px] md:px-10 lg:px-14">
                    <div className="mx-auto max-w-4xl text-center">
                        <p className="mb-5 text-xs font-medium uppercase tracking-[0.3em] text-white/50">
                            {t('pages.capabilities.kicker')}
                        </p>
                        <AnimatedHeading
                            text={t('pages.capabilities.title')}
                            className="text-4xl font-normal leading-tight md:text-6xl lg:text-7xl"
                            style={{ letterSpacing: '-0.03em' }}
                        />
                        <p className="mx-auto mt-6 max-w-2xl text-base text-white/70 md:text-lg">
                            {t('pages.capabilities.lead')}
                        </p>
                    </div>
                </div>
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-black to-transparent" />
            </section>

            {/* ===== 关键指标 ===== */}
            <section className="c-reveal border-y border-white/10 px-6 py-12 md:px-10 lg:px-14">
                <div className="mx-auto grid max-w-5xl grid-cols-2 gap-8 md:grid-cols-4">
                    {metrics.map((m, i) => (
                        <div key={i} className="text-center">
                            <div className="text-4xl font-light md:text-5xl" style={{ letterSpacing: '-0.02em' }}>{m.value}</div>
                            <div className="mt-2 text-sm text-white/50">{m.label}</div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ===== 五大能力详解 ===== */}
            <section className="mx-auto max-w-5xl px-6 py-24 md:px-10 lg:px-14">
                <div className="space-y-16 md:space-y-24">
                    {CAP_KEYS.map((key, i) => (
                        <div
                            key={key}
                            className={`c-reveal flex flex-col gap-6 md:flex-row md:items-start md:gap-12 ${i % 2 === 1 ? 'md:flex-row-reverse' : ''
                                }`}
                        >
                            <div className="shrink-0 text-6xl font-light tabular-nums text-white/15 md:text-7xl">
                                {String(i + 1).padStart(2, '0')}
                            </div>
                            <div className="md:pt-3">
                                <h2 className="mb-3 text-2xl font-medium md:text-3xl" style={{ letterSpacing: '-0.02em' }}>
                                    {t(`capabilities.${key}.title`)}
                                </h2>
                                <p className="mb-3 text-base font-medium text-white/80">
                                    {t(`capabilities.${key}.desc`)}
                                </p>
                                <p className="max-w-xl text-base leading-relaxed text-white/60">
                                    {t(`pages.capabilities.detail.${key}`)}
                                </p>
                            </div>
                        </div>
                    ))}
                </div>
                <p className="c-reveal mx-auto mt-20 max-w-3xl text-center text-lg text-white/50">
                    {t('pages.capabilities.outro')}
                </p>
            </section>

            {/* ===== CTA ===== */}
            <section className="c-reveal border-t border-white/10 px-6 py-20 text-center md:px-10 lg:px-14">
                <div className="flex flex-wrap justify-center gap-4">
                    <Link to="/workflow" className="rounded-lg bg-white px-8 py-3 font-medium text-black transition hover:bg-gray-100">
                        {t('nav.workflow')}
                    </Link>
                    <Link to="/#start" className="liquid-glass rounded-lg border border-white/20 px-8 py-3 font-medium text-white transition hover:bg-white hover:text-black">
                        {t('pages.cta')}
                    </Link>
                </div>
            </section>

            <SiteFooter />
        </div>
    )
}
