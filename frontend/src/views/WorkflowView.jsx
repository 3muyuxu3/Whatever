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

// 五个步骤（复用首页已完整翻译的 workflow.* + pages.workflow.detail.* 扩展文案）
const STEP_KEYS = ['step1', 'step2', 'step3', 'step4', 'step5']

/**
 * FlowScene —— 「数据流水线」3D 背景
 * 大量粒子沿一条闭合空间曲线流动，象征从种子到世界的推演流程；
 * 曲线以淡线勾勒，整体缓慢自转并随鼠标视差。
 */
function FlowScene() {
    const hostRef = useRef(null)

    useThreeScene(
        hostRef,
        ({ THREE, scene, camera }) => {
            camera.position.z = 6
            const group = new THREE.Group()
            scene.add(group)

            // 闭合空间曲线（结状回环）
            const ctrl = []
            for (let i = 0; i < 8; i++) {
                const a = (i / 8) * Math.PI * 2
                ctrl.push(new THREE.Vector3(
                    Math.cos(a) * 2.4 + Math.cos(a * 2) * 0.6,
                    Math.sin(a * 3) * 1.0,
                    Math.sin(a) * 2.4,
                ))
            }
            const curve = new THREE.CatmullRomCurve3(ctrl, true, 'catmullrom', 0.6)
            const spaced = curve.getSpacedPoints(1200)
            const L = spaced.length

            // 曲线淡线
            const lineGeo = new THREE.BufferGeometry().setFromPoints(spaced)
            const lineMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.1 })
            group.add(new THREE.Line(lineGeo, lineMat))

            // 圆形光点纹理
            const dot = document.createElement('canvas')
            dot.width = dot.height = 64
            const dctx = dot.getContext('2d')
            const g = dctx.createRadialGradient(32, 32, 0, 32, 32, 32)
            g.addColorStop(0, 'rgba(255,255,255,1)')
            g.addColorStop(0.45, 'rgba(255,255,255,0.55)')
            g.addColorStop(1, 'rgba(255,255,255,0)')
            dctx.fillStyle = g
            dctx.fillRect(0, 0, 64, 64)
            const dotTex = new THREE.CanvasTexture(dot)

            // 流动粒子
            const COUNT = 680
            const positions = new Float32Array(COUNT * 3)
            const offsets = new Int32Array(COUNT)
            for (let i = 0; i < COUNT; i++) {
                offsets[i] = Math.floor(Math.random() * L)
                const p = spaced[offsets[i]]
                positions[i * 3] = p.x; positions[i * 3 + 1] = p.y; positions[i * 3 + 2] = p.z
            }
            const pgeo = new THREE.BufferGeometry()
            const posAttr = new THREE.BufferAttribute(positions, 3)
            pgeo.setAttribute('position', posAttr)
            const pmat = new THREE.PointsMaterial({
                map: dotTex, size: 0.12, transparent: true, depthWrite: false,
                opacity: 0.9, sizeAttenuation: true, color: 0xffffff,
            })
            group.add(new THREE.Points(pgeo, pmat))

            // 鼠标视差
            const target = { x: 0, y: 0 }
            const ease = { x: 0, y: 0 }
            let spin = 0
            let head = 0
            const onMove = (e) => {
                target.x = (e.clientX / window.innerWidth) * 2 - 1
                target.y = (e.clientY / window.innerHeight) * 2 - 1
            }
            window.addEventListener('pointermove', onMove, { passive: true })

            return {
                update(t, dt) {
                    // 粒子沿曲线前进
                    head += dt * 130
                    const H = Math.floor(head)
                    for (let i = 0; i < COUNT; i++) {
                        const idx = (offsets[i] + H) % L
                        const p = spaced[idx]
                        positions[i * 3] = p.x; positions[i * 3 + 1] = p.y; positions[i * 3 + 2] = p.z
                    }
                    posAttr.needsUpdate = true

                    spin += dt * 0.1
                    ease.x += (target.x * 0.45 - ease.x) * 0.05
                    ease.y += (target.y * 0.3 - ease.y) * 0.05
                    group.rotation.y = spin + ease.x
                    group.rotation.x = ease.y
                },
                dispose() {
                    window.removeEventListener('pointermove', onMove)
                    lineGeo.dispose(); lineMat.dispose(); pgeo.dispose(); pmat.dispose(); dotTex.dispose()
                },
            }
        },
        [],
    )

    return <div ref={hostRef} className="absolute inset-0" aria-hidden="true" />
}

/**
 * WorkflowView —— 「流程」页面
 * 数据流粒子主视觉 + 五步纵向时间线（逐步滚动揭示）。
 */
export default function WorkflowView() {
    const { t } = useTranslation()
    const rootRef = useRef(null)

    useGSAP(() => {
        const mm = gsap.matchMedia()
        mm.add('(prefers-reduced-motion: no-preference)', () => {
            gsap.utils.toArray('.w-step').forEach((el) => {
                gsap.from(el, {
                    y: 40, autoAlpha: 0, duration: 0.8, ease: 'power3.out',
                    scrollTrigger: { trigger: el, start: 'top 85%', once: true },
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
                <FlowScene />
                <div className="relative z-10 w-full px-6 pt-[72px] md:px-10 lg:px-14">
                    <div className="mx-auto max-w-4xl text-center">
                        <p className="mb-5 text-xs font-medium uppercase tracking-[0.3em] text-white/50">
                            {t('pages.workflow.kicker')}
                        </p>
                        <AnimatedHeading
                            text={t('pages.workflow.title')}
                            className="text-4xl font-normal leading-tight md:text-6xl lg:text-7xl"
                            style={{ letterSpacing: '-0.03em' }}
                        />
                        <p className="mx-auto mt-6 max-w-2xl text-base text-white/70 md:text-lg">
                            {t('pages.workflow.lead')}
                        </p>
                    </div>
                </div>
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-black to-transparent" />
            </section>

            {/* ===== 五步时间线 ===== */}
            <section className="mx-auto max-w-4xl px-6 py-24 md:px-10 lg:px-14">
                <div className="relative">
                    {/* 竖直连接轨 */}
                    <div className="absolute bottom-0 left-[27px] top-2 hidden w-px bg-gradient-to-b from-white/40 via-white/15 to-transparent md:block" />
                    <div className="space-y-14">
                        {STEP_KEYS.map((step, i) => (
                            <div key={step} className="w-step relative flex gap-6 md:gap-10">
                                {/* 序号节点 */}
                                <div className="relative z-10 flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-white/20 bg-black text-lg font-medium">
                                    {String(i + 1).padStart(2, '0')}
                                </div>
                                <div className="pt-1">
                                    <h2 className="mb-2 text-2xl font-medium md:text-3xl" style={{ letterSpacing: '-0.02em' }}>
                                        {t(`workflow.${step}.title`)}
                                    </h2>
                                    <p className="mb-3 text-base font-medium text-white/80">
                                        {t(`workflow.${step}.desc`)}
                                    </p>
                                    <p className="max-w-2xl text-base leading-relaxed text-white/60">
                                        {t(`pages.workflow.detail.${step}`)}
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* CTA */}
                <div className="w-step mt-20 flex flex-wrap justify-center gap-4">
                    <Link to="/#start" className="rounded-lg bg-white px-8 py-3 font-medium text-black transition hover:bg-gray-100">
                        {t('pages.cta')}
                    </Link>
                    <Link to="/vision" className="liquid-glass rounded-lg border border-white/20 px-8 py-3 font-medium text-white transition hover:bg-white hover:text-black">
                        {t('nav.vision')}
                    </Link>
                </div>
            </section>

            <SiteFooter />
        </div>
    )
}
